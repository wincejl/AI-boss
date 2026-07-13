from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from .boss_browser import BossSearchPayload, delete_chat, read_candidates, read_chats, search_candidates, send_chat_message, snapshot
from .boss_visual import capture_boss_window, draft_from_ocr_text, ocr_region, probe_region, probe_visual_capabilities, scan_and_draft_boss_chats, scan_boss_chats, wgc_status
from .recruitment_agent import run_recruitment_agent
from .schemas import BossBrowserCandidatesRequest, BossBrowserChatsRequest, BossBrowserDeleteChatRequest, BossBrowserSearchRequest, BossBrowserSendMessageRequest, BossDesktopDraftFromOCRRequest, BossDesktopScanDraftRequest, BossDesktopScanRequest, BossVisualOCRRegionRequest, BossVisualRegionProbeRequest, RecruitmentAgentRequest

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


@app.get("/v1/boss/visual/probe")
def boss_visual_probe():
    return probe_visual_capabilities()


@app.post("/v1/boss/visual/region-probe")
def boss_visual_region_probe(payload: BossVisualRegionProbeRequest):
    return probe_region(payload.x, payload.y, payload.width, payload.height)


@app.post("/v1/boss/visual/ocr-region")
def boss_visual_ocr_region(payload: BossVisualOCRRegionRequest):
    return ocr_region(payload.x, payload.y, payload.width, payload.height)


@app.get("/v1/boss/desktop/wgc-status")
def boss_desktop_wgc_status():
    return wgc_status()


@app.post("/v1/boss/desktop/capture")
def boss_desktop_capture():
    try:
        return capture_boss_window()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/desktop/scan")
def boss_desktop_scan(payload: BossDesktopScanRequest):
    try:
        return scan_boss_chats(payload.count, payload.ocr)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/desktop/draft-from-ocr")
def boss_desktop_draft_from_ocr(payload: BossDesktopDraftFromOCRRequest):
    try:
        return draft_from_ocr_text(payload)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/desktop/scan-draft")
def boss_desktop_scan_draft(payload: BossDesktopScanDraftRequest):
    try:
        return scan_and_draft_boss_chats(payload)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/search")
def boss_search(payload: BossBrowserSearchRequest):
    try:
        return search_candidates(BossSearchPayload(**payload.model_dump()))
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/candidates")
def boss_candidates(payload: BossBrowserCandidatesRequest):
    try:
        return read_candidates(payload.limit)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/chats")
def boss_chats(payload: BossBrowserChatsRequest):
    try:
        return read_chats(payload.limit, payload.incremental)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/send-message")
def boss_send_message(payload: BossBrowserSendMessageRequest):
    try:
        return send_chat_message(payload.name, payload.role, payload.content)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/v1/boss/delete-chat")
def boss_delete_chat(payload: BossBrowserDeleteChatRequest):
    try:
        return delete_chat(payload.name, payload.role)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
