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
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents.intelligence_agent import IntelligenceAgent
from .models import AiReplyRequest, ObjectDetection, PerceptionOutput, RingEvent
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
    # Start background inactivity checker
    asyncio.create_task(_inactivity_checker_loop())


async def _inactivity_checker_loop() -> None:
    """Background loop that auto-ends sessions when no person is visible in the
    camera feed for NO_PERSON_TIMEOUT seconds. This handles cases like a
    delivery person leaving after dropping a package."""
    while True:
        try:
            await asyncio.sleep(INACTIVITY_CHECK_INTERVAL)
            now = datetime.now(timezone.utc).timestamp()
            ended_sessions: list[str] = []

            for sid in list(_active_sessions):
                last_seen = _last_person_seen.get(sid, 0.0)
                # Only trigger if we have a valid timestamp and the timeout elapsed
                if last_seen > 0 and (now - last_seen) >= NO_PERSON_TIMEOUT:
                    ended_sessions.append(sid)

            for sid in ended_sessions:
                logger.info(
                    "Auto-ending session %s (no person visible for %.0fs)",
                    sid, NO_PERSON_TIMEOUT,
                )
                _active_sessions.discard(sid)

                # Update DB status to completed
                try:
                    _get_db().update_session(sid, "completed")
                except Exception:
                    pass

                # Add a transcript entry so the conversation log shows it
                try:
                    _get_db().add_transcript(
                        session_id=sid,
                        role="assistant",
                        content="Session ended automatically due to visitor inactivity.",
                    )
                except Exception:
                    pass

                # Notify owner dashboard
                await ws_manager.broadcast("owner", {
                    "type": "session_ended",
                    "sessionId": sid,
                    "reason": "inactivity",
                })
                # Notify the visitor's doorbell page
                await ws_manager.broadcast(sid, {
                    "type": "session_ended",
                    "reason": "inactivity",
                    "message": "Thank you! The session has ended due to inactivity. Have a great day!",
                })

                # Clean up frame data
                _session_frames.pop(sid, None)
                _frame_timestamps.pop(sid, None)
                _last_person_seen.pop(sid, None)
                _last_person_scan.pop(sid, None)
                _last_weapon_scan.pop(sid, None)
                _weapon_alert_sent.pop(sid, None)
                _weapon_hit_streak.pop(sid, None)
                _person_hit_streak.pop(sid, None)
                _last_person_alert.pop(sid, None)

        except Exception as exc:
            logger.error("Inactivity checker error: %s", exc)


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
# Owner settings (Vacation Mode and friends)
# ══════════════════════════════════════════════════════════════

class OwnerSettingsUpdate(BaseModel):
    vacation_mode: Optional[bool] = None


@app.get("/api/owner/settings")
async def get_owner_settings(authorization: Optional[str] = Header(None)) -> dict:
    owner = _require_auth(authorization)
    return _get_db().get_owner_settings(owner["id"])


@app.put("/api/owner/settings")
async def update_owner_settings(
    req: OwnerSettingsUpdate, authorization: Optional[str] = Header(None)
) -> dict:
    owner = _require_auth(authorization)
    db = _get_db()
    if req.vacation_mode is not None:
        db.set_owner_setting(owner["id"], "vacation_mode", req.vacation_mode)
        try:
            db.add_action(
                session_id="",
                action_type="owner_setting_changed",
                payload={"key": "vacation_mode", "value": bool(req.vacation_mode)},
                status="done",
                short_reason=f"vacation_mode={'on' if req.vacation_mode else 'off'}",
                agent_name="owner",
            )
        except Exception:
            pass
    return db.get_owner_settings(owner["id"])


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
    reply_text = result.get("reply", payload.message)
    event_type = "ai_reply" if not payload.owner else "owner_reply"
    session_payload = {
        "type": event_type,
        "message": reply_text,
        "sessionId": payload.session_id,
    }
    # Tell the visitor's session channel so the doorbell page can render the reply.
    asyncio.create_task(ws_manager.broadcast(payload.session_id, session_payload))
    # Also poke the owner channel so the dashboard refreshes its visitor card —
    # otherwise the owner only sees the AI's first reply until they manually refresh.
    asyncio.create_task(
        ws_manager.broadcast("owner", {
            "type": "transcript_updated",
            "sessionId": payload.session_id,
            "role": "owner" if payload.owner else "visitor",
            "message": payload.message,
            "reply": reply_text,
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
    asyncio.create_task(
        ws_manager.broadcast("owner", {
            "type": "transcript_updated",
            "sessionId": payload.session_id,
            "role": "owner",
            "message": payload.message,
        })
    )
    return result


@app.get("/api/logs")
async def logs(limit: int = 50) -> dict:
    return app.state.orchestrator.get_logs(limit=limit)


# ══════════════════════════════════════════════════════════════
# Streaming — continuous video frames + live weapon detection
# ══════════════════════════════════════════════════════════════

# Store latest frame per session for MJPEG streaming
_session_frames: dict[str, bytes] = {}
_frame_timestamps: dict[str, float] = {}

# ── Inactivity auto-end (person-absence based) ─────────────────
NO_PERSON_TIMEOUT = 20.0         # seconds with no person visible → auto-end
INACTIVITY_CHECK_INTERVAL = 5.0  # how often the background loop runs
PERSON_DETECT_INTERVAL = 2.0     # seconds between person-presence scans
_active_sessions: set[str] = set()          # sessions currently streaming frames
_last_person_seen: dict[str, float] = {}    # last time a person was detected per session
_last_person_scan: dict[str, float] = {}    # rate-limiter for person detection

# Rate-limit weapon detection: run at most once per WEAPON_DETECT_INTERVAL seconds.
# OpenThreatDetection (YOLOv4 SavedModel @ 608x608) on CPU is ~1-2s/frame on
# Apple Silicon, so we space scans further apart than the legacy YOLOv8 model.
WEAPON_DETECT_INTERVAL = 1.5   # seconds — scan ~once every 1.5 s
WEAPON_DETECT_TIMEOUT = 8      # seconds — max time for a single TF inference
WEAPON_CONF_THRESHOLD = 0.35   # tuned for OpenThreatDetection (upstream default 0.30)
WEAPON_CONSECUTIVE_HITS = 2    # require N consecutive positive frames before alerting
_last_weapon_scan: dict[str, float] = {}
_weapon_alert_sent: dict[str, bool] = {}  # avoid spamming alerts
_weapon_hit_streak: dict[str, int] = {}   # consecutive positive detections per session

# ── Vacation Mode person-alert state ───────────────────────
PERSON_ALERT_CONSECUTIVE_HITS = 2   # match weapon-alert hysteresis
PERSON_ALERT_COOLDOWN = 30.0        # seconds between vacation alerts per session
_person_hit_streak: dict[str, int] = {}
_last_person_alert: dict[str, float] = {}


def _decode_frame_to_numpy(frame_bytes: bytes):
    """Decode JPEG bytes to a numpy array (BGR). Shared by weapon & person detection."""
    import numpy as np
    img_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    try:
        import cv2
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except ImportError:
        from PIL import Image
        import io
        return np.array(Image.open(io.BytesIO(frame_bytes)).convert("RGB"))


def _run_person_detection_on_frame(frame_bytes: bytes) -> bool:
    """Run the general YOLOv8n model to check if a person is visible.
    Returns True if at least one person is detected with conf >= 0.40."""
    perception = app.state.orchestrator.perception_agent
    if perception.vision_model is None:
        return True  # if no model loaded, assume person present (safe default)

    try:
        img = _decode_frame_to_numpy(frame_bytes)
        if img is None:
            return True

        results = perception.vision_model.predict(
            source=img,
            imgsz=416,
            conf=0.40,
            classes=[0],   # class 0 = person in COCO
            device="cpu",
            half=False,
            verbose=False,
        )
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is not None and len(boxes.conf) > 0:
                return True
        return False
    except Exception as exc:
        logger.debug("Person detection on frame failed: %s", exc)
        return True  # assume present on error (don't accidentally end session)


def _run_weapon_detection_on_frame(frame_bytes: bytes) -> dict:
    """Run the perception agent's OpenThreatDetector on raw JPEG bytes.
    Decodes in-memory (no disk I/O) and delegates to the adapter.
    Returns {weapon_detected, weapon_confidence, weapon_labels}."""
    perception = app.state.orchestrator.perception_agent
    detector = perception.weapon_model
    if detector is None:
        return {"weapon_detected": False, "weapon_confidence": 0.0, "weapon_labels": []}
    img = _decode_frame_to_numpy(frame_bytes)
    if img is None:
        return {"weapon_detected": False, "weapon_confidence": 0.0, "weapon_labels": []}
    return detector.detect_from_array(img, conf=WEAPON_CONF_THRESHOLD)


def _is_owner_on_vacation() -> bool:
    """Single-household owner lookup. Returns False if no owner is registered."""
    try:
        owner = app.state.orchestrator.db.get_default_owner()
        return bool(owner and owner.get("vacation_mode"))
    except Exception:
        return False


async def _emit_vacation_person_alert(
    session_id: str,
    frame_data: bytes,
    weapon_result: dict | None,
    now: float,
) -> None:
    """Persist a snapshot, build a one-line description, broadcast to the owner
    channel, and log an action row. Failures are swallowed — the alert is
    best-effort and must never break the streaming endpoint."""
    timestamp = datetime.now(timezone.utc).isoformat()
    snaps_dir = Path("data/snaps")
    snaps_dir.mkdir(parents=True, exist_ok=True)
    image_filename = f"{session_id}_vacation_{int(now)}.jpg"
    image_path = snaps_dir / image_filename
    try:
        image_path.write_bytes(frame_data)
    except Exception as exc:
        logger.debug("Vacation alert: failed to persist frame: %s", exc)

    weapon_detected = bool(weapon_result and weapon_result.get("weapon_detected"))
    weapon_labels = list(weapon_result.get("weapon_labels", [])) if weapon_result else []
    objects: list[ObjectDetection] = [ObjectDetection(label=lbl, conf=1.0) for lbl in weapon_labels]

    perception_stub = PerceptionOutput(
        session_id=session_id,
        person_detected=True,
        objects=objects,
        weapon_detected=weapon_detected,
        weapon_labels=weapon_labels,
        num_persons=1,
        face_visible=True,
        emotion="neutral",
    )
    description = IntelligenceAgent.summarise_perception(perception_stub)

    payload = {
        "type": "person_detected",
        "sessionId": session_id,
        "imageUrl": f"/static/snaps/{image_filename}",
        "description": description,
        "timestamp": timestamp,
        "weapon_detected": weapon_detected,
        "num_persons": 1,
    }
    try:
        await ws_manager.broadcast("owner", payload)
        await ws_manager.broadcast(session_id, payload)
    except Exception as exc:
        logger.debug("Vacation alert: broadcast failed: %s", exc)

    try:
        app.state.orchestrator.db.add_action(
            session_id=session_id,
            action_type="vacation_person_alert",
            payload={
                "image_path": str(image_path),
                "description": description,
                "weapon_detected": weapon_detected,
                "weapon_labels": weapon_labels,
            },
            status="sent",
            short_reason="Person detected during vacation mode",
            agent_name="perception_agent",
        )
    except Exception as exc:
        logger.debug("Vacation alert: DB log failed: %s", exc)


@app.post("/api/session/{session_id}/stream-frame")
async def stream_frame(session_id: str, request: Request) -> dict:
    """
    Receive a frame from the doorbell camera to stream to the owner.
    Also runs weapon detection periodically and broadcasts alerts.
    """
    try:
        body = await request.json()
        frame_base64 = body.get("frame_base64", "")

        if not frame_base64:
            raise HTTPException(status_code=400, detail="Missing frame_base64")

        # Decode and store frame
        frame_data = base64.b64decode(frame_base64)
        _session_frames[session_id] = frame_data
        now = datetime.now(timezone.utc).timestamp()
        _frame_timestamps[session_id] = now
        _active_sessions.add(session_id)  # mark as actively streaming
        # Initialise person-seen timestamp on first frame
        if session_id not in _last_person_seen:
            _last_person_seen[session_id] = now

        # ── Periodic person-presence detection ─────────────────────
        person_found_this_scan = False
        person_scan_ran = False
        last_pscan = _last_person_scan.get(session_id, 0.0)
        if (now - last_pscan) >= PERSON_DETECT_INTERVAL:
            _last_person_scan[session_id] = now
            person_scan_ran = True
            try:
                person_found_this_scan = await asyncio.wait_for(
                    asyncio.to_thread(_run_person_detection_on_frame, frame_data),
                    timeout=3,
                )
                if person_found_this_scan:
                    _last_person_seen[session_id] = now
            except Exception as exc:
                logger.debug("Person detection scan failed: %s", exc)
        # ── Periodic weapon detection on live frames ──────────────
        weapon_result = None
        last_scan = _last_weapon_scan.get(session_id, 0.0)
        if (now - last_scan) >= WEAPON_DETECT_INTERVAL:
            _last_weapon_scan[session_id] = now
            try:
                weapon_result = await asyncio.wait_for(
                    asyncio.to_thread(_run_weapon_detection_on_frame, frame_data),
                    timeout=WEAPON_DETECT_TIMEOUT,
                )
                # Visible at INFO so you can confirm the live scan is actually running
                # and see what conf/labels the model returned per frame.
                logger.info(
                    "Live weapon scan [%s]: detected=%s conf=%.3f labels=%s",
                    session_id,
                    weapon_result.get("weapon_detected"),
                    weapon_result.get("weapon_confidence", 0.0),
                    weapon_result.get("weapon_labels", []),
                )
            except Exception as exc:
                # Bumped from debug→warning so silent failures aren't swallowed.
                logger.warning("Live weapon scan failed [%s]: %s", session_id, exc)

        # Track consecutive detections to avoid false positives
        if weapon_result:
            if weapon_result.get("weapon_detected"):
                _weapon_hit_streak[session_id] = _weapon_hit_streak.get(session_id, 0) + 1
            else:
                _weapon_hit_streak[session_id] = 0  # reset on a clean frame

        # ── Vacation-mode person alert ─────────────────────────────
        # Fires once per confirmed person presence, independent of the weapon
        # alert path. Cooldown prevents spamming the owner during one visit.
        if person_scan_ran and _is_owner_on_vacation():
            if person_found_this_scan:
                _person_hit_streak[session_id] = _person_hit_streak.get(session_id, 0) + 1
            else:
                _person_hit_streak[session_id] = 0
            p_streak = _person_hit_streak.get(session_id, 0)
            last_alert = _last_person_alert.get(session_id, 0.0)
            if (
                person_found_this_scan
                and p_streak >= PERSON_ALERT_CONSECUTIVE_HITS
                and (now - last_alert) >= PERSON_ALERT_COOLDOWN
            ):
                _last_person_alert[session_id] = now
                await _emit_vacation_person_alert(session_id, frame_data, weapon_result, now)

        streak = _weapon_hit_streak.get(session_id, 0)
        # Only alert after WEAPON_CONSECUTIVE_HITS consecutive positive frames
        if weapon_result and weapon_result.get("weapon_detected") and streak >= WEAPON_CONSECUTIVE_HITS:
            labels = weapon_result.get("weapon_labels", [])
            confidence = weapon_result.get("weapon_confidence", 0.0)
            logger.warning(
                "⚠️ WEAPON DETECTED in live stream [%s]: %s (conf=%.2f, streak=%d)",
                session_id, labels, confidence, streak,
            )

            # Broadcast to owner channel
            await ws_manager.broadcast("owner", {
                "type": "weapon_alert",
                "sessionId": session_id,
                "weapon_labels": labels,
                "weapon_confidence": confidence,
                "timestamp": now,
            })

            # Also broadcast to the session channel (for any session listeners)
            await ws_manager.broadcast(session_id, {
                "type": "weapon_alert",
                "sessionId": session_id,
                "weapon_labels": labels,
                "weapon_confidence": confidence,
                "timestamp": now,
            })

            # Log to DB actions table
            try:
                app.state.orchestrator.db.add_action(
                    session_id=session_id,
                    action_type="weapon_alert",
                    payload={
                        "weapon_labels": labels,
                        "weapon_confidence": confidence,
                        "source": "live_stream",
                    },
                    status="alert_sent",
                    short_reason=f"Weapon detected in live stream: {', '.join(labels)}",
                    agent_name="perception_agent",
                )
            except Exception:
                pass

            _weapon_alert_sent[session_id] = True

        return {
            "status": "frame received",
            "sessionId": session_id,
            "weapon_detected": bool(weapon_result and weapon_result.get("weapon_detected")),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error receiving stream frame: %s", e)
        raise HTTPException(status_code=500, detail="Failed to receive frame")


@app.get("/api/stream/{session_id}")
async def stream_mjpeg(session_id: str) -> StreamingResponse:
    """
    Stream live video frames from the doorbell as MJPEG.
    Returns a stream of JPEG images with multipart/x-mixed-replace boundary.
    """
    async def frame_generator():
        while True:
            frame_data = _session_frames.get(session_id)
            if frame_data:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"\r\n" + frame_data + b"\r\n"
                )
            await asyncio.sleep(0.1)  # ~10 FPS output (frames arrive at ~5 FPS)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/stream/{session_id}/snapshot")
async def stream_snapshot(session_id: str) -> Response:
    """Return the latest JPEG frame for a session as a single image.
    Used as a polling fallback when MJPEG streaming doesn't work."""
    frame_data = _session_frames.get(session_id)
    if not frame_data:
        raise HTTPException(status_code=404, detail="No frames available for this session")
    return Response(content=frame_data, media_type="image/jpeg")


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

