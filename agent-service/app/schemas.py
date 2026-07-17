from __future__ import annotations

from pydantic import BaseModel, Field


class RecruitmentRequirement(BaseModel):
    id: int = 0
    title: str = ""
    role: str = ""
    job_category: str = ""
    location: str = ""
    search_keyword: str = ""
    education_requirement: str = ""
    age_requirement: str = ""
    recommended_filters: str = ""
    sort_preference: str = ""
    filter_viewed_14_days: bool = False
    filter_exchanged_30_days: bool = False
    batch_size: int = 10
    tags: str = ""
    must_have: str = ""
    nice_have: str = ""
    description: str = ""


class RecruitmentCandidate(BaseModel):
    id: int = 0
    name: str = ""
    source: str = ""
    current_role: str = ""
    location: str = ""
    tags: str = ""
    profile: str = ""
    contact_status: str = "new"
    consent_to_contact: bool = False
    private_contact: str = ""
    group_status: str = "not_invited"
    last_message: str = ""
    next_action: str = ""


class RecruitmentAgentRequest(BaseModel):
    thread_id: str = ""
    knowledge_context: str = ""
    requirement: RecruitmentRequirement
    candidate: RecruitmentCandidate


class AgentEvent(BaseModel):
    step: str
    status: str = "ok"
    message: str = ""


class RecruitmentAgentResponse(BaseModel):
    thread_id: str
    stage: str
    match_score: int = Field(ge=0, le=100)
    match_reason: str
    risk_flags: list[str] = Field(default_factory=list)
    draft: str
    next_action: str
    requires_human_approval: bool = True
    mode: str = "langgraph"
    events: list[AgentEvent] = Field(default_factory=list)


class BossBrowserSearchRequest(BaseModel):
    city: str = ""
    category: str = ""
    keyword: str = ""
    education: str = ""
    age: str = ""
    recommended_filters: str = ""
    sort_preference: str = ""
    filter_viewed_14_days: bool = False
    filter_exchanged_30_days: bool = False


class BossBrowserCandidatesRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class BossBrowserChatsRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)
    incremental: bool = False


class BossBrowserSendMessageRequest(BaseModel):
    name: str
    role: str = ""
    content: str


class BossBrowserDeleteChatRequest(BaseModel):
    name: str
    role: str = ""


class BossVisualRegionProbeRequest(BaseModel):
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    width: int = Field(default=1, ge=1, le=1200)
    height: int = Field(default=1, ge=1, le=900)


class BossVisualOCRRegionRequest(BaseModel):
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    width: int = Field(default=1, ge=1, le=1200)
    height: int = Field(default=1, ge=1, le=900)


class BossDesktopScanRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=10)
    ocr: bool = False
    select_first: bool = False


class BossDesktopDraftFromOCRRequest(BaseModel):
    thread_id: str = ""
    knowledge_context: str = ""
    requirement: RecruitmentRequirement
    chat_text: str = Field(default="", min_length=1)
    candidate_name: str = ""
    current_role: str = ""


class BossDesktopScanDraftRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=5)
    knowledge_context: str = ""
    requirement: RecruitmentRequirement
