from __future__ import annotations

import operator
import os
import re
import sqlite3
from pathlib import Path
from typing import Annotated, Any, TypedDict

import httpx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .schemas import (
    AgentEvent,
    RecruitmentAgentRequest,
    RecruitmentAgentResponse,
    RecruitmentCandidate,
    RecruitmentRequirement,
)

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except Exception:  # pragma: no cover - optional dependency fallback
    SqliteSaver = None  # type: ignore[assignment]


class AgentState(TypedDict, total=False):
    thread_id: str
    knowledge_context: str
    requirement: dict[str, Any]
    parsed_requirement: dict[str, Any]
    candidate: dict[str, Any]
    parsed_candidate: dict[str, Any]
    stage: str
    match_score: int
    match_reason: str
    risk_flags: list[str]
    draft: str
    next_action: str
    requires_human_approval: bool
    events: Annotated[list[dict[str, str]], operator.add]


def build_recruitment_graph():
    builder = StateGraph(AgentState)
    builder.add_node("normalize_context", normalize_context)
    builder.add_node("parse_requirement", parse_requirement)
    builder.add_node("parse_candidate", parse_candidate)
    builder.add_node("score_match", score_match)
    builder.add_node("draft_message", draft_message)
    builder.add_node("request_human_approval", request_human_approval)
    builder.add_edge(START, "normalize_context")
    builder.add_edge("normalize_context", "parse_requirement")
    builder.add_edge("parse_requirement", "parse_candidate")
    builder.add_edge("parse_candidate", "score_match")
    builder.add_edge("score_match", "draft_message")
    builder.add_edge("draft_message", "request_human_approval")
    builder.add_edge("request_human_approval", END)
    return builder.compile(checkpointer=create_checkpointer())


def create_checkpointer():
    db_path = os.getenv("AGENT_CHECKPOINT_DB", "").strip()
    if db_path and SqliteSaver is not None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        return SqliteSaver(conn)
    return InMemorySaver()


def run_recruitment_agent(payload: RecruitmentAgentRequest) -> RecruitmentAgentResponse:
    thread_id = payload.thread_id or f"candidate-{payload.candidate.id or 'manual'}"
    graph = build_recruitment_graph()
    state: AgentState = {
        "thread_id": thread_id,
        "knowledge_context": payload.knowledge_context,
        "requirement": payload.requirement.model_dump(),
        "candidate": payload.candidate.model_dump(),
        "events": [],
    }
    result = graph.invoke(state, {"configurable": {"thread_id": thread_id}})
    return RecruitmentAgentResponse(
        thread_id=thread_id,
        stage=result.get("stage", "awaiting_human_approval"),
        match_score=int(result.get("match_score", 0)),
        match_reason=str(result.get("match_reason", "")),
        risk_flags=[str(item) for item in result.get("risk_flags", [])],
        draft=str(result.get("draft", "")),
        next_action=str(result.get("next_action", "")),
        requires_human_approval=bool(result.get("requires_human_approval", True)),
        events=[AgentEvent(**event) for event in result.get("events", [])],
    )


def normalize_context(state: AgentState) -> dict[str, Any]:
    requirement = normalize_dict(state.get("requirement", {}))
    candidate = normalize_dict(state.get("candidate", {}))
    return {
        "requirement": requirement,
        "candidate": candidate,
        "stage": "profile_ready",
        "events": [
            {
                "step": "normalize_context",
                "status": "ok",
                "message": "Requirement and candidate fields normalized.",
            }
        ],
    }


def score_match(state: AgentState) -> dict[str, Any]:
    requirement = RecruitmentRequirement(**state.get("requirement", {}))
    candidate = RecruitmentCandidate(**state.get("candidate", {}))
    from .recruitment_scoring import score_candidate_match

    rule_score, rule_reason, risk_flags, next_action = score_candidate_match(requirement, candidate)
    semantic_score = compute_semantic_similarity(requirement, candidate)
    score = _combine_scores(rule_score, semantic_score)
    if semantic_score is not None:
        msg = f"总分{score}（规则分{rule_score} + 语义分{semantic_score}）: {rule_reason}"
        match_reason = f"规则分{rule_score}；{rule_reason}；语义相似度分{semantic_score}"
    else:
        msg = f"总分{score}: {rule_reason}"
        match_reason = f"规则分{rule_score}；{rule_reason}"
    return {
        "match_score": score,
        "match_reason": match_reason,
        "risk_flags": risk_flags,
        "next_action": next_action,
        "stage": "matched",
        "events": [
            {
                "step": "score_match",
                "status": "ok",
                "message": msg,
            }
        ],
    }


def draft_message(state: AgentState) -> dict[str, Any]:
    requirement = RecruitmentRequirement(**state.get("requirement", {}))
    candidate = RecruitmentCandidate(**state.get("candidate", {}))
    reason = str(state.get("match_reason", "profile has matching points"))
    knowledge_context = str(state.get("knowledge_context", ""))
    draft = llm_draft(requirement, candidate, reason, knowledge_context) or fallback_draft(
        requirement, candidate, reason
    )
    return {
        "draft": draft,
        "stage": "drafted",
        "events": [
            {
                "step": "draft_message",
                "status": "ok",
                "message": "First-contact draft generated.",
            }
        ],
    }


def request_human_approval(state: AgentState) -> dict[str, Any]:
    candidate = RecruitmentCandidate(**state.get("candidate", {}))
    next_action = clean_text(str(state.get("next_action", "")))
    if not next_action:
        next_action = with_knowledge_hint(
            next_action_for(candidate), str(state.get("knowledge_context", ""))
        )
    return {
        "next_action": next_action,
        "stage": "awaiting_human_approval",
        "requires_human_approval": True,
        "events": [
            {
                "step": "request_human_approval",
                "status": "pending",
                "message": "Human review is required before any BOSS message is sent.",
            }
        ],
    }


def clean_text(value: str) -> str:
    return value.strip()


def normalize_dict(value: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, raw in value.items():
        normalized[key] = raw.strip() if isinstance(raw, str) else raw
    return normalized


def parse_requirement(state: AgentState) -> dict[str, Any]:
    requirement = RecruitmentRequirement(**state.get("requirement", {}))
    parsed = parse_hard_requirements(requirement)
    summary = summarize_hard_requirements(parsed)
    return {
        "parsed_requirement": parsed,
        "stage": "requirement_parsed",
        "events": [
            {
                "step": "parse_requirement",
                "status": "ok",
                "message": summary,
            }
        ],
    }


def parse_candidate(state: AgentState) -> dict[str, Any]:
    candidate = RecruitmentCandidate(**state.get("candidate", {}))
    parsed = parse_candidate_profile(candidate)
    summary = summarize_candidate_profile(parsed)
    return {
        "parsed_candidate": parsed,
        "stage": "candidate_parsed",
        "events": [
            {
                "step": "parse_candidate",
                "status": "ok",
                "message": summary,
            }
        ],
    }


EDUCATION_RANKS = ["初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"]


def parse_hard_requirements(requirement: RecruitmentRequirement) -> dict[str, Any]:
    filters = parse_filter_pairs(requirement.recommended_filters)
    keyword = first_non_empty(
        requirement.search_keyword,
        requirement.role,
        "" if "不限" in requirement.job_category else requirement.job_category,
        requirement.title,
    )
    education_raw = (requirement.education_requirement or "").strip()
    if not education_raw or education_raw == "不限":
        education_raw = map_school_requirement(filters.get("院校要求", ""))
    experience_raw = first_non_empty(filters.get("经验要求", ""), filters.get("工作经验", ""))
    return {
        "keyword": keyword,
        "location": requirement.location,
        "age": parse_age_range(requirement.age_requirement),
        "education": parse_education_range(education_raw),
        "experience": parse_experience_range(experience_raw),
        "salary": parse_salary_range(filters.get("薪资区间", "")),
        "major": parse_major_requirement(filters.get("专业要求", "")),
        "activity": first_non_empty(filters.get("活跃度", ""), filters.get("活跃状态", "")),
        "job_status": filters.get("求职状态", ""),
        "gender": filters.get("性别要求", ""),
        "position": filters.get("职位要求", ""),
        "bonus": tokens(requirement.nice_have),
        "exclusions": parse_exclusion_tokens(requirement.must_have),
        "raw_filters": filters,
    }


def map_school_requirement(raw: str) -> str:
    value = (raw or "").strip()
    if not value or value == "不限":
        return "不限"
    if "博士" in value:
        return "博士"
    if "硕士" in value:
        return "硕士及以上"
    if "本科" in value:
        return "本科及以上"
    if "大专" in value:
        return "大专及以上"
    return value


def parse_filter_pairs(raw: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for item in re.split(r"[;；]", raw or ""):
        if not item.strip():
            continue
        parts = re.split(r"[:：=]", item, maxsplit=1)
        if len(parts) != 2:
            continue
        key, value = parts[0].strip(), parts[1].strip()
        if key and value and value != "不限":
            pairs[key] = value
    return pairs


def parse_age_range(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value or value == "不限":
        return {"raw": value, "required": False, "min": None, "max": None}
    hit = re.search(r"(\d{1,2})\s*[-~到至]\s*(\d{1,2})", value)
    if hit:
        low, high = sorted([int(hit.group(1)), int(hit.group(2))])
        return {"raw": value, "required": True, "min": low, "max": high}
    hit = re.search(r"(\d{1,2})\s*以上", value)
    if hit:
        return {"raw": value, "required": True, "min": int(hit.group(1)), "max": None}
    hit = re.search(r"(\d{1,2})\s*以下", value)
    if hit:
        return {"raw": value, "required": True, "min": None, "max": int(hit.group(1))}
    return {"raw": value, "required": True, "min": None, "max": None}


def parse_education_range(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value or value == "不限":
        return {"raw": value, "required": False, "min": None, "max": None}
    if "-" in value:
        parts = [part.strip() for part in value.split("-", maxsplit=1)]
        known = [part for part in parts if part in EDUCATION_RANKS]
        if len(known) == 2:
            ordered = sorted(known, key=EDUCATION_RANKS.index)
            return {"raw": value, "required": True, "min": ordered[0], "max": ordered[1]}
    for level in EDUCATION_RANKS:
        if value.startswith(level) or level in value:
            max_level = None if "以上" in value else level
            return {"raw": value, "required": True, "min": level, "max": max_level}
    return {"raw": value, "required": True, "min": None, "max": None}


def parse_experience_range(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value or value == "不限":
        return {"raw": value, "required": False, "min_years": None, "max_years": None, "category": ""}
    if any(key in value for key in ["应届", "在校", "毕业"]):
        return {"raw": value, "required": True, "min_years": 0, "max_years": 0, "category": "fresh_or_student"}
    hit = re.search(r"(\d+)\s*[-~到至]\s*(\d+)\s*年", value)
    if hit:
        low, high = sorted([int(hit.group(1)), int(hit.group(2))])
        return {"raw": value, "required": True, "min_years": low, "max_years": high, "category": "years"}
    hit = re.search(r"(\d+)\s*年以上", value)
    if hit:
        return {"raw": value, "required": True, "min_years": int(hit.group(1)), "max_years": None, "category": "years"}
    return {"raw": value, "required": True, "min_years": None, "max_years": None, "category": ""}


def parse_salary_range(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value or value == "不限":
        return {"raw": value, "required": False, "min_k": None, "max_k": None}
    hit = re.search(r"(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)\s*[Kk]", value)
    if hit:
        low, high = sorted([float(hit.group(1)), float(hit.group(2))])
        return {"raw": value, "required": True, "min_k": low, "max_k": high}
    hit = re.search(r"(\d+(?:\.\d+)?)\s*[Kk]", value)
    if hit:
        amount = float(hit.group(1))
        return {"raw": value, "required": True, "min_k": amount, "max_k": amount}
    return {"raw": value, "required": True, "min_k": None, "max_k": None}


def parse_major_requirement(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value or value == "不限":
        return {"raw": value, "required": False, "category": "", "group": "", "major": ""}
    parts = [part.strip() for part in value.split("/") if part.strip()]
    return {
        "raw": value,
        "required": True,
        "category": parts[0] if len(parts) >= 1 else "",
        "group": parts[1] if len(parts) >= 2 and parts[1] != "全部" else "",
        "major": parts[2] if len(parts) >= 3 and parts[2] != "全部" else "",
    }


def parse_exclusion_tokens(raw: str) -> list[str]:
    exclusions: list[str] = []
    for token in tokens(raw):
        cleaned = re.sub(r"^(排除|不要|不能|不接受|禁止)[:：]?", "", token).strip()
        has_exclusion_prefix = token.startswith(("排除", "不要", "不能", "不接受", "禁止"))
        if cleaned and (cleaned != token or has_exclusion_prefix):
            exclusions.append(cleaned)
    return exclusions


def first_non_empty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def summarize_hard_requirements(parsed: dict[str, Any]) -> str:
    parts = [
        f"岗位关键词={parsed.get('keyword') or '未设置'}",
        f"地区={parsed.get('location') or '不限'}",
        f"年龄={parsed.get('age', {}).get('raw') or '不限'}",
        f"学历={parsed.get('education', {}).get('raw') or '不限'}",
        f"经验={parsed.get('experience', {}).get('raw') or '不限'}",
        f"薪资={parsed.get('salary', {}).get('raw') or '不限'}",
        f"专业={parsed.get('major', {}).get('raw') or '不限'}",
    ]
    if parsed.get("activity"):
        parts.append(f"活跃度={parsed['activity']}")
    if parsed.get("job_status"):
        parts.append(f"求职状态={parsed['job_status']}")
    return "硬性要求解析: " + "；".join(parts)


def parse_candidate_profile(candidate: RecruitmentCandidate) -> dict[str, Any]:
    resume_text = "\n".join(
        item for item in [
            candidate.current_role,
            candidate.location,
            candidate.tags,
            candidate.profile,
            candidate.last_message,
        ] if item
    )
    return {
        "age": parse_candidate_age(resume_text),
        "education": parse_candidate_education(resume_text),
        "experience": parse_candidate_experience(resume_text),
        "current_role": candidate.current_role,
        "expected_city": parse_expected_city(resume_text, candidate.location),
        "salary": parse_candidate_salary(resume_text),
        "activity": parse_candidate_activity(resume_text),
        "job_status": parse_candidate_job_status(resume_text),
        "major": parse_candidate_major(resume_text),
        "tags": tokens(candidate.tags),
        "resume_text": resume_text,
    }


def parse_candidate_age(text: str) -> dict[str, Any]:
    hit = re.search(r"(\d{1,2})\s*岁", text)
    if not hit:
        return {"raw": "", "value": None}
    return {"raw": hit.group(0), "value": int(hit.group(1))}


def parse_candidate_education(text: str) -> dict[str, Any]:
    for level in reversed(EDUCATION_RANKS):
        if level in text:
            return {"raw": level, "level": level, "rank": EDUCATION_RANKS.index(level)}
    return {"raw": "", "level": "", "rank": None}


def parse_candidate_experience(text: str) -> dict[str, Any]:
    if any(key in text for key in ["应届", "在校", "毕业生"]):
        return {"raw": "应届/在校", "years": 0, "category": "fresh_or_student"}
    hit = re.search(r"(\d+)\s*年(?:以上)?(?:工作|相关|岗位|服务|餐饮|实习|采购|管理)?经验", text)
    if hit:
        return {"raw": hit.group(0), "years": int(hit.group(1)), "category": "years"}
    hit = re.search(r"经验\s*(\d+)\s*年", text)
    if hit:
        return {"raw": hit.group(0), "years": int(hit.group(1)), "category": "years"}
    hit = re.search(r"(\d+)\s*年以上", text)
    if hit:
        return {"raw": hit.group(0), "years": int(hit.group(1)), "category": "years"}
    hit = re.search(r"(?m)^\s*(\d+)\s*年(?:以上)?\s*$", text)
    if hit:
        return {"raw": hit.group(0).strip(), "years": int(hit.group(1)), "category": "years"}
    return {"raw": "", "years": None, "category": ""}


def parse_expected_city(text: str, fallback_location: str) -> str:
    for pattern in [
        r"期望(?!薪资|工资|待遇)(?:城市|地点|工作地|地区)?[:：]?\s*([\u4e00-\u9fa5]{2,12})",
        r"居住(?:地|在)?[:：]?\s*([\u4e00-\u9fa5]{2,12})",
    ]:
        hit = re.search(pattern, text)
        if hit:
            return hit.group(1).strip("，。；;、 ")
    return fallback_location


def parse_candidate_salary(text: str) -> dict[str, Any]:
    hit = re.search(r"(?:期望薪资|薪资|月薪)[:：]?\s*(\d+(?:\.\d+)?)\s*[Kk]", text)
    if hit:
        amount = float(hit.group(1))
        return {"raw": hit.group(0), "min_k": amount, "max_k": amount}
    hit = re.search(r"(?:期望薪资|薪资|月薪)[:：]?\s*(\d{3,5})", text)
    if hit:
        amount = round(float(hit.group(1)) / 1000, 2)
        return {"raw": hit.group(0), "min_k": amount, "max_k": amount}
    hit = re.search(r"(\d+(?:\.\d+)?)\s*[-~到至]\s*(\d+(?:\.\d+)?)\s*[Kk]", text)
    if hit:
        low, high = sorted([float(hit.group(1)), float(hit.group(2))])
        return {"raw": hit.group(0), "min_k": low, "max_k": high}
    return {"raw": "", "min_k": None, "max_k": None}


def parse_candidate_activity(text: str) -> str:
    for value in ["刚刚活跃", "今日活跃", "本周活跃", "3日内活跃", "2周内活跃", "近一周活跃", "近一个月活跃"]:
        if value in text:
            return value
    return ""


def parse_candidate_job_status(text: str) -> str:
    for value in ["离职-随时到岗", "在职-暂不考虑", "在职-考虑机会", "在职-月内到岗"]:
        if value in text:
            return value
    if "随时到岗" in text:
        return "离职-随时到岗"
    if "考虑机会" in text:
        return "在职-考虑机会"
    return ""


def parse_candidate_major(text: str) -> dict[str, str]:
    hit = re.search(r"([\u4e00-\u9fa5]{1,12})(?:专业|类)", text)
    if not hit:
        return {"raw": "", "name": ""}
    return {"raw": hit.group(0), "name": hit.group(1)}


def summarize_candidate_profile(parsed: dict[str, Any]) -> str:
    parts = [
        f"年龄={parsed.get('age', {}).get('raw') or '未知'}",
        f"学历={parsed.get('education', {}).get('level') or '未知'}",
        f"经验={parsed.get('experience', {}).get('raw') or '未知'}",
        f"当前岗位={parsed.get('current_role') or '未知'}",
        f"期望城市={parsed.get('expected_city') or '未知'}",
        f"薪资={parsed.get('salary', {}).get('raw') or '未知'}",
    ]
    if parsed.get("activity"):
        parts.append(f"活跃度={parsed['activity']}")
    if parsed.get("job_status"):
        parts.append(f"求职状态={parsed['job_status']}")
    if parsed.get("major", {}).get("raw"):
        parts.append(f"专业={parsed['major']['raw']}")
    return "候选人解析: " + "；".join(parts)


def _combine_scores(rule_score: int, semantic_score: float | None) -> int:
    """Combine rule score (0-100) and optional semantic score (0-100) into final score."""
    if semantic_score is None:
        return rule_score
    return round(rule_score * 0.6 + semantic_score * 0.4)


_semantic_cache: dict[str, float] = {}
_EMB_API_URL = os.getenv("AGENT_EMBEDDING_API_URL", "").strip()
_EMB_API_KEY = os.getenv("AGENT_EMBEDDING_API_KEY", "").strip()
_EMB_MODEL = os.getenv("AGENT_EMBEDDING_MODEL", "text-embedding-3-small").strip()


def _build_requirement_text(requirement: RecruitmentRequirement) -> str:
    parts = [requirement.role, requirement.search_keyword, requirement.description]
    if requirement.must_have:
        parts.append(requirement.must_have)
    if requirement.nice_have:
        parts.append(requirement.nice_have)
    return " ".join(part for part in parts if part)


def _build_candidate_text(candidate: RecruitmentCandidate) -> str:
    parts = [candidate.current_role, candidate.tags, candidate.profile, candidate.last_message]
    return " ".join(part for part in parts if part)


def _compute_cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    n1 = sum(a * a for a in v1) ** 0.5
    n2 = sum(b * b for b in v2) ** 0.5
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def compute_semantic_similarity(
    requirement: RecruitmentRequirement, candidate: RecruitmentCandidate
) -> float | None:
    if not _EMB_API_URL or not _EMB_API_KEY:
        return None
    query_text = _build_requirement_text(requirement)
    doc_text = _build_candidate_text(candidate)
    if not query_text or not doc_text:
        return None
    texts = [query_text, doc_text]
    key = "|".join(texts)
    if key in _semantic_cache:
        return _semantic_cache[key]
    try:
        resp = httpx.post(
            _EMB_API_URL,
            headers={"Authorization": f"Bearer {_EMB_API_KEY}", "Content-Type": "application/json"},
            json={"model": _EMB_MODEL, "input": texts},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        vectors = [item["embedding"] for item in data["data"]]
        if len(vectors) == 2:
            raw_sim = _compute_cosine_similarity(vectors[0], vectors[1])
            score = round(max(0, min(100, (raw_sim + 1) * 50)), 1)
            _semantic_cache[key] = score
            return score
    except Exception:
        pass
    return None


def tokens(raw: str) -> list[str]:
    items = [item.strip() for item in re.split(r"[,，;；/、\s]+", raw or "")]
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def llm_draft(
    requirement: RecruitmentRequirement,
    candidate: RecruitmentCandidate,
    reason: str,
    knowledge_context: str,
) -> str:
    api_url = os.getenv("AGENT_LLM_API_URL", "").strip()
    api_key = os.getenv("AGENT_LLM_API_KEY", "").strip()
    model = os.getenv("AGENT_LLM_MODEL", "").strip()
    if not api_url or not api_key or not model:
        return ""

    prompt = (
        "你是招聘沟通助手。请生成一段 BOSS 平台内首轮沟通话术，要求："
        "语气自然、简短；不要承诺薪资；不要索要隐私；需要联系方式或入群时必须先征得明确同意。\n\n"
        f"岗位: {requirement.role or requirement.title}\n"
        f"地点: {requirement.location or '不限'}\n"
        f"岗位说明: {requirement.description}\n"
        f"候选人: {candidate.name}\n"
        f"候选人资料: {candidate.current_role} {candidate.tags} {candidate.profile}\n"
        f"匹配原因: {reason}"
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你只输出可直接发送前需人工确认的话术正文。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(os.getenv("AGENT_LLM_TEMPERATURE", "1") or "1"),
        "max_completion_tokens": 450,
    }
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()
    except Exception:
        return ""


def fallback_draft(
    requirement: RecruitmentRequirement, candidate: RecruitmentCandidate, reason: str
) -> str:
    name = candidate.name or "你好"
    role = requirement.role or requirement.title or "相关岗位"
    location = requirement.location or "本地"
    return (
        f"{name}，你好。我这边有一个{location}的{role}机会，"
        f"看到你的资料里{reason}，想先确认你近期是否考虑相关工作机会？"
        "如果你愿意，我们可以先在平台内沟通岗位内容；后续需要记录联系方式或邀请进群时，会先征得你的明确同意。"
    )


def with_knowledge_hint(action: str, knowledge_context: str) -> str:
    lines = (knowledge_context or "").strip().splitlines()
    if not lines:
        return action
    hint = lines[0].strip()
    if not hint:
        return action
    return f"{action}\nKnowledge hint: {hint[:160]}"


def next_action_for(candidate: RecruitmentCandidate) -> str:
    if candidate.consent_to_contact and candidate.private_contact:
        return "核对联系方式并确认是否愿意加入微信群或企业微信。"
    if candidate.contact_status == "replied":
        return "根据候选人回复继续沟通岗位细节，不要在未同意前记录私人联系方式。"
    if candidate.contact_status == "contacted":
        return "等待候选人回复；如长期未回复，由人工判断是否停止跟进。"
    return "人工确认首轮话术后，在 BOSS 平台内发送。"
