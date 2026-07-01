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
    candidate: dict[str, Any]
    stage: str
    match_score: int
    match_reason: str
    draft: str
    next_action: str
    requires_human_approval: bool
    events: Annotated[list[dict[str, str]], operator.add]


def build_recruitment_graph():
    builder = StateGraph(AgentState)
    builder.add_node("normalize_context", normalize_context)
    builder.add_node("score_match", score_match)
    builder.add_node("draft_message", draft_message)
    builder.add_node("request_human_approval", request_human_approval)
    builder.add_edge(START, "normalize_context")
    builder.add_edge("normalize_context", "score_match")
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
    score, reason = heuristic_score(requirement, candidate)
    return {
        "match_score": score,
        "match_reason": reason,
        "stage": "matched",
        "events": [
            {
                "step": "score_match",
                "status": "ok",
                "message": f"Score {score}: {reason}",
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


def normalize_dict(value: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, raw in value.items():
        normalized[key] = raw.strip() if isinstance(raw, str) else raw
    return normalized


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
            reasons.append(f"job keyword matched: {token}")
            break

    if requirement.location and requirement.location.lower() in haystack:
        score += 15
        reasons.append(f"location matched: {requirement.location}")

    score += weighted_token_score(haystack, requirement.must_have, 12, 35, reasons, "must-have")
    score += weighted_token_score(haystack, requirement.nice_have, 6, 18, reasons, "nice-have")
    score += weighted_token_score(haystack, requirement.tags, 8, 24, reasons, "tag")

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
