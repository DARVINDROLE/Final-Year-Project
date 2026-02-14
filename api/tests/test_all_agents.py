"""
Comprehensive tests for ALL agents — Phase 5 final testing.

Covers:
  - Perception Agent: emotion detection, context flags, anti-spoof
  - Intelligence Agent: 13 Indian-scenario intents, risk scoring, context flag weights
  - Decision Agent: 12 rules including scam/aggression/occupancy/identity/multi-person
  - Action Agent: TTS generation, notifications, escalation, DB logging
  - End-to-end pipeline integration

Run with:
    cd D:\\Final-year-project\\Final-Year-Project
    .\\fyp-api\\Scripts\\Activate.ps1
    $env:DOORBELL_DISABLE_MODELS="1"
    python -m pytest api/tests/test_all_agents.py -v
"""

import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Disable model loading for unit tests
os.environ["DOORBELL_DISABLE_MODELS"] = "1"

from api.agents.action_agent import ActionAgent
from api.agents.decision_agent import DecisionAgent
from api.agents.intelligence_agent import IntelligenceAgent
from api.agents.perception_agent import PerceptionAgent
from api.db import Database
from api.models import (
    ActionRequest,
    DecisionOutput,
    IntelligenceOutput,
    PerceptionOutput,
    RingEvent,
)


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
        num_persons=1,
        face_visible=True,
        context_flags=[],
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


def _make_decision(**overrides) -> DecisionOutput:
    defaults = dict(
        session_id="visitor_test01",
        final_action="auto_reply",
        reason="test decision",
        dispatch={"tts": True, "notify_owner": False},
        timestamp=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return DecisionOutput(**defaults)


# ══════════════════════════════════════════════════════════════
# PERCEPTION AGENT TESTS
# ══════════════════════════════════════════════════════════════

class TestPerceptionEmotion:
    """Test emotion inference with Indian/Hindi keywords."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = PerceptionAgent()

    def test_aggressive_hindi(self):
        assert self.agent._infer_emotion("darwaza kholo warna dekh lena") == "aggressive"

    def test_aggressive_english(self):
        assert self.agent._infer_emotion("I will break the door") == "aggressive"

    def test_distressed_hindi(self):
        assert self.agent._infer_emotion("bachao madad karo") == "distressed"

    def test_distressed_english(self):
        assert self.agent._infer_emotion("help there is a fire") == "distressed"

    def test_concerned(self):
        assert self.agent._infer_emotion("please it is very urgent") == "concerned"

    def test_nervous(self):
        assert self.agent._infer_emotion("actually umm well you see") == "nervous"

    def test_neutral_delivery(self):
        assert self.agent._infer_emotion("I have a package") == "neutral"

    def test_empty_transcript(self):
        assert self.agent._infer_emotion("") == "neutral"


class TestPerceptionContextFlags:
    """Test Indian-scenario context flag detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = PerceptionAgent()

    def _flags(self, transcript, objects=None, person_detected=True, num_persons=1):
        from api.models import ObjectDetection
        objs = objects or []
        return self.agent._detect_context_flags(transcript, objs, person_detected, num_persons)

    def test_delivery_no_package_mismatch(self):
        from api.models import ObjectDetection
        objs = [ObjectDetection(label="person", conf=0.9)]
        flags = self._flags("amazon delivery hai", objects=objs)
        assert "claim_object_mismatch" in flags

    def test_delivery_with_package_no_mismatch(self):
        from api.models import ObjectDetection
        objs = [ObjectDetection(label="person", conf=0.9), ObjectDetection(label="backpack", conf=0.7)]
        flags = self._flags("amazon delivery hai", objects=objs)
        assert "claim_object_mismatch" not in flags

    def test_otp_request_detected(self):
        flags = self._flags("sir otp bata dijiye")
        assert "otp_request" in flags

    def test_occupancy_probe_detected(self):
        flags = self._flags("koi ghar pe hai?")
        assert "occupancy_probe" in flags

    def test_entry_request_detected(self):
        flags = self._flags("darwaza khol do andar aana hai")
        assert "entry_request" in flags

    def test_financial_request_detected(self):
        flags = self._flags("upi se payment kar dijiye")
        assert "financial_request" in flags

    def test_identity_claim_detected(self):
        flags = self._flags("owner ne bola hai, relative hoon")
        assert "identity_claim" in flags

    def test_authority_claim_detected(self):
        flags = self._flags("bijli department se aaye hain inspection ke liye")
        assert "authority_claim" in flags

    def test_staff_claim_detected(self):
        flags = self._flags("main aaj se kaam karungi purani bai nahi aayegi")
        assert "staff_claim" in flags

    def test_donation_request_detected(self):
        flags = self._flags("mandir ke liye chanda hai")
        assert "donation_request" in flags

    def test_multi_person_flag(self):
        flags = self._flags("delivery hai", num_persons=3)
        assert "multi_person" in flags

    def test_no_flags_for_simple_greeting(self):
        flags = self._flags("hello good morning")
        assert flags == []


class TestPerceptionAntiSpoof:
    """Test enhanced anti-spoof scoring."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = PerceptionAgent()

    def test_no_person(self):
        score = self.agent._compute_anti_spoof_score(False, 0.0, "hello")
        assert score == 0.9

    def test_face_hidden_penalty(self):
        score = self.agent._compute_anti_spoof_score(True, 0.5, "hello", face_visible=False)
        assert score >= 0.25

    def test_otp_context_flag_penalty(self):
        score = self.agent._compute_anti_spoof_score(
            True, 0.5, "otp batao", context_flags=["otp_request"]
        )
        assert score >= 0.15

    def test_clean_visitor(self):
        score = self.agent._compute_anti_spoof_score(True, 0.9, "hello")
        assert score < 0.1


# ══════════════════════════════════════════════════════════════
# INTELLIGENCE AGENT TESTS — Indian Scenarios
# ══════════════════════════════════════════════════════════════

class TestIntelligenceIndianScenarios:
    """Test all 13 Indian-specific intent categories."""

    @pytest.fixture(autouse=True)
    def setup(self):
        old = os.environ.pop("GROQ_API_KEY", None)
        self.agent = IntelligenceAgent()
        yield
        if old is not None:
            os.environ["GROQ_API_KEY"] = old

    def _process(self, **kwargs):
        perception = _make_perception(**kwargs)
        return asyncio.get_event_loop().run_until_complete(self.agent.process(perception))

    # --- Delivery ---
    def test_delivery_intent(self):
        r = self._process(transcript="I have a flipkart delivery")
        assert r.intent == "delivery"
        assert r.risk_score < 0.5

    def test_delivery_swiggy(self):
        r = self._process(transcript="swiggy order")
        assert r.intent == "delivery"

    # --- Scam ---
    def test_otp_scam(self):
        r = self._process(transcript="sir otp bata dijiye delivery complete karna hai")
        assert r.intent == "scam_attempt"
        assert r.risk_score >= 0.85
        assert r.escalation_required is True
        assert "otp" in r.reply_text.lower()

    def test_kyc_scam(self):
        r = self._process(transcript="aadhaar kyc verification hai")
        assert r.intent == "scam_attempt"
        assert r.escalation_required is True

    def test_upi_scam(self):
        r = self._process(transcript="qr scan kar dijiye refund dena hai")
        assert r.intent == "scam_attempt"
        assert r.risk_score >= 0.85

    def test_bank_scam(self):
        r = self._process(transcript="bank verification ke liye account number dijiye")
        assert r.intent == "scam_attempt"

    # --- Domestic staff ---
    def test_maid_claim(self):
        r = self._process(transcript="main aaj se kaam karungi purani bai nahi aayegi")
        assert r.intent == "domestic_staff"
        assert "verify" in r.reply_text.lower() or "owner" in r.reply_text.lower()

    # --- Religious donation ---
    def test_temple_donation(self):
        r = self._process(transcript="mandir ke liye chanda hai")
        assert r.intent == "religious_donation"
        assert "donation" in r.reply_text.lower() or "available" in r.reply_text.lower()

    # --- Government claim ---
    def test_electricity_check(self):
        r = self._process(transcript="bijli check karne aaye hain")
        assert r.intent == "government_claim"
        assert "owner" in r.reply_text.lower() or "appointment" in r.reply_text.lower()

    # --- Sales ---
    def test_water_purifier_sales(self):
        r = self._process(transcript="free demo hai water purifier ka")
        assert r.intent == "sales_marketing"
        assert "not interested" in r.reply_text.lower() or "thank" in r.reply_text.lower()

    # --- Aggression ---
    def test_verbal_threat_hindi(self):
        r = self._process(transcript="darwaza kholo warna dekh lena")
        assert r.intent == "aggression"
        assert r.risk_score >= 0.80
        assert r.escalation_required is True
        assert "notified" in r.reply_text.lower() or "security" in r.reply_text.lower()

    # --- Child/elderly ---
    def test_lost_child(self):
        r = self._process(transcript="mummy kho gayi", emotion="distressed")
        assert r.intent == "child_elderly"
        assert "help" in r.reply_text.lower() or "worry" in r.reply_text.lower() or "notify" in r.reply_text.lower()

    def test_elderly_water(self):
        r = self._process(transcript="bhai sahab paani milega")
        assert r.intent == "child_elderly"

    # --- Occupancy probe ---
    def test_occupancy_probe(self):
        r = self._process(transcript="koi ghar pe hai?")
        assert r.intent == "occupancy_probe"
        assert r.risk_score >= 0.70
        assert r.escalation_required is True
        # Must never reveal occupancy info
        assert "home" not in r.reply_text.lower() or "owner" in r.reply_text.lower()

    # --- Identity claim ---
    def test_identity_claim(self):
        r = self._process(transcript="i know the owner personally")
        assert r.intent == "identity_claim"
        assert "verify" in r.reply_text.lower() or "owner" in r.reply_text.lower()

    # --- Entry request ---
    def test_entry_request(self):
        r = self._process(transcript="gate khol do andar aana hai")
        assert r.intent == "entry_request"
        assert r.risk_score >= 0.65
        assert "cannot open" in r.reply_text.lower() or "owner" in r.reply_text.lower()

    # --- Context flag risk adjustments ---
    def test_otp_flag_raises_risk(self):
        r = self._process(
            transcript="otp bata do",
            context_flags=["otp_request"],
        )
        assert r.risk_score >= 0.85  # scam_attempt intent + otp flag weight

    def test_face_hidden_raises_risk(self):
        r = self._process(
            transcript="hello",
            face_visible=False,
        )
        # Face hidden adds +0.20 risk
        assert r.risk_score > 0.3

    def test_multi_person_raises_risk(self):
        r = self._process(
            transcript="delivery hai",
            num_persons=4,
        )
        # 4 persons adds +0.15 risk
        assert r.risk_score > 0.2


# ══════════════════════════════════════════════════════════════
# DECISION AGENT TESTS — Hardened Rules
# ══════════════════════════════════════════════════════════════

class TestDecisionIndianRules:
    """Test all 12 decision rules including Indian-specific scenarios."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.agent = DecisionAgent()

    def _decide(self, intel_kwargs=None, **extra):
        intel = _make_intelligence(**(intel_kwargs or {}))
        return asyncio.get_event_loop().run_until_complete(
            self.agent.process(intel, **extra)
        )

    # Rule 1: weapon
    def test_weapon_escalates(self):
        r = self._decide(weapon_detected=True)
        assert r.final_action == "escalate"
        assert r.dispatch.get("notify_watchman") is True

    # Rule 2: scam
    def test_scam_intent_escalates(self):
        r = self._decide(intel_kwargs={"intent": "scam_attempt", "risk_score": 0.9, "escalation_required": True})
        assert r.final_action == "escalate"

    def test_otp_flag_escalates(self):
        r = self._decide(context_flags=["otp_request"])
        assert r.final_action == "escalate"

    # Rule 3: aggression
    def test_aggression_escalates(self):
        r = self._decide(intel_kwargs={"intent": "aggression", "risk_score": 0.8, "escalation_required": True})
        assert r.final_action == "escalate"
        assert r.dispatch.get("notify_watchman") is True

    # Rule 4: occupancy probe
    def test_occupancy_probe_escalates(self):
        r = self._decide(intel_kwargs={"intent": "occupancy_probe", "risk_score": 0.7, "escalation_required": True})
        assert r.final_action == "escalate"

    def test_occupancy_flag_escalates(self):
        r = self._decide(context_flags=["occupancy_probe"])
        assert r.final_action == "escalate"

    # Rule 5: high risk
    def test_high_risk_escalates(self):
        r = self._decide(intel_kwargs={"risk_score": 0.8, "escalation_required": True})
        assert r.final_action == "escalate"

    # Rule 6: anti-spoof
    def test_anti_spoof_escalates(self):
        r = self._decide(anti_spoof_score=0.65)
        assert r.final_action == "escalate"

    # Rule 7: face hidden
    def test_face_hidden_notifies_owner(self):
        r = self._decide(face_visible=False)
        assert r.final_action == "notify_owner"

    # Rule 8: identity/staff/government claims
    def test_identity_claim_notifies_owner(self):
        r = self._decide(intel_kwargs={"intent": "identity_claim"})
        assert r.final_action == "notify_owner"

    def test_domestic_staff_notifies_owner(self):
        r = self._decide(intel_kwargs={"intent": "domestic_staff"})
        assert r.final_action == "notify_owner"

    def test_government_claim_notifies_owner(self):
        r = self._decide(intel_kwargs={"intent": "government_claim"})
        assert r.final_action == "notify_owner"

    def test_entry_request_notifies_owner(self):
        r = self._decide(intel_kwargs={"intent": "entry_request"})
        assert r.final_action == "notify_owner"

    def test_staff_flag_notifies_owner(self):
        r = self._decide(context_flags=["staff_claim"])
        assert r.final_action == "notify_owner"

    # Rule 9: multi-person
    def test_multi_person_notifies_owner(self):
        r = self._decide(num_persons=3)
        assert r.final_action == "notify_owner"

    # Rule 10: child/elderly
    def test_child_elderly_notifies_owner(self):
        r = self._decide(intel_kwargs={"intent": "child_elderly"})
        assert r.final_action == "notify_owner"

    # Rule 11: low risk auto-reply
    def test_low_risk_auto_replies(self):
        r = self._decide(intel_kwargs={"risk_score": 0.2, "escalation_required": False})
        assert r.final_action == "auto_reply"
        assert r.dispatch.get("tts") is True

    # Rule 12: medium risk notify
    def test_medium_risk_notifies_owner(self):
        r = self._decide(intel_kwargs={"risk_score": 0.55, "escalation_required": False})
        assert r.final_action == "notify_owner"


# ══════════════════════════════════════════════════════════════
# ACTION AGENT TESTS — Phase 5
# ══════════════════════════════════════════════════════════════

class TestActionAgent:
    """Test the Phase 5 Action Agent: TTS, notifications, escalation, DB logging."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.db_path = str(tmp_path / "test_action.sqlite")
        self.db = Database(self.db_path)
        self.db.initialize()
        # Create a test session
        self.db.create_session("visitor_test01", datetime.now(timezone.utc).isoformat(), "test-device")
        self.agent = ActionAgent(db=self.db)
        self.tmp_path = tmp_path

    def _run(self, decision_kwargs=None, intel_kwargs=None, perception_kwargs=None):
        decision = _make_decision(**(decision_kwargs or {}))
        intel = _make_intelligence(**(intel_kwargs or {}))
        perception = _make_perception(**(perception_kwargs or {}))
        request = ActionRequest(
            session_id="visitor_test01",
            tts_text=intel.reply_text,
            image_path="data/snaps/test.jpg",
            notify_payload={"priority": "normal"},
            timestamp=datetime.now(timezone.utc),
        )
        return asyncio.get_event_loop().run_until_complete(
            self.agent.handle(decision, intel, perception, request)
        )

    def test_auto_reply_generates_tts(self):
        result = self._run(
            decision_kwargs={"final_action": "auto_reply", "dispatch": {"tts": True, "notify_owner": False}},
            intel_kwargs={"reply_text": "Please leave the package at the doorstep."},
        )
        assert result.status == "played"
        assert result.action_type == "auto_reply"
        assert result.payload.get("tts_file")
        assert result.payload.get("reply_text") == "Please leave the package at the doorstep."

    def test_notify_owner_creates_notification(self):
        result = self._run(
            decision_kwargs={"final_action": "notify_owner", "dispatch": {"tts": True, "notify_owner": True}},
            intel_kwargs={"reply_text": "Please wait while I verify with the owner.", "intent": "domestic_staff"},
        )
        assert result.status == "queued"
        assert result.action_type == "notify_owner"
        assert "notification" in result.payload
        notif = result.payload["notification"]
        assert notif["priority"] == "normal"
        assert "owner" in notif["recipients"]
        assert notif["intent"] == "domestic_staff"

    def test_escalation_creates_critical_notification(self):
        result = self._run(
            decision_kwargs={
                "final_action": "escalate",
                "dispatch": {"tts": True, "notify_owner": True, "notify_watchman": True},
            },
            intel_kwargs={
                "reply_text": "I have notified the owner and the security guard.",
                "risk_score": 0.9,
                "escalation_required": True,
                "intent": "aggression",
            },
            perception_kwargs={"emotion": "aggressive"},
        )
        assert result.status == "escalated"
        assert result.action_type == "escalate"
        assert "notification" in result.payload
        notif = result.payload["notification"]
        assert notif["priority"] == "critical"
        assert "owner" in notif["recipients"]
        assert "watchman" in notif["recipients"]
        assert notif["emotion"] == "aggressive"

    def test_ignore_action(self):
        result = self._run(
            decision_kwargs={"final_action": "ignore", "dispatch": {}},
        )
        assert result.status == "ignored"
        assert result.action_type == "ignore"

    def test_db_logging_on_auto_reply(self):
        """Verify action agent writes to actions table in DB."""
        self._run(
            decision_kwargs={"final_action": "auto_reply", "dispatch": {"tts": True}},
            intel_kwargs={"reply_text": "test reply"},
        )
        logs = self.db.get_recent_logs(limit=10)
        action_types = [a["action_type"] for a in logs.get("actions", [])]
        assert "auto_reply" in action_types

    def test_escalation_logs_notification_action(self):
        """Verify escalation creates a pending notification row in DB."""
        self._run(
            decision_kwargs={
                "final_action": "escalate",
                "dispatch": {"tts": True, "notify_owner": True},
            },
        )
        logs = self.db.get_recent_logs(limit=10)
        action_types = [a["action_type"] for a in logs.get("actions", [])]
        assert "escalation_notification" in action_types

    def test_sanitizes_tts_text(self):
        """Verify dangerous characters are sanitized from TTS text."""
        from api.utils.tts import sanitize_tts_text
        assert sanitize_tts_text('Hello "world"') == "Hello 'world'"
        assert len(sanitize_tts_text("A" * 500)) == 240
        assert "\n" not in sanitize_tts_text("line1\nline2")


# ══════════════════════════════════════════════════════════════
# TTS UTILITY TESTS
# ══════════════════════════════════════════════════════════════

class TestTTSUtility:
    """Test the TTS utility module."""

    def test_sanitize_strips_control_chars(self):
        from api.utils.tts import sanitize_tts_text
        text_with_control = "Hello\x00World\x07Test"
        result = sanitize_tts_text(text_with_control)
        assert "\x00" not in result
        assert "\x07" not in result

    def test_sanitize_max_length(self):
        from api.utils.tts import sanitize_tts_text
        long = "x" * 500
        assert len(sanitize_tts_text(long)) == 240

    def test_generate_creates_file(self, tmp_path):
        from api.utils.tts import generate_tts_audio
        path = generate_tts_audio(
            text="Hello world",
            session_id="test_session",
            output_dir=str(tmp_path),
            play=False,
        )
        assert path  # not empty
        assert Path(path).exists()


# ══════════════════════════════════════════════════════════════
# END-TO-END PIPELINE INTEGRATION TEST
# ══════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """Test the full pipeline: Perception → Intelligence → Decision → Action."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        os.environ.pop("GROQ_API_KEY", None)
        self.perception = PerceptionAgent()
        self.intelligence = IntelligenceAgent()
        self.decision = DecisionAgent()
        self.db = Database(str(tmp_path / "test_pipeline.sqlite"))
        self.db.initialize()
        self.db.create_session("visitor_pipe01", datetime.now(timezone.utc).isoformat(), "test")
        self.action = ActionAgent(db=self.db)

    async def _run_pipeline(self, transcript: str, **perc_overrides):
        """Simulate the full pipeline with a given transcript."""
        perception = _make_perception(
            session_id="visitor_pipe01",
            transcript=transcript,
            **perc_overrides,
        )
        intelligence = await self.intelligence.process(perception)
        decision = await self.decision.process(
            intelligence,
            weapon_detected=perception.weapon_detected,
            anti_spoof_score=perception.anti_spoof_score,
            context_flags=perception.context_flags,
            num_persons=perception.num_persons,
            face_visible=perception.face_visible,
        )
        action_request = ActionRequest(
            session_id="visitor_pipe01",
            tts_text=intelligence.reply_text,
            image_path=perception.image_path,
            notify_payload={"priority": "high" if decision.final_action == "escalate" else "normal"},
            timestamp=datetime.now(timezone.utc),
        )
        action_result = await self.action.handle(decision, intelligence, perception, action_request)
        return {
            "perception": perception,
            "intelligence": intelligence,
            "decision": decision,
            "action": action_result,
        }

    def test_simple_delivery_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline("I have a package delivery")
        )
        assert r["intelligence"].intent == "delivery"
        assert r["decision"].final_action == "auto_reply"
        assert r["action"].status == "played"

    def test_otp_scam_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline(
                "sir otp bata dijiye",
                context_flags=["otp_request"],
            )
        )
        assert r["intelligence"].intent == "scam_attempt"
        assert r["intelligence"].escalation_required is True
        assert r["decision"].final_action == "escalate"
        assert r["action"].status == "escalated"

    def test_weapon_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline(
                "open the door now",
                weapon_detected=True,
                weapon_labels=["knife"],
            )
        )
        assert r["intelligence"].risk_score >= 0.75
        assert r["decision"].final_action == "escalate"
        assert r["decision"].dispatch.get("notify_watchman") is True

    def test_occupancy_probe_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline(
                "koi ghar pe hai?",
                context_flags=["occupancy_probe"],
            )
        )
        assert r["intelligence"].intent == "occupancy_probe"
        assert r["decision"].final_action == "escalate"
        # Response must not reveal occupancy
        assert "home" not in r["intelligence"].reply_text.lower() or "owner" in r["intelligence"].reply_text.lower()

    def test_child_elderly_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline("mummy kho gayi", emotion="distressed")
        )
        assert r["intelligence"].intent == "child_elderly"
        assert r["decision"].final_action == "notify_owner"

    def test_sales_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline("free demo hai")
        )
        assert r["intelligence"].intent == "sales_marketing"
        assert r["decision"].final_action == "auto_reply"

    def test_aggression_pipeline(self):
        r = asyncio.get_event_loop().run_until_complete(
            self._run_pipeline("todenge darwaza maar dunga", emotion="aggressive")
        )
        assert r["intelligence"].intent == "aggression"
        assert r["intelligence"].escalation_required is True
        assert r["decision"].final_action == "escalate"
