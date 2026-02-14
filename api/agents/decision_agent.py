from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import DecisionOutput, IntelligenceOutput
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

_DEFAULT_POLICY = {
    "thresholds": {
        "escalate_risk": 0.7,
        "auto_reply_max_risk": 0.4,
    },
    "owner_defaults": {
        "auto_reply_enabled": True,
        "vacation_mode": False,
    },
    "vacation_overrides": {
        "escalate_risk": 0.5,
        "auto_reply_max_risk": 0.3,
        "default_action": "escalate",
    },
}


class DecisionAgent(BaseAgent):
    """Policy and business-logic layer — maps risk into concrete actions."""

    def __init__(self, policy_path: str = "api/policies/policy.yaml") -> None:
        super().__init__("api/instructions/decision.md")
        self.policy = self._load_policy(policy_path)
        self._thresholds = self.policy.get("thresholds", _DEFAULT_POLICY["thresholds"])
        self._owner = self.policy.get("owner_defaults", _DEFAULT_POLICY["owner_defaults"])
        self._vacation = self.policy.get("vacation_overrides", _DEFAULT_POLICY["vacation_overrides"])

    # ------------------------------------------------------------------
    # Policy loading
    # ------------------------------------------------------------------

    def _load_policy(self, policy_path: str) -> dict[str, Any]:
        """Load policy.yaml — falls back to built-in defaults if missing."""
        path = Path(policy_path)
        if not path.exists():
            logger.warning("Policy file not found at %s — using built-in defaults", path)
            return dict(_DEFAULT_POLICY)

        try:
            yaml = importlib.import_module("yaml")
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
            logger.info("Loaded decision policy from %s (%d rules)", path, len(data.get("rules", [])))
            return data
        except ImportError:
            logger.warning("PyYAML not installed — using built-in policy defaults")
            return dict(_DEFAULT_POLICY)
        except Exception as exc:
            logger.warning("Failed to parse policy file: %s — using defaults", exc)
            return dict(_DEFAULT_POLICY)

    # ------------------------------------------------------------------
    # Active thresholds (vacation mode aware)
    # ------------------------------------------------------------------

    def _active_thresholds(self) -> dict[str, float]:
        """Return effective thresholds, adjusted for vacation mode."""
        base = dict(self._thresholds)
        if self._owner.get("vacation_mode", False):
            base["escalate_risk"] = self._vacation.get(
                "escalate_risk", base["escalate_risk"]
            )
            base["auto_reply_max_risk"] = self._vacation.get(
                "auto_reply_max_risk", base["auto_reply_max_risk"]
            )
        return base

    # ------------------------------------------------------------------
    # Main processing
    # ------------------------------------------------------------------

    async def process(
        self,
        intelligence: IntelligenceOutput,
        weapon_detected: bool = False,
        anti_spoof_score: float = 0.0,
    ) -> DecisionOutput:
        """Evaluate policy rules against intelligence output. Extra context
        (weapon_detected, anti_spoof_score) is forwarded by the orchestrator
        for rules that need perception-level data."""

        thresholds = self._active_thresholds()
        escalate_risk = thresholds.get("escalate_risk", 0.7)
        auto_reply_max = thresholds.get("auto_reply_max_risk", 0.4)
        auto_reply_enabled = self._owner.get("auto_reply_enabled", True)

        # --- Rule 1: weapon → always escalate ---
        if weapon_detected:
            return self._decision(
                intelligence.session_id,
                "escalate",
                "Weapon detected — mandatory escalation",
                {"tts": True, "notify_owner": True, "notify_watchman": True},
            )

        # --- Rule 2: high risk / escalation flag ---
        if intelligence.escalation_required or intelligence.risk_score >= escalate_risk:
            return self._decision(
                intelligence.session_id,
                "escalate",
                f"risk ({intelligence.risk_score:.3f}) >= threshold ({escalate_risk}) or escalation flag",
                {"tts": True, "notify_owner": True},
            )

        # --- Rule 3: anti-spoof trigger ---
        if anti_spoof_score >= 0.6:
            return self._decision(
                intelligence.session_id,
                "escalate",
                f"Anti-spoof score ({anti_spoof_score:.2f}) indicates possible spoofing",
                {"tts": True, "notify_owner": True},
            )

        # --- Rule 4: low risk auto-reply ---
        if intelligence.risk_score < auto_reply_max and auto_reply_enabled:
            return self._decision(
                intelligence.session_id,
                "auto_reply",
                f"risk ({intelligence.risk_score:.3f}) < auto-reply threshold ({auto_reply_max})",
                {"tts": True, "notify_owner": False},
            )

        # --- Rule 5: default medium risk → notify owner ---
        return self._decision(
            intelligence.session_id,
            "notify_owner",
            f"Medium risk ({intelligence.risk_score:.3f}) — owner notification",
            {"tts": False, "notify_owner": True},
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _decision(
        session_id: str, action: str, reason: str, dispatch: dict[str, Any]
    ) -> DecisionOutput:
        logger.info("Decision [%s]: action=%s reason='%s'", session_id, action, reason)
        return DecisionOutput(
            session_id=session_id,
            final_action=action,
            reason=reason,
            dispatch=dispatch,
            timestamp=datetime.now(timezone.utc),
        )
