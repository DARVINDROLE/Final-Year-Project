from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def test_ring_creates_session_in_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "test_db.sqlite"
    monkeypatch.setenv("DOORBELL_DB_PATH", str(db_path))
    monkeypatch.setenv("DOORBELL_DISABLE_MODELS", "1")

    from api.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/ring",
            json={
                "type": "ring",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "image_base64": None,
                "audio_base64": None,
                "device_id": "frontdoor-01",
                "metadata": {"rssi": -50},
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["sessionId"].startswith("visitor_")
        assert payload["status"] == "queued"

        session_id = payload["sessionId"]
        statuses_seen = []

        deadline = time.time() + 3
        while time.time() < deadline:
            status_response = client.get(f"/api/session/{session_id}/status")
            assert status_response.status_code == 200
            status_payload = status_response.json()
            statuses_seen.append(status_payload["status"])
            if status_payload["status"] == "completed":
                break
            time.sleep(0.1)

        assert "queued" in statuses_seen or "processing" in statuses_seen
        assert statuses_seen[-1] == "completed"


def test_session_id_auto_generation(tmp_path, monkeypatch):
    """Test that session IDs are auto-generated when not provided."""
    db_path = tmp_path / "test_db.sqlite"
    monkeypatch.setenv("DOORBELL_DB_PATH", str(db_path))
    monkeypatch.setenv("DOORBELL_DISABLE_MODELS", "1")

    from api.main import app

    with TestClient(app) as client:
        # Test 1: Without session_id (should auto-generate)
        response1 = client.post(
            "/api/ring",
            json={
                "type": "ring",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_id": "frontdoor-01",
            },
        )
        assert response1.status_code == 200
        session_id_1 = response1.json()["sessionId"]
        assert session_id_1.startswith("visitor_")
        assert len(session_id_1) == len("visitor_") + 8

        # Test 2: Another request should generate different ID
        response2 = client.post(
            "/api/ring",
            json={
                "type": "ring",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_id": "frontdoor-02",
            },
        )
        assert response2.status_code == 200
        session_id_2 = response2.json()["sessionId"]
        assert session_id_2.startswith("visitor_")
        assert session_id_1 != session_id_2  # Should be unique

        # Test 3: With explicit session_id (should use provided)
        response3 = client.post(
            "/api/ring",
            json={
                "type": "ring",
                "session_id": "custom_session_123",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_id": "frontdoor-03",
            },
        )
        assert response3.status_code == 200
        session_id_3 = response3.json()["sessionId"]
        assert session_id_3 == "custom_session_123"  # Should use provided ID

        logs_response = client.get("/api/logs")
        assert logs_response.status_code == 200
        logs_payload = logs_response.json()
        assert "sessions" in logs_payload
        assert "actions" in logs_payload

    assert Path(db_path).exists()
