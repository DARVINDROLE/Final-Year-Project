from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RingEvent(BaseModel):
    type: str = "ring"
    session_id: str | None = Field(None, description="Leave null for auto-generation")
    timestamp: datetime
    image_base64: str | None = Field(None, description="Base64-encoded image or null")
    audio_base64: str | None = Field(None, description="Base64-encoded audio or null")
    image_path: str | None = None
    audio_path: str | None = None
    device_id: str = Field(..., example="frontdoor-01")
    metadata: dict[str, Any] = Field(default_factory=dict, example={"rssi": -50})


class ObjectDetection(BaseModel):
    label: str
    conf: float


class PerceptionOutput(BaseModel):
    session_id: str
    person_detected: bool
    objects: list[ObjectDetection] = Field(default_factory=list)
    vision_confidence: float = 0.0
    transcript: str = ""
    stt_confidence: float = 0.0
    emotion: str = "neutral"
    anti_spoof_score: float = 0.0
    weapon_detected: bool = False
    weapon_confidence: float = 0.0
    weapon_labels: list[str] = Field(default_factory=list)
    image_path: str
    timestamp: datetime
    # --- Indian-scenario context flags (Phase 5 hardening) ---
    num_persons: int = 0
    face_visible: bool = True
    context_flags: list[str] = Field(default_factory=list)


class IntelligenceOutput(BaseModel):
    session_id: str
    intent: str
    reply_text: str
    risk_score: float
    escalation_required: bool
    tags: list[str] = Field(default_factory=list)
    timestamp: datetime


class DecisionOutput(BaseModel):
    session_id: str
    final_action: str
    reason: str
    dispatch: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class ActionRequest(BaseModel):
    session_id: str
    tts_text: str
    image_path: str
    notify_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class AiReplyRequest(BaseModel):
    session_id: str
    message: str
    owner: bool = True
    dispatch_action: bool = False


class ActionResult(BaseModel):
    session_id: str
    status: str
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
