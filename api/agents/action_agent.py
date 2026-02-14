from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..db import Database
from ..models import ActionRequest, ActionResult, DecisionOutput, IntelligenceOutput, PerceptionOutput
from .base_agent import BaseAgent


class ActionAgent(BaseAgent):
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
        tts_text = self._sanitize_tts_text(action_request.tts_text)

        if decision_output.final_action == "auto_reply":
            tts_path = self._write_tts_preview(action_request.session_id, tts_text)
            return ActionResult(
                session_id=action_request.session_id,
                status="played",
                action_type="auto_reply",
                payload={"tts_file": tts_path},
                timestamp=datetime.now(timezone.utc),
            )

        if decision_output.final_action in {"notify_owner", "escalate"}:
            return ActionResult(
                session_id=action_request.session_id,
                status="queued",
                action_type=decision_output.final_action,
                payload={
                    "message": intelligence_output.reply_text,
                    "risk_score": intelligence_output.risk_score,
                    "image_path": perception_output.image_path,
                },
                timestamp=datetime.now(timezone.utc),
            )

        return ActionResult(
            session_id=action_request.session_id,
            status="ignored",
            action_type=decision_output.final_action,
            payload={},
            timestamp=datetime.now(timezone.utc),
        )

    def _sanitize_tts_text(self, text: str) -> str:
        safe = "".join(ch for ch in text if ch.isprintable())
        safe = safe.replace('"', "'")
        return safe[:240]

    def _write_tts_preview(self, session_id: str, text: str) -> str:
        tts_dir = Path("data/tts")
        tts_dir.mkdir(parents=True, exist_ok=True)
        tts_file = tts_dir / f"{session_id}.txt"
        tts_file.write_text(text, encoding="utf-8")
        return str(tts_file).replace("\\", "/")
