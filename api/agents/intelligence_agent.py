from __future__ import annotations

import asyncio
import importlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ..models import IntelligenceOutput, PerceptionOutput
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword sets for fast rule-based intent classification
# ---------------------------------------------------------------------------
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "delivery": [
        "package", "delivery", "courier", "amazon", "parcel",
        "ups", "fedex", "flipkart", "post", "mail", "dhl",
    ],
    "help": [
        "help", "emergency", "urgent", "accident", "fire",
        "ambulance", "police",
    ],
    "visitor": [
        "owner", "speak", "talk", "friend", "family",
        "appointment", "meeting", "visit",
    ],
}

# Dangerous keywords that force escalation regardless of risk score
_DANGEROUS_KEYWORDS: list[str] = [
    "unlock", "let me in", "open the door", "break", "weapon",
]


class IntelligenceAgent(BaseAgent):
    """Reasoning and risk-assessment layer with optional Groq LLM integration."""

    def __init__(self) -> None:
        super().__init__("api/instructions/intelligence.md")
        self._groq_client = self._init_groq_client()
        self._system_prompt = self._load_system_prompt()

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _init_groq_client(self):
        """Initialize the Groq client if the API key is available."""
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "GROQ_API_KEY not set. LLM reply generation disabled — "
                "falling back to canned rule-based replies."
            )
            return None
        try:
            groq_mod = importlib.import_module("groq")
            client = groq_mod.Groq(api_key=api_key)
            logger.info("Groq client initialized successfully")
            return client
        except Exception as exc:
            logger.warning("Failed to initialise Groq client: %s", exc)
            return None

    def _load_system_prompt(self) -> str:
        """Load the Groq system prompt from disk."""
        prompt_path = Path("api/prompts/groq_system_prompt.txt")
        if prompt_path.exists():
            text = prompt_path.read_text(encoding="utf-8").strip()
            logger.info("Loaded Groq system prompt (%d chars)", len(text))
            return text
        logger.warning("System prompt file missing at %s — using built-in fallback", prompt_path)
        return (
            "You are a smart doorbell assistant. Respond in one short polite sentence. "
            "Never instruct the visitor to open or enter. Never reveal personal info."
        )

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------

    async def process(self, perception: PerceptionOutput) -> IntelligenceOutput:
        transcript_lower = perception.transcript.lower()
        intent = self._classify_intent(transcript_lower)

        # --- Step 1: compute risk score ---
        emotion_score = self._emotion_weight(perception.emotion)
        base_risk = (
            0.5 * (1 - perception.vision_confidence)
            + 0.3 * perception.anti_spoof_score
            + 0.2 * emotion_score
        )

        # Weapon override
        if perception.weapon_detected:
            base_risk = max(base_risk, 0.75)

        # Dangerous keyword override
        if any(kw in transcript_lower for kw in _DANGEROUS_KEYWORDS):
            base_risk = max(base_risk, 0.7)

        base_risk = round(min(max(base_risk, 0.0), 1.0), 3)

        # --- Step 2: escalation decision ---
        escalation_required = (
            base_risk >= 0.7
            or perception.weapon_detected
            or perception.anti_spoof_score >= 0.6
        )

        # --- Step 3: reply generation ---
        if escalation_required:
            reply = "I have notified the owner and the security guard."
        else:
            reply = await self._generate_reply(intent, perception, transcript_lower)

        # Build tags
        tags = [intent]
        if perception.weapon_detected:
            tags.append("weapon")
        if escalation_required:
            tags.append("escalated")

        logger.info(
            "Intelligence result [%s]: intent=%s risk=%.3f escalation=%s reply='%s'",
            perception.session_id, intent, base_risk, escalation_required,
            reply[:60],
        )

        return IntelligenceOutput(
            session_id=perception.session_id,
            intent=intent,
            reply_text=reply,
            risk_score=base_risk,
            escalation_required=escalation_required,
            tags=tags,
            timestamp=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Intent classification (rule-based, zero-latency)
    # ------------------------------------------------------------------

    def _classify_intent(self, transcript: str) -> str:
        for intent, keywords in _INTENT_KEYWORDS.items():
            if any(kw in transcript for kw in keywords):
                return intent
        return "unknown"

    # ------------------------------------------------------------------
    # Emotion → numeric weight
    # ------------------------------------------------------------------

    @staticmethod
    def _emotion_weight(emotion: str) -> float:
        return {"aggressive": 0.6, "distressed": 0.4, "concerned": 0.3, "neutral": 0.2}.get(
            emotion.lower(), 0.2
        )

    # ------------------------------------------------------------------
    # Reply generation (Groq LLM with canned fallback)
    # ------------------------------------------------------------------

    async def _generate_reply(
        self, intent: str, perception: PerceptionOutput, transcript_lower: str
    ) -> str:
        """Generate visitor reply — tries Groq LLM first, falls back to canned."""

        # For high-confidence known intents, use fast canned replies (no API cost)
        # BUT: if transcript is longer/conversational, use LLM for a contextual reply
        canned = self._canned_reply(intent)
        transcript_words = len(transcript_lower.split())
        use_llm = self._groq_client and transcript_words > 4

        if not use_llm:
            return canned

        # Build a compact context for the LLM
        try:
            reply = await asyncio.wait_for(
                asyncio.to_thread(self._call_groq, perception), timeout=8
            )
            if reply:
                return reply
        except asyncio.TimeoutError:
            logger.warning("Groq API timed out — using canned reply")
        except Exception as exc:
            logger.warning("Groq API call failed: %s — using canned reply", exc)

        return canned

    def _call_groq(self, perception: PerceptionOutput) -> str:
        """Synchronous Groq API call with retry (runs in a thread)."""
        context = self._build_llm_context(perception)

        max_retries = 2
        backoff = 0.5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = self._groq_client.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    messages=[
                        {"role": "system", "content": self._system_prompt},
                        {"role": "user", "content": context},
                    ],
                    max_tokens=128,
                    temperature=0.2,
                )
                text = response.choices[0].message.content.strip()
                if text:
                    logger.info("Groq reply (attempt %d): %s", attempt + 1, text[:80])
                    return text
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Groq attempt %d/%d failed: %s", attempt + 1, max_retries + 1, exc
                )
                if attempt < max_retries:
                    import time
                    time.sleep(backoff)
                    backoff *= 2

        logger.error("All Groq retries exhausted. Last error: %s", last_error)
        return ""

    @staticmethod
    def _build_llm_context(perception: PerceptionOutput) -> str:
        """Build a compact context string for the Groq LLM prompt."""
        objects_str = ", ".join(
            f"{o.label} ({o.conf:.0%})" for o in perception.objects[:5]
        )
        return (
            f"Detected objects: {objects_str or 'none'}\n"
            f"Visitor said: \"{perception.transcript or '(silence)'}\"\n"
            f"Emotion: {perception.emotion}\n"
            f"Risk level: {'HIGH' if perception.weapon_detected else 'normal'}\n"
            f"Weapon detected: {'YES — ' + ', '.join(perception.weapon_labels) if perception.weapon_detected else 'No'}"
        )

    @staticmethod
    def _canned_reply(intent: str) -> str:
        """Fast canned replies keyed by classified intent."""
        return {
            "delivery": "Please leave the package at the doorstep. Thank you.",
            "help": "I'm alerting the owner right away. Please stay safe.",
            "visitor": "Please wait while I notify the owner.",
            "unknown": "Please wait while I notify the owner.",
        }.get(intent, "Please wait while I notify the owner.")
