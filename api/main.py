from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import AiReplyRequest, RingEvent
from .orchestrator import Orchestrator

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI(title="Smart Doorbell API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve data/snaps and data/tts as static files so frontend can load images/audio
for static_dir in ["data/snaps", "data/tts"]:
    Path(static_dir).mkdir(parents=True, exist_ok=True)
app.mount("/static/snaps", StaticFiles(directory="data/snaps"), name="snaps")
app.mount("/static/tts", StaticFiles(directory="data/tts"), name="tts")
app.mount("/static/members", StaticFiles(directory="data/members"), name="members")


# ── Helpers ───────────────────────────────────────────────────

def _build_orchestrator() -> Orchestrator:
    db_path = os.getenv("DOORBELL_DB_PATH", "data/db.sqlite")
    orchestrator = Orchestrator(db_path=db_path)
    orchestrator.initialize()
    return orchestrator


def _get_db():
    return app.state.orchestrator.db


def _require_auth(authorization: str | None) -> dict:
    """Validate Bearer token and return owner dict. Raises 401 if invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    owner = _get_db().verify_token(token)
    if not owner:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return owner


# ── WebSocket connection manager ──────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections per session for real-time updates."""
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(session_id, []).append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        if session_id in self.active:
            self.active[session_id] = [w for w in self.active[session_id] if w != ws]

    async def broadcast(self, session_id: str, data: dict):
        for ws in self.active.get(session_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass

ws_manager = ConnectionManager()


# ── Startup ───────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    app.state.orchestrator = _build_orchestrator()
    app.state.ws_manager = ws_manager
    # Ensure member photos directory exists
    Path("data/members").mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# Auth endpoints
# ══════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str = ""

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
async def register(req: RegisterRequest) -> dict:
    result = _get_db().register_owner(req.username, req.password, req.name)
    if not result:
        raise HTTPException(status_code=409, detail="Username already taken")
    token = _get_db().create_token(result["id"])
    return {"user": result, "token": token}


@app.post("/api/auth/login")
async def login(req: LoginRequest) -> dict:
    owner = _get_db().verify_owner(req.username, req.password)
    if not owner:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _get_db().create_token(owner["id"])
    return {"user": owner, "token": token}


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        _get_db().delete_token(token)
    return {"status": "ok"}


@app.get("/api/auth/me")
async def auth_me(authorization: Optional[str] = Header(None)) -> dict:
    owner = _require_auth(authorization)
    return {"user": owner}


# ══════════════════════════════════════════════════════════════
# Member management endpoints
# ══════════════════════════════════════════════════════════════

class MemberCreate(BaseModel):
    name: str
    phone: str = ""
    role: str = "family"
    photo_base64: str = ""

class MemberUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    permitted: Optional[bool] = None
    photo_base64: Optional[str] = None


@app.get("/api/members")
async def list_members(authorization: Optional[str] = Header(None)) -> list[dict]:
    owner = _require_auth(authorization)
    return _get_db().get_members(owner["id"])


@app.post("/api/members")
async def create_member(req: MemberCreate, authorization: Optional[str] = Header(None)) -> dict:
    owner = _require_auth(authorization)
    photo_path = ""
    if req.photo_base64:
        photo_path = _save_member_photo(req.name, req.photo_base64)
    return _get_db().add_member(owner["id"], req.name, req.phone, req.role, photo_path)


@app.put("/api/members/{member_id}")
async def update_member(member_id: int, req: MemberUpdate, authorization: Optional[str] = Header(None)) -> dict:
    owner = _require_auth(authorization)
    kwargs = {}
    if req.name is not None:
        kwargs["name"] = req.name
    if req.phone is not None:
        kwargs["phone"] = req.phone
    if req.role is not None:
        kwargs["role"] = req.role
    if req.permitted is not None:
        kwargs["permitted"] = 1 if req.permitted else 0
    if req.photo_base64:
        kwargs["photo_path"] = _save_member_photo(req.name or f"member_{member_id}", req.photo_base64)
    ok = _get_db().update_member(member_id, owner["id"], **kwargs)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"status": "updated"}


@app.delete("/api/members/{member_id}")
async def delete_member(member_id: int, authorization: Optional[str] = Header(None)) -> dict:
    owner = _require_auth(authorization)
    ok = _get_db().delete_member(member_id, owner["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"status": "deleted"}


def _save_member_photo(name: str, photo_base64: str) -> str:
    photos_dir = Path("data/members")
    photos_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower())
    photo_path = photos_dir / f"{safe_name}_{os.urandom(4).hex()}.jpg"
    photo_bytes = base64.b64decode(photo_base64.strip())
    photo_path.write_bytes(photo_bytes)
    return str(photo_path).replace("\\", "/")


# ══════════════════════════════════════════════════════════════
# Core doorbell endpoints (existing + enhanced)
# ══════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "smart-doorbell-backend"}


@app.post("/api/ring")
async def ring(payload: RingEvent) -> dict:
    result = await app.state.orchestrator.handle_ring(payload)
    # Notify any WebSocket listeners about the new ring (with image and greeting)
    session_id = result.get("sessionId", "")
    if session_id:
        asyncio.create_task(
            ws_manager.broadcast("owner", {
                "type": "new_ring",
                "sessionId": session_id,
                "greeting": result.get("greeting", ""),
                "imageUrl": result.get("imageUrl"),
            })
        )
    return result


class TranscribeRequest(BaseModel):
    audio_base64: str


@app.post("/api/transcribe")
async def transcribe(payload: TranscribeRequest) -> dict:
    """Transcribe audio using Groq Whisper STT (via perception agent)."""
    try:
        result = await app.state.orchestrator.transcribe_audio(payload.audio_base64)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Transcription failed: %s", e)
        raise HTTPException(status_code=500, detail="Transcription failed")


class TTSRequest(BaseModel):
    text: str
    session_id: str = ""


@app.post("/api/tts")
async def tts_generate(payload: TTSRequest) -> dict:
    """Generate TTS audio for the given text (supports Hindi and English).
    Returns the URL to the generated audio file."""
    from .utils.tts import generate_tts_audio
    import uuid

    sid = payload.session_id or f"tts_{uuid.uuid4().hex[:8]}"
    try:
        path = await asyncio.to_thread(
            generate_tts_audio,
            text=payload.text,
            session_id=sid,
            output_dir="data/tts",
            play=False,
        )
        if path and (path.endswith(".mp3") or path.endswith(".wav")):
            filename = Path(path).name
            return {"audioUrl": f"/static/tts/{filename}", "sessionId": sid}
        return {"audioUrl": None, "sessionId": sid}
    except Exception as e:
        logger.error("TTS generation failed: %s", e)
        raise HTTPException(status_code=500, detail="TTS generation failed")


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str) -> dict:
    return app.state.orchestrator.get_session_status(session_id)


@app.get("/api/session/{session_id}/detail")
async def session_detail(session_id: str) -> dict:
    detail = _get_db().get_session_detail(session_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail


@app.post("/api/ai-reply")
async def ai_reply(payload: AiReplyRequest) -> dict:
    result = await app.state.orchestrator.handle_ai_reply(payload)
    # Broadcast the reply to any WebSocket listeners on the session
    reply_text = result.get("reply", payload.message)
    asyncio.create_task(
        ws_manager.broadcast(payload.session_id, {
            "type": "ai_reply" if not payload.owner else "owner_reply",
            "message": reply_text,
            "sessionId": payload.session_id,
        })
    )
    return result


@app.post("/api/owner-reply")
async def owner_reply(payload: AiReplyRequest) -> dict:
    """Owner sends a reply to a visitor session."""
    result = await app.state.orchestrator.handle_ai_reply(payload)
    asyncio.create_task(
        ws_manager.broadcast(payload.session_id, {
            "type": "owner_reply",
            "message": payload.message,
            "sessionId": payload.session_id,
        })
    )
    return result


@app.get("/api/logs")
async def logs(limit: int = 50) -> dict:
    return app.state.orchestrator.get_logs(limit=limit)


# ══════════════════════════════════════════════════════════════
# WebSocket — real-time session updates
# ══════════════════════════════════════════════════════════════

@app.websocket("/api/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    """WebSocket for real-time updates.

    Channels:
      - 'owner' — owner dashboard gets notified of new rings
      - '{session_id}' — specific session updates (status changes, owner replies)
    """
    await ws_manager.connect(channel, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle incoming messages if needed
            pass
    except WebSocketDisconnect:
        ws_manager.disconnect(channel, websocket)

