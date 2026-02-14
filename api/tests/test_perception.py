from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from api.agents.perception_agent import PerceptionAgent
from api.models import RingEvent


def test_perception_output_shape(monkeypatch):
    monkeypatch.setenv("DOORBELL_DISABLE_MODELS", "1")

    agent = PerceptionAgent()
    event = RingEvent(
        type="ring",
        session_id="visitor_test_01",
        timestamp=datetime.now(timezone.utc),
        image_base64=None,
        audio_base64=None,
        image_path="",
        audio_path=None,
        device_id="frontdoor-01",
        metadata={},
    )

    result = asyncio.run(agent.process(event))

    assert result.session_id == "visitor_test_01"
    assert isinstance(result.person_detected, bool)
    assert isinstance(result.objects, list)
    assert 0.0 <= result.anti_spoof_score <= 1.0
    assert isinstance(result.weapon_detected, bool)
    assert isinstance(result.weapon_labels, list)
