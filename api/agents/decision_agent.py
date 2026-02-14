from __future__ import annotations

from datetime import datetime, timezone

from ..models import DecisionOutput, IntelligenceOutput
from .base_agent import BaseAgent


class DecisionAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("api/instructions/decision.md")

    async def process(self, intelligence: IntelligenceOutput) -> DecisionOutput:
        if intelligence.escalation_required or intelligence.risk_score >= 0.7:
            return DecisionOutput(
                session_id=intelligence.session_id,
                final_action="escalate",
                reason="risk >= threshold or escalation flag",
                dispatch={"tts": True, "notify_owner": True},
                timestamp=datetime.now(timezone.utc),
            )

        if intelligence.risk_score < 0.4:
            return DecisionOutput(
                session_id=intelligence.session_id,
                final_action="auto_reply",
                reason="risk < threshold",
                dispatch={"tts": True, "notify_owner": False},
                timestamp=datetime.now(timezone.utc),
            )

        return DecisionOutput(
            session_id=intelligence.session_id,
            final_action="notify_owner",
            reason="default medium-risk handling",
            dispatch={"tts": False, "notify_owner": True},
            timestamp=datetime.now(timezone.utc),
        )
