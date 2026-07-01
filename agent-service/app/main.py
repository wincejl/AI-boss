from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from .boss_browser import BossSearchPayload, search_candidates, snapshot
from .recruitment_agent import run_recruitment_agent
from .schemas import BossBrowserSearchRequest, RecruitmentAgentRequest

load_dotenv()

app = FastAPI(title="AIHR Recruitment Agent Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "ok": True,
        "service": "recruitment-agent",
        "llm_configured": bool(
            os.getenv("AGENT_LLM_API_URL")
            and os.getenv("AGENT_LLM_API_KEY")
            and os.getenv("AGENT_LLM_MODEL")
        ),
        "checkpoint": "sqlite" if os.getenv("AGENT_CHECKPOINT_DB") else "memory",
    }


@app.post("/v1/recruitment/run")
def run_agent(payload: RecruitmentAgentRequest):
    return run_recruitment_agent(payload)


@app.post("/v1/recruitment/draft")
def draft(payload: RecruitmentAgentRequest) -> dict[str, str | bool]:
    result = run_recruitment_agent(payload)
    return {
        "thread_id": result.thread_id,
        "draft": result.draft,
        "requires_human_approval": result.requires_human_approval,
    }


@app.get("/v1/boss/snapshot")
def boss_snapshot():
    return snapshot()


@app.post("/v1/boss/search")
def boss_search(payload: BossBrowserSearchRequest):
    try:
        return search_candidates(BossSearchPayload(**payload.model_dump()))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
