from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..db import Database
from ..models import ActionRequest, ActionResult, DecisionOutput, IntelligenceOutput, PerceptionOutput
from ..utils.tts import generate_tts_audio, sanitize_tts_text
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ActionAgent(BaseAgent):
    """Phase 5 Action Agent — executes decisions via TTS, notifications, and logging.

    Responsibilities:
      - auto_reply:    Generate TTS audio file and play locally (via utils/tts.py)
      - notify_owner:  Create action row in DB with notification payload for frontend
      - escalate:      Alert owner + watchman, create high-priority action rows
      - All actions:   Log to SQLite actions table with full audit trail
    """

    def __init__(self, db: Database) -> None:
        super().__init__("api/instructions/action.md")
        self.db = db

    async def handle(
        self,
        decision_output: DecisionOutput,
        intelligence_output: IntelligenceOutput,
        perception_output: PerceptionOutput,
        action_request: ActionRequest,
    ) -> ActionResult:
        tts_text = sanitize_tts_text(action_request.tts_text)
        session_id = action_request.session_id
        action = decision_output.final_action
        dispatch = decision_output.dispatch

        logger.info(
            "Action [%s]: executing action=%s tts=%s notify=%s",
            session_id, action,
            dispatch.get("tts", False),
            dispatch.get("notify_owner", False),
        )

        # ── auto_reply: generate TTS and respond to visitor ──
        if action == "auto_reply":
            tts_path = await self._generate_tts(session_id, tts_text)
            self._log_action_to_db(
                session_id, "auto_reply", "done",
                reason=decision_output.reason,
                payload={
                    "tts_file": tts_path,
                    "reply_text": tts_text,
                },
            )
            return ActionResult(
                session_id=session_id,
                status="played",
                action_type="auto_reply",
                payload={"tts_file": tts_path, "reply_text": tts_text},
                timestamp=datetime.now(timezone.utc),
            )

        # ── escalate: highest priority — TTS + owner + watchman ──
        if action == "escalate":
            tts_path = ""
            if dispatch.get("tts", True):
                tts_path = await self._generate_tts(session_id, tts_text)

            notification = self._build_notification(
                session_id=session_id,
                intelligence=intelligence_output,
                perception=perception_output,
                priority="critical",
                recipients=self._escalation_recipients(dispatch),
            )

            # Log escalation notification for frontend/admin
            self._log_action_to_db(
                session_id, "escalation_notification", "pending",
                reason=decision_output.reason,
                payload=notification,
            )

            return ActionResult(
                session_id=session_id,
                status="escalated",
                action_type="escalate",
                payload={
                    "tts_file": tts_path,
                    "notification": notification,
                    "reply_text": tts_text,
                },
                timestamp=datetime.now(timezone.utc),
            )

        # ── notify_owner: medium priority — queue notification ──
        if action == "notify_owner":
            tts_path = ""
            if dispatch.get("tts", False):
                tts_path = await self._generate_tts(session_id, tts_text)

            notification = self._build_notification(
                session_id=session_id,
                intelligence=intelligence_output,
                perception=perception_output,
                priority="normal",
                recipients=["owner"],
            )

            self._log_action_to_db(
                session_id, "owner_notification", "pending",
                reason=decision_output.reason,
                payload=notification,
            )

            return ActionResult(
                session_id=session_id,
                status="queued",
                action_type="notify_owner",
                payload={
                    "tts_file": tts_path,
                    "notification": notification,
                    "reply_text": tts_text,
                },
                timestamp=datetime.now(timezone.utc),
            )

        # ── ignore or unknown action ──
        logger.info("Action [%s]: action '%s' ignored/no-op", session_id, action)
        self._log_action_to_db(
            session_id, action, "ignored",
            reason=decision_output.reason,
            payload={},
        )
        return ActionResult(
            session_id=session_id,
            status="ignored",
            action_type=action,
            payload={},
            timestamp=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # TTS generation (delegated to utils/tts.py)
    # ------------------------------------------------------------------

    async def _generate_tts(self, session_id: str, text: str) -> str:
        """Generate TTS audio file in a worker thread to avoid blocking."""
        if not text:
            return ""
        try:
            path = await asyncio.to_thread(
                generate_tts_audio,
                text=text,
                session_id=session_id,
                output_dir="data/tts",
                play=False,  # don't play automatically in server mode
            )
            logger.info("TTS generated for %s: %s", session_id, path)
            return path
        except Exception as exc:
            logger.warning("TTS generation failed for %s: %s", session_id, exc)
            # Fallback: write text file
            return self._write_text_fallback(session_id, text)

    @staticmethod
    def _write_text_fallback(session_id: str, text: str) -> str:
        """Write text-only TTS preview file as a last resort."""
        tts_dir = Path("data/tts")
        tts_dir.mkdir(parents=True, exist_ok=True)
        tts_file = tts_dir / f"{session_id}.txt"
        tts_file.write_text(text, encoding="utf-8")
        return str(tts_file).replace("\\", "/")

    # ------------------------------------------------------------------
    # Notification builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_notification(
        session_id: str,
        intelligence: IntelligenceOutput,
        perception: PerceptionOutput,
        priority: str = "normal",
        recipients: list[str] | None = None,
    ) -> dict:
        """Build a structured notification payload for the frontend/admin UI."""
        return {
            "session_id": session_id,
            "priority": priority,
            "recipients": recipients or ["owner"],
            "message": intelligence.reply_text,
            "intent": intelligence.intent,
            "risk_score": intelligence.risk_score,
            "escalation_required": intelligence.escalation_required,
            "tags": intelligence.tags,
            "image_path": perception.image_path,
            "weapon_detected": perception.weapon_detected,
            "emotion": perception.emotion,
            "transcript": perception.transcript,
            "num_persons": getattr(perception, "num_persons", 0),
            "context_flags": getattr(perception, "context_flags", []),
        }

    @staticmethod
    def _escalation_recipients(dispatch: dict) -> list[str]:
        """Determine escalation recipients from dispatch flags."""
        recipients = []
        if dispatch.get("notify_owner", True):
            recipients.append("owner")
        if dispatch.get("notify_watchman", False):
            recipients.append("watchman")
        return recipients or ["owner"]

    # ------------------------------------------------------------------
    # DB logging
    # ------------------------------------------------------------------

    def _log_action_to_db(
        self,
        session_id: str,
        action_type: str,
        status: str,
        reason: str = "",
        payload: dict | None = None,
    ) -> None:
        """Write an action row to the actions table for audit trail."""
        try:
            self.db.add_action(
                session_id=session_id,
                action_type=action_type,
                payload=payload or {},
                status=status,
                short_reason=reason[:200],
                agent_name="action_agent",
            )
        except Exception as exc:
            logger.error("Failed to log action to DB for %s: %s", session_id, exc)
