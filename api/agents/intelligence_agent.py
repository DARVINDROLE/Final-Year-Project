from __future__ import annotations

import asyncio
import importlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ..models import IntelligenceOutput, PerceptionOutput
from ..utils.hindi_normalize import normalize_hindi_transcript
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword sets for fast rule-based intent classification
# Expanded for Indian household scenarios (45+ edge cases)
# ---------------------------------------------------------------------------
# IMPORTANT: Dict order = classification priority.  Dangerous / high-risk
# intents MUST appear FIRST so that a transcript containing both "delivery"
# and "otp" is classified as scam_attempt, not delivery.
# ---------------------------------------------------------------------------
_INTENT_KEYWORDS: dict[str, list[str]] = {
    # --- Highest priority: dangerous / scam / aggressive ---
    "scam_attempt": [
        "otp", "verification code", "verify karna", "code bata",
        "upi", "qr scan", "account number", "bank verification",
        "aadhaar", "kyc", "pan card", "refund dena", "refund hai",
        "lottery", "prize", "winner",
    ],
    "aggression": [
        "dekh lena", "maar", "todenge", "warna", "dhamki",
        "threat", "kill", "attack", "break", "smash",
        "goli", "chaku", "jaan se", "darwaza tod",
        "khol warna",
    ],
    "occupancy_probe": [
        "koi ghar pe", "koi hai", "anyone home", "is anyone",
        "ghar pe hai", "kaun hai ghar", "owner hai kya",
        "ghar khali", "ghar pe koi nahi",
    ],
    # --- Medium priority: claims that need owner verification ---
    "identity_claim": [
        "owner ne bola", "relative hoon", "chacha hoon", "mama hoon",
        "i know the owner", "personally jaanta", "unke bete",
        "family member", "ghar wale", "neighbour hoon",
    ],
    "entry_request": [
        "andar aana", "let me in", "open the door", "darwaza khol",
        "gate khol", "lift use", "building mein aana",
        "come inside", "enter karna",
    ],
    "government_claim": [
        "government", "sarkari", "court", "legal notice",
        "tax", "inspection", "bijli", "electricity",
        "gas", "gas leak", "water board", "meter reading",
        "census", "survey",
    ],
    "domestic_staff": [
        "kaam karungi", "kaam karta", "bai", "maid", "cook",
        "driver", "chaabi", "keys", "kaam wali", "safai",
        "purani bai", "replacement", "naya kaam",
    ],
    # --- Lower priority: benign intents ---
    "help": [
        "help", "emergency", "urgent", "accident", "fire",
        "ambulance", "police", "hospital", "bachao", "madad",
        "aag lagi", "blood", "injured", "hurt",
    ],
    "child_elderly": [
        "mummy kho gayi", "papa kho gaye", "lost", "bachcha",
        "child", "uncle", "aunty", "paani milega", "bhai sahab",
        "ghar nahi mil raha",
    ],
    "religious_donation": [
        "chanda", "donation", "mandir", "temple", "masjid",
        "church", "gurudwara", "havan", "puja", "bhagwan",
        "society collection", "ganpati", "durga",
    ],
    "sales_marketing": [
        "free demo", "offer", "discount", "deal", "insurance",
        "policy", "purifier", "water purifier", "broadband",
        "fiber", "real estate", "flat sell", "loan",
    ],
    "delivery": [
        "package", "delivery", "courier", "amazon", "parcel",
        "ups", "fedex", "flipkart", "post", "mail", "dhl",
        "swiggy", "zomato", "bigbasket", "blinkit", "dunzo",
        "meesho", "myntra", "cod", "cash on delivery",
    ],
    # --- Lowest priority: generic visitor ---
    "visitor": [
        "speak", "talk", "friend", "family",
        "appointment", "meeting", "visit", "milna hai",
    ],
}

# Dangerous keywords that force escalation regardless of risk score
_DANGEROUS_KEYWORDS: list[str] = [
    "unlock", "let me in", "open the door", "break", "weapon",
    "goli", "chaku", "bomb", "jaan se", "maar dunga",
    "todenge", "aag laga", "kill", "attack",
]

# --- Indian-context risk weight adjustments (from scenarios.md risk-weight matrix) ---
_CONTEXT_FLAG_RISK_WEIGHTS: dict[str, float] = {
    "otp_request": 0.50,
    "occupancy_probe": 0.40,
    "entry_request": 0.35,
    "claim_object_mismatch": 0.30,
    "financial_request": 0.35,
    "identity_claim": 0.25,
    "authority_claim": 0.20,
    "multi_person": 0.20,
    "staff_claim": 0.15,
    "donation_request": 0.10,
}


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
        # Normalize Devanagari → Romanized so keyword matching works with Whisper output
        normalized = normalize_hindi_transcript(perception.transcript)
        transcript_lower = normalized.lower()
        intent = self._classify_intent(transcript_lower)

        # --- Step 1: compute base risk score ---
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

        # --- Step 1b: Indian-context flag risk adjustments ---
        context_flags = getattr(perception, "context_flags", []) or []
        for flag in context_flags:
            weight = _CONTEXT_FLAG_RISK_WEIGHTS.get(flag, 0.0)
            if weight > 0:
                base_risk += weight

        # Scam-intent auto-escalation (OTP, financial manipulation)
        if intent == "scam_attempt":
            base_risk = max(base_risk, 0.85)
        elif intent == "aggression":
            base_risk = max(base_risk, 0.80)
        elif intent == "occupancy_probe":
            base_risk = max(base_risk, 0.70)
        elif intent == "entry_request":
            base_risk = max(base_risk, 0.65)

        # Face not visible penalty
        if not getattr(perception, "face_visible", True):
            base_risk += 0.20

        # Multi-person penalty
        num_persons = getattr(perception, "num_persons", 0)
        if num_persons > 2:
            base_risk += 0.15

        base_risk = round(min(max(base_risk, 0.0), 1.0), 3)

        # --- Step 2: escalation decision ---
        escalation_required = (
            base_risk >= 0.7
            or perception.weapon_detected
            or perception.anti_spoof_score >= 0.6
            or intent in ("scam_attempt", "aggression")
        )

        # --- Step 3: reply generation ---
        if escalation_required:
            # Use intent-specific escalation replies for Indian scenarios
            reply = self._escalation_reply(intent)
        else:
            reply = await self._generate_reply(intent, perception, transcript_lower)

        # Build tags
        tags = [intent]
        if perception.weapon_detected:
            tags.append("weapon")
        if escalation_required:
            tags.append("escalated")
        tags.extend(context_flags)

        logger.info(
            "Intelligence result [%s]: intent=%s risk=%.3f escalation=%s flags=%s reply='%s'",
            perception.session_id, intent, base_risk, escalation_required,
            context_flags, reply[:60],
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
        return {
            "aggressive": 0.6,
            "distressed": 0.4,
            "concerned": 0.3,
            "nervous": 0.25,
            "neutral": 0.2,
        }.get(emotion.lower(), 0.2)

    # ------------------------------------------------------------------
    # Escalation replies — intent-specific for Indian scenarios
    # ------------------------------------------------------------------

    @staticmethod
    def _escalation_reply(intent: str) -> str:
        """Return a safe escalation reply that never reveals system details."""
        replies = {
            "scam_attempt": "I cannot share any OTP, bank details, or personal information. The owner has been notified.",
            "aggression": "I have notified the owner and the security guard.",
            "occupancy_probe": "Please wait while I notify the owner.",
            "entry_request": "I cannot open the door. The owner has been notified.",
        }
        return replies.get(intent, "I have notified the owner and the security guard.")

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

    # ------------------------------------------------------------------
    # Conversation follow-up reply (for multi-turn chat)
    # ------------------------------------------------------------------

    async def generate_conversation_reply(
        self,
        session_id: str,
        message: str,
        conversation_history: list[dict],
        is_owner: bool = False,
    ) -> str:
        """Generate a reply in the context of an ongoing conversation.

        Uses Groq LLM with conversation history. Falls back to a canned reply
        if the LLM is unavailable.
        """
        if not self._groq_client:
            return self._canned_reply(self._classify_intent(message.lower()))

        try:
            reply = await asyncio.wait_for(
                asyncio.to_thread(
                    self._call_groq_conversation, message, conversation_history, is_owner
                ),
                timeout=8,
            )
            if reply:
                return reply
        except asyncio.TimeoutError:
            logger.warning("Groq conversation API timed out")
        except Exception as exc:
            logger.warning("Groq conversation call failed: %s", exc)

        return self._canned_reply(self._classify_intent(message.lower()))

    def _call_groq_conversation(
        self, message: str, history: list[dict], is_owner: bool = False
    ) -> str:
        """Call Groq LLM with conversation history for multi-turn chat."""
        messages = [{"role": "system", "content": self._system_prompt}]

        # Add conversation history (last 10 messages for context window efficiency)
        for entry in history[-10:]:
            messages.append({
                "role": entry.get("role", "user"),
                "content": entry.get("content", ""),
            })

        # Add the current message
        prefix = "[Owner says]" if is_owner else "[Visitor says]"
        messages.append({"role": "user", "content": f"{prefix}: {message}"})

        max_retries = 2
        backoff = 0.5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = self._groq_client.chat.completions.create(
                    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    messages=messages,
                    max_tokens=150,
                    temperature=0.3,
                )
                text = response.choices[0].message.content.strip()
                if text:
                    logger.info("Groq conversation reply (attempt %d): %s", attempt + 1, text[:80])
                    return text
            except Exception as exc:
                last_error = exc
                logger.warning("Groq conversation attempt %d/%d failed: %s", attempt + 1, max_retries + 1, exc)
                if attempt < max_retries:
                    import time
                    time.sleep(backoff)
                    backoff *= 2

        logger.error("All Groq conversation retries exhausted. Last error: %s", last_error)
        return ""

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
        """Build a compact context string for the Groq LLM prompt.
        Includes Indian-scenario context flags so the LLM can reason about them."""
        objects_str = ", ".join(
            f"{o.label} ({o.conf:.0%})" for o in perception.objects[:5]
        )
        context_flags = getattr(perception, "context_flags", []) or []
        num_persons = getattr(perception, "num_persons", 0)
        face_visible = getattr(perception, "face_visible", True)

        lines = [
            f"Detected objects: {objects_str or 'none'}",
            f"Visitor said: \"{perception.transcript or '(silence)'}\"",
            f"Emotion: {perception.emotion}",
            f"Risk level: {'HIGH' if perception.weapon_detected else 'normal'}",
            f"Weapon detected: {'YES — ' + ', '.join(perception.weapon_labels) if perception.weapon_detected else 'No'}",
            f"Number of persons: {num_persons}",
            f"Face visible: {'Yes' if face_visible else 'No — face obscured or camera blocked'}",
        ]
        if context_flags:
            lines.append(f"Context flags: {', '.join(context_flags)}")
        return "\n".join(lines)

    @staticmethod
    def _canned_reply(intent: str) -> str:
        """Fast canned replies keyed by classified intent — expanded for Indian scenarios."""
        return {
            "delivery": "Please leave the package at the doorstep. Thank you.",
            "help": "I'm alerting the owner right away. Please stay safe.",
            "visitor": "Please wait while I notify the owner.",
            "scam_attempt": "I cannot share any OTP, bank details, or personal information. The owner has been notified.",
            "domestic_staff": "Please wait while I verify with the owner.",
            "religious_donation": "Thank you, but the owner is not available for donations right now.",
            "government_claim": "Please wait while I notify the owner. Official visits require prior appointment.",
            "sales_marketing": "We are not interested, thank you.",
            "aggression": "I have notified the owner and the security guard.",
            "child_elderly": "Please don't worry. I'm notifying someone to help you right away.",
            "occupancy_probe": "Please wait while I notify the owner.",
            "identity_claim": "Please wait while I verify with the owner.",
            "entry_request": "I cannot open the door. Please wait while I notify the owner.",
            "unknown": "Please wait while I notify the owner.",
        }.get(intent, "Please wait while I notify the owner.")
