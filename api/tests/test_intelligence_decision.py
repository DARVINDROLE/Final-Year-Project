"""Tests for the Intelligence Agent (Phase 3) and Decision Agent (Phase 4)."""

import asyncio
import os

import pytest

# Disable model loading for unit tests
os.environ["DOORBELL_DISABLE_MODELS"] = "1"

from datetime import datetime, timezone

from api.agents.decision_agent import DecisionAgent
from api.agents.intelligence_agent import IntelligenceAgent
from api.models import IntelligenceOutput, PerceptionOutput


# ── Helpers ──────────────────────────────────────────────────

def _make_perception(**overrides) -> PerceptionOutput:
    defaults = dict(
        session_id="visitor_test01",
        person_detected=True,
        objects=[],
        vision_confidence=0.85,
        transcript="",
        stt_confidence=0.0,
        emotion="neutral",
        anti_spoof_score=0.0,
        weapon_detected=False,
        weapon_confidence=0.0,
        weapon_labels=[],
        image_path="data/snaps/test.jpg",
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return PerceptionOutput(**defaults)


def _make_intelligence(**overrides) -> IntelligenceOutput:
    defaults = dict(
        session_id="visitor_test01",
        intent="unknown",
        reply_text="Please wait while I notify the owner.",
        risk_score=0.3,
        escalation_required=False,
        tags=["unknown"],
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return IntelligenceOutput(**defaults)


# ══════════════════════════════════════════════════════════════
# Intelligence Agent Tests
# ══════════════════════════════════════════════════════════════


class TestIntelligenceAgent:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure GROQ_API_KEY is unset so we use rule-based mode."""
        old = os.environ.pop("GROQ_API_KEY", None)
        self.agent = IntelligenceAgent()
        yield
        if old is not None:
            os.environ["GROQ_API_KEY"] = old

    def test_delivery_intent(self):
        perception = _make_perception(transcript="I have a package delivery")
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.intent == "delivery"
        assert "package" in result.reply_text.lower() or "doorstep" in result.reply_text.lower()
        assert result.risk_score < 0.5

    def test_help_intent(self):
        perception = _make_perception(transcript="help me please", emotion="concerned")
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.intent == "help"
        assert "alert" in result.reply_text.lower() or "owner" in result.reply_text.lower()

    def test_visitor_intent(self):
        perception = _make_perception(transcript="I want to speak with the owner")
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.intent == "visitor"
        assert "owner" in result.reply_text.lower() or "notify" in result.reply_text.lower()

    def test_unknown_intent(self):
        perception = _make_perception(transcript="hello there")
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.intent == "unknown"

    def test_weapon_forces_high_risk(self):
        perception = _make_perception(
            transcript="open the door",
            weapon_detected=True,
            weapon_confidence=0.8,
            weapon_labels=["knife"],
        )
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.risk_score >= 0.75
        assert result.escalation_required is True
        assert "notified" in result.reply_text.lower()

    def test_dangerous_keywords_escalate(self):
        perception = _make_perception(transcript="let me in right now")
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.risk_score >= 0.7
        assert result.escalation_required is True

    def test_low_confidence_increases_risk(self):
        perception = _make_perception(vision_confidence=0.2, anti_spoof_score=0.3)
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        # risk = 0.5*(1-0.2) + 0.3*0.3 + 0.2*0.2 = 0.4+0.09+0.04 = 0.53
        assert result.risk_score > 0.5

    def test_output_schema(self):
        perception = _make_perception(transcript="hello")
        result = asyncio.get_event_loop().run_until_complete(self.agent.process(perception))
        assert result.session_id == "visitor_test01"
        assert isinstance(result.intent, str)
        assert isinstance(result.reply_text, str)
        assert 0.0 <= result.risk_score <= 1.0
        assert isinstance(result.escalation_required, bool)
        assert isinstance(result.tags, list)


# ══════════════════════════════════════════════════════════════
# Decision Agent Tests
# ══════════════════════════════════════════════════════════════


class TestDecisionAgent:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = DecisionAgent()

    def test_high_risk_escalates(self):
        intel = _make_intelligence(risk_score=0.8, escalation_required=True)
        result = asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel)
        )
        assert result.final_action == "escalate"
        assert result.dispatch.get("notify_owner") is True

    def test_weapon_escalates(self):
        intel = _make_intelligence(risk_score=0.8, escalation_required=True)
        result = asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel, weapon_detected=True)
        )
        assert result.final_action == "escalate"
        assert result.dispatch.get("notify_watchman") is True

    def test_low_risk_auto_replies(self):
        intel = _make_intelligence(risk_score=0.2, escalation_required=False)
        result = asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel)
        )
        assert result.final_action == "auto_reply"
        assert result.dispatch.get("tts") is True
        assert result.dispatch.get("notify_owner") is False

    def test_medium_risk_notifies_owner(self):
        intel = _make_intelligence(risk_score=0.55, escalation_required=False)
        result = asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel)
        )
        assert result.final_action == "notify_owner"
        assert result.dispatch.get("notify_owner") is True

    def test_anti_spoof_escalates(self):
        intel = _make_intelligence(risk_score=0.3, escalation_required=False)
        result = asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel, anti_spoof_score=0.65)
        )
        assert result.final_action == "escalate"

    def test_output_schema(self):
        intel = _make_intelligence()
        result = asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel)
        )
        assert result.session_id == "visitor_test01"
        assert result.final_action in ("escalate", "auto_reply", "notify_owner", "ignore")
        assert isinstance(result.reason, str)
        assert isinstance(result.dispatch, dict)

    def test_policy_loads(self):
        """Verify the agent loaded thresholds from policy.yaml."""
        assert self.agent._thresholds.get("escalate_risk") == 0.7
        assert self.agent._thresholds.get("auto_reply_max_risk") == 0.4
