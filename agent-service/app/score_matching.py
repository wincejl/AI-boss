from __future__ import annotations
import operator
import os
import re
from typing import Annotated, Any, TypedDict

import httpx
from .schemas import (
    AgentEvent,
    RecruitmentAgentRequest,
    RecruitmentAgentResponse,
    RecruitmentCandidate,
    RecruitmentRequirement,
)

from recruitment_agent import ( AgentState
)


def score_match(state: AgentState) -> dict[str, Any]:
    requirement = RecruitmentRequirement(**state.get("requirement", {}))
    candidate = RecruitmentCandidate(**state.get("candidate", {}))
    rule_score, rule_reason = heuristic_score(requirement, candidate)
    semantic_score = compute_semantic_similarity(requirement, candidate)
    score = _combine_scores(rule_score, semantic_score)
    if semantic_score is not None:
        msg = f"总分{score}（规则分{rule_score} + 语义分{semantic_score}）: {rule_reason}"
        match_reason = f"规则分{rule_score}；{rule_reason}；语义相似度分{semantic_score}"
    else:
        msg = f"Score {score}: {rule_reason}"
        match_reason = f"规则分{rule_score}；{rule_reason}"
    return {
        "match_score": score,
        "match_reason": match_reason,
        "stage": "matched",
        "events": [
            {
                "step": "score_match",
                "status": "ok",
                "message": msg,
            }
        ],
    }


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
    return {
        "keyword": keyword,
        "location": requirement.location,
        "age": parse_age_range(requirement.age_requirement),
        "education": parse_education_range(requirement.education_requirement),
        "experience": parse_experience_range(filters.get("经验要求", "")),
        "salary": parse_salary_range(filters.get("薪资区间", "")),
        "major": parse_major_requirement(filters.get("专业要求", "")),
        "activity": filters.get("活跃度", ""),
        "job_status": filters.get("求职状态", ""),
        "gender": filters.get("性别要求", ""),
        "position": filters.get("职位要求", ""),
        "bonus": tokens(requirement.nice_have),
        "exclusions": parse_exclusion_tokens(requirement.must_have),
        "raw_filters": filters,
    }


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
    hit = re.search(r"(\d+)\s*年(?:以上)?(?:工作|相关|岗位|服务|餐饮|实习)?经验", text)
    if hit:
        return {"raw": hit.group(0), "years": int(hit.group(1)), "category": "years"}
    hit = re.search(r"经验\s*(\d+)\s*年", text)
    if hit:
        return {"raw": hit.group(0), "years": int(hit.group(1)), "category": "years"}
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
    for value in ["刚刚活跃", "今日活跃", "3日内活跃", "近一周活跃", "近一个月活跃"]:
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


def heuristic_score(
    requirement: RecruitmentRequirement, candidate: RecruitmentCandidate
) -> tuple[int, str]:
    haystack = " ".join(
        [
            candidate.name,
            candidate.current_role,
            candidate.location,
            candidate.tags,
            candidate.profile,
            candidate.last_message,
            
        ]
    ).lower()
    score = 0
    reasons: list[str] = []

    for token in tokens(requirement.role):
        if token.lower() in haystack:
            score += 30
            reasons.append(f"岗位匹配: {token}")
            break

    if requirement.location and requirement.location.lower() in haystack:
        score += 15
        reasons.append(f"工作地点匹配: {requirement.location}")

    ## 年龄

    ## 学历
    ## 经验
    ## 活跃度 

    if score > 100:
        score = 100
    if not reasons:
        reasons.append("manual review required")
    return score, "; ".join(sorted(reasons))


def weighted_token_score(
    haystack: str, raw: str, per_hit: int, max_score: int, reasons: list[str], label: str
) -> int:
    total = 0
    for token in tokens(raw):
        if token.lower() in haystack:
            total += per_hit
            reasons.append(f"{label} matched: {token}")
        if total >= max_score:
            return max_score
    return total



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

## 可以添加本地向量化(后续)
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