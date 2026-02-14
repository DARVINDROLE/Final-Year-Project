from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agents.action_agent import ActionAgent
from .agents.decision_agent import DecisionAgent
from .agents.intelligence_agent import IntelligenceAgent
from .agents.perception_agent import PerceptionAgent
from .db import Database
from .models import (
    ActionRequest,
    AiReplyRequest,
    PerceptionOutput,
    RingEvent,
)


logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """Generate a unique session ID for visitor tracking."""
    return f"visitor_{uuid4().hex[:8]}"


class Orchestrator:
    def __init__(self, db_path: str = "data/db.sqlite") -> None:
        self.db = Database(db_path)
        self.session_queues: dict[str, asyncio.Queue] = {}
        self.session_tasks: dict[str, asyncio.Task] = {}
        self.max_concurrent_sessions = 2
        self._session_semaphore = asyncio.Semaphore(self.max_concurrent_sessions)

        self.perception_agent = PerceptionAgent()
        self.intelligence_agent = IntelligenceAgent()
        self.decision_agent = DecisionAgent()
        self.action_agent = ActionAgent(db=self.db)

    def initialize(self) -> None:
        self.db.initialize()

    async def handle_ring(self, event: RingEvent) -> dict:
        # Generate session ID if not provided
        session_id = event.session_id if event.session_id else generate_session_id()
        created_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"Processing ring event for session {session_id} (device: {event.device_id})")

        image_path = ""
        audio_path = ""
        if event.image_base64 and event.image_base64.strip():
            image_path = await self._save_image(session_id, event.image_base64)
        if event.audio_base64 and event.audio_base64.strip():
            audio_path = await self._save_audio(session_id, event.audio_base64)

        self.db.create_session(
            session_id=session_id,
            created_at=created_at,
            device_id=event.device_id,
            status="queued",
        )

        event_data = event.model_dump()
        event_data["session_id"] = session_id
        event_data["image_path"] = image_path or None
        event_data["audio_path"] = audio_path or None
        enriched_event = RingEvent(**event_data)

        session_queue = self.session_queues.setdefault(session_id, asyncio.Queue(maxsize=4))
        await session_queue.put(enriched_event)
        self.db.add_action(
            session_id=session_id,
            action_type="ring_received",
            payload={"device_id": event.device_id},
            status="queued",
            short_reason="Ring event queued",
            agent_name="orchestrator",
        )

        if session_id not in self.session_tasks or self.session_tasks[session_id].done():
            self.session_tasks[session_id] = asyncio.create_task(self.handle_session(session_id))

        return {
            "sessionId": session_id,
            "status": "queued",
            "imagePath": image_path,
            "audioPath": audio_path,
        }

    async def handle_session(self, session_id: str) -> None:
        queue = self.session_queues.get(session_id)
        if queue is None:
            return

        async with self._session_semaphore:
            try:
                self.db.update_session(session_id, "processing")
                ring_event: RingEvent = await asyncio.wait_for(queue.get(), timeout=2)

                perception = await asyncio.wait_for(
                    self.perception_agent.process(ring_event), timeout=10
                )
                self.db.update_session(session_id, "perception_done")
                self._persist_perception(perception)

                intelligence = await asyncio.wait_for(
                    self.intelligence_agent.process(perception), timeout=10
                )
                self.db.update_session(
                    session_id, "intelligence_done", risk_score=float(intelligence.risk_score)
                )
                self.db.add_transcript(
                    session_id=session_id,
                    role="assistant",
                    content=intelligence.reply_text,
                    timestamp=intelligence.timestamp.isoformat(),
                )

                decision = await asyncio.wait_for(
                    self.decision_agent.process(
                        intelligence,
                        weapon_detected=perception.weapon_detected,
                        anti_spoof_score=perception.anti_spoof_score,
                    ),
                    timeout=5,
                )
                self.db.update_session(
                    session_id, "decision_done", risk_score=float(intelligence.risk_score)
                )

                action_request = ActionRequest(
                    session_id=session_id,
                    tts_text=intelligence.reply_text,
                    image_path=perception.image_path,
                    notify_payload={"priority": "high" if decision.final_action == "escalate" else "normal"},
                    timestamp=datetime.now(timezone.utc),
                )
                action_result = await asyncio.wait_for(
                    self.action_agent.handle(
                        decision_output=decision,
                        intelligence_output=intelligence,
                        perception_output=perception,
                        action_request=action_request,
                    ),
                    timeout=8,
                )

                self.db.add_action(
                    session_id=session_id,
                    action_type=decision.final_action,
                    payload=action_result.model_dump(),
                    status="done",
                    short_reason=decision.reason,
                    agent_name="action_agent",
                )
                self.db.update_session(
                    session_id, "completed", risk_score=float(intelligence.risk_score)
                )
            except Exception as exc:
                self._log_agent_error(session_id, exc)
                self.db.update_session(session_id, "error")

    def get_session_status(self, session_id: str) -> dict:
        session = self.db.get_session(session_id)
        if not session:
            return {"sessionId": session_id, "status": "not_found"}
        return {
            "sessionId": session_id,
            "status": session["status"],
            "lastUpdated": session["last_updated"],
            "riskScore": session["risk_score"],
        }

    async def handle_ai_reply(self, payload: AiReplyRequest) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        self.db.add_transcript(
            session_id=payload.session_id,
            role="owner" if payload.owner else "assistant",
            content=payload.message,
            timestamp=timestamp,
        )

        action_status = "logged"
        if payload.dispatch_action:
            self.db.add_action(
                session_id=payload.session_id,
                action_type="manual_reply",
                payload={"message": payload.message},
                status="pending",
                short_reason="Owner manual override",
                agent_name="orchestrator",
                timestamp=timestamp,
            )
            action_status = "queued"

        return {
            "sessionId": payload.session_id,
            "status": action_status,
            "timestamp": timestamp,
        }

    def get_logs(self, limit: int = 50) -> dict:
        return self.db.get_recent_logs(limit=limit)

    async def _save_image(self, session_id: str, image_base64: str) -> str:
        snaps_dir = Path("data/snaps")
        snaps_dir.mkdir(parents=True, exist_ok=True)
        image_path = snaps_dir / f"{session_id}.jpg"
        try:
            image_bytes = base64.b64decode(image_base64.strip())
        except Exception as e:
            raise ValueError(f"Invalid base64 image data: {e}")
        await asyncio.to_thread(image_path.write_bytes, image_bytes)
        return str(image_path).replace("\\", "/")

    async def _save_audio(self, session_id: str, audio_base64: str) -> str:
        audio_dir = Path("data/tmp") / session_id
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / "ring_audio.wav"
        try:
            audio_bytes = base64.b64decode(audio_base64.strip())
        except Exception as e:
            raise ValueError(f"Invalid base64 audio data: {e}")
        await asyncio.to_thread(audio_path.write_bytes, audio_bytes)
        return str(audio_path).replace("\\", "/")

    def _persist_perception(self, perception: PerceptionOutput) -> None:
        if perception.transcript:
            self.db.add_transcript(
                session_id=perception.session_id,
                role="visitor",
                content=perception.transcript,
                timestamp=perception.timestamp.isoformat(),
            )

        self.db.upsert_visitor(
            session_id=perception.session_id,
            image_path=perception.image_path,
            visitor_type="unknown",
            ai_summary=f"emotion={perception.emotion}",
        )

        self.db.add_action(
            session_id=perception.session_id,
            action_type="perception",
            payload={
                "person_detected": perception.person_detected,
                "vision_confidence": perception.vision_confidence,
                "objects": [obj.model_dump() for obj in perception.objects],
                "weapon_detected": perception.weapon_detected,
                "weapon_confidence": perception.weapon_confidence,
            },
            status="done",
            short_reason="Perception complete",
            agent_name="perception_agent",
        )

    def _log_agent_error(self, session_id: str, exc: Exception) -> None:
        logs_path = Path("data/logs")
        logs_path.mkdir(parents=True, exist_ok=True)
        error_file = logs_path / "agent_errors.log"
        payload = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }
        with error_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        logger.exception("Agent pipeline failed for session %s", session_id)
