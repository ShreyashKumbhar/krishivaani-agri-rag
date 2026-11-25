"""Pydantic request/response models."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    language: Optional[Literal["hi", "mr", "en"]] = None
    crop: Optional[str] = Field(default=None, max_length=80)
    state: str = Field(default="Maharashtra", max_length=80)
    district: Optional[str] = Field(default=None, max_length=80)
    input_mode: Literal["text", "voice_browser", "voice_upload"] = "text"
    asr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    user_id: Optional[str] = Field(default=None, max_length=120)
    session_id: Optional[str] = Field(default=None, max_length=120)


class FeedbackRequest(BaseModel):
    query_id: str = Field(min_length=3, max_length=80)
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=1000)


class ReviewRequest(BaseModel):
    status: Literal["reviewed", "needs_followup", "dismissed"] = "reviewed"
    note: str = Field(default="", max_length=2000)
    corrected_answer: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="admin", max_length=80)


class DocumentStatusRequest(BaseModel):
    status: Literal["approved", "rejected", "pending", "superseded"]
    note: str = Field(default="", max_length=2000)
    reviewer: str = Field(default="admin", max_length=80)


class AdminLoginRequest(BaseModel):
    username: str = Field(default="admin", max_length=80)
    password: str = Field(default="", max_length=200)
    token: str = Field(default="", max_length=200)


class GlossaryEntryRequest(BaseModel):
    term_en: str = Field(min_length=1, max_length=120)
    term_hi: str = Field(default="", max_length=120)
    term_mr: str = Field(default="", max_length=120)
    category: str = Field(default="general", max_length=40)
    aliases: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=500)


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    language: Literal["hi", "mr", "en"] = "hi"


class QueryResponse(BaseModel):
    query_id: str
    created_at: str
    text: str
    decision: Literal["answer", "ask_to_repeat", "refuse"]
    answer: str
    language: str
    detected_language: str
    language_name: str
    intent: str
    intent_confidence: float
    entities: dict[str, Any]
    confidence: float
    reason_code: str
    reason_detail: str
    signals: dict[str, Any]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    tool_data: Optional[dict[str, Any]] = None
    data_as_of: Optional[str] = None
    simulated: bool
    demo_knowledge: bool
    generation_provider: str
    generation_mode: str
    grounding_score: float
    llm_fallback_reason: Optional[str] = None
    safety_note: Optional[str] = None
    disclaimer: str
    provenance: dict[str, Any]
    suggested_followups: list[str]
    latency_ms: float
    input_mode: str
    asr_confidence: Optional[float] = None
    crop: str
    state: str
    district: str
    review_status: str
