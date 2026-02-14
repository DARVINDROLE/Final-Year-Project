from __future__ import annotations

from datetime import datetime, timezone

from ..models import IntelligenceOutput, PerceptionOutput
from .base_agent import BaseAgent


class IntelligenceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("api/instructions/intelligence.md")

    async def process(self, perception: PerceptionOutput) -> IntelligenceOutput:
        transcript = perception.transcript.lower()
        intent = self._classify_intent(transcript)

        emotion_score = 0.6 if perception.emotion == "aggressive" else 0.2
        base_risk = 0.5 * (1 - perception.vision_confidence) + 0.3 * perception.anti_spoof_score + 0.2 * emotion_score

        if perception.weapon_detected:
            base_risk = max(base_risk, 0.75)

        escalation_required = base_risk >= 0.7 or perception.weapon_detected
        if escalation_required:
            reply = "I have notified the owner and the security guard."
        elif intent == "delivery":
            reply = "Please leave the package at the doorstep."
        else:
            reply = "Please wait while I notify the owner."

        return IntelligenceOutput(
            session_id=perception.session_id,
            intent=intent,
            reply_text=reply,
            risk_score=round(base_risk, 3),
            escalation_required=escalation_required,
            tags=[intent],
            timestamp=datetime.now(timezone.utc),
        )

    def _classify_intent(self, transcript: str) -> str:
        if any(keyword in transcript for keyword in ["package", "delivery", "courier", "amazon"]):
            return "delivery"
        if any(keyword in transcript for keyword in ["help", "emergency"]):
            return "help"
        if any(keyword in transcript for keyword in ["owner", "speak", "talk"]):
            return "visitor"
        return "unknown"
