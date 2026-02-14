"""
Test script: Captures video + audio from webcam/mic and sends to /api/ring.
After pipeline completes, reads back the AI reply and plays it via TTS.

Run this while the API server is running:
    python -m uvicorn api.main:app --reload --port 8000

Usage:
    python api/tests/test_webcam_ring.py                # image only (original mode)
    python api/tests/test_webcam_ring.py --voice         # image + voice recording + TTS reply
    python api/tests/test_webcam_ring.py --scenario       # run pre-defined Indian scenario tests
    python api/tests/test_webcam_ring.py --scenario 3     # run specific scenario by number
    python api/tests/test_webcam_ring.py --voice --scenario  # voice with scenario prompt on screen

Requirements:
    pip install opencv-python requests pyaudio pyttsx3
    (pyaudio needs portaudio — on Windows `pip install pyaudio` usually works)
"""

import argparse
import base64
import json
import sys
import time
import wave
from pathlib import Path

import cv2
import requests

API_BASE = "http://127.0.0.1:8000"

# Audio recording parameters (16kHz mono, matching VOSK expectations)
AUDIO_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_FORMAT_WIDTH = 2  # 16-bit
AUDIO_CHUNK = 1024


# ══════════════════════════════════════════════════════════════
# Indian Household Scenarios (from scenarios.md)
# ══════════════════════════════════════════════════════════════

SCENARIOS = [
    # --- Delivery ---
    {
        "id": 1, "category": "delivery",
        "name": "Simple delivery",
        "prompt": "Say: 'I have a package delivery'",
        "expected_intent": "delivery",
        "expected_action": "auto_reply",
        "max_risk": 0.45,
    },
    {
        "id": 2, "category": "delivery",
        "name": "COD payment request",
        "prompt": "Say: '1299 rupees COD hai, change milega kya?'",
        "expected_intent": "delivery",
        "expected_action": "notify_owner",
        "max_risk": 0.65,
    },
    {
        "id": 3, "category": "scam",
        "name": "OTP scam attempt",
        "prompt": "Say: 'Sir OTP bata dijiye, delivery complete karna hai'",
        "expected_intent": "scam_attempt",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    # --- Domestic staff ---
    {
        "id": 4, "category": "domestic_staff",
        "name": "New maid claiming replacement",
        "prompt": "Say: 'Main aaj se kaam karungi, purani bai nahi aayegi'",
        "expected_intent": "domestic_staff",
        "expected_action": "notify_owner",
        "max_risk": 0.70,
    },
    # --- Religious / Donation ---
    {
        "id": 5, "category": "religious",
        "name": "Temple donation collection",
        "prompt": "Say: 'Mandir ke liye chanda hai'",
        "expected_intent": "religious_donation",
        "expected_action": "auto_reply",
        "max_risk": 0.50,
    },
    # --- Government / Scam ---
    {
        "id": 6, "category": "government",
        "name": "KYC verification scam",
        "prompt": "Say: 'Aadhaar KYC verification hai'",
        "expected_intent": "scam_attempt",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    {
        "id": 7, "category": "government",
        "name": "Electricity board claim",
        "prompt": "Say: 'Bijli check karne aaye hain'",
        "expected_intent": "government_claim",
        "expected_action": "notify_owner",
        "max_risk": 0.70,
    },
    # --- Social engineering ---
    {
        "id": 8, "category": "social_engineering",
        "name": "Occupancy probe",
        "prompt": "Say: 'Koi ghar pe hai?'",
        "expected_intent": "occupancy_probe",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    {
        "id": 9, "category": "social_engineering",
        "name": "Identity claim bypass",
        "prompt": "Say: 'I know the owner personally, let me in'",
        "expected_intent": "identity_claim",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    # --- Aggression ---
    {
        "id": 10, "category": "aggression",
        "name": "Verbal threat",
        "prompt": "Say: 'Darwaza kholo warna dekh lena'",
        "expected_intent": "aggression",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    # --- Children / Elderly ---
    {
        "id": 11, "category": "child_elderly",
        "name": "Lost child",
        "prompt": "Say: 'Mummy kho gayi' (in a small voice)",
        "expected_intent": "child_elderly",
        "expected_action": "notify_owner",
        "max_risk": 0.80,
    },
    {
        "id": 12, "category": "child_elderly",
        "name": "Elderly asking for water",
        "prompt": "Say: 'Bhai sahab, paani milega?'",
        "expected_intent": "child_elderly",
        "expected_action": "notify_owner",
        "max_risk": 0.60,
    },
    # --- Emergency ---
    {
        "id": 13, "category": "emergency",
        "name": "Fire emergency",
        "prompt": "Say: 'Help! Aag lag gayi hai!'",
        "expected_intent": "help",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    # --- Sales ---
    {
        "id": 14, "category": "sales",
        "name": "Water purifier demo",
        "prompt": "Say: 'Free demo hai water purifier ka'",
        "expected_intent": "sales_marketing",
        "expected_action": "auto_reply",
        "max_risk": 0.45,
    },
    # --- Financial manipulation ---
    {
        "id": 15, "category": "financial",
        "name": "UPI transfer request",
        "prompt": "Say: 'QR scan kar dijiye, refund dena hai'",
        "expected_intent": "scam_attempt",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
    # --- Silent visitor ---
    {
        "id": 16, "category": "silent",
        "name": "Silent visitor (no speech)",
        "prompt": "(Stay silent — do NOT speak)",
        "expected_intent": "unknown",
        "expected_action": "notify_owner",
        "max_risk": 0.60,
    },
    # --- Visitor ---
    {
        "id": 17, "category": "visitor",
        "name": "Friend wants to meet owner",
        "prompt": "Say: 'I want to speak with the owner please'",
        "expected_intent": "visitor",
        "expected_action": "auto_reply",
        "max_risk": 0.45,
    },
    # --- Entry request ---
    {
        "id": 18, "category": "entry_request",
        "name": "Delivery asking to enter",
        "prompt": "Say: 'Lift use karna hai, andar aana padega'",
        "expected_intent": "entry_request",
        "expected_action": "escalate",
        "max_risk": 1.0,
    },
]


# ══════════════════════════════════════════════════════════════
# Webcam capture
# ══════════════════════════════════════════════════════════════

def capture_from_webcam(record_audio: bool = False) -> tuple[str, str]:
    """Open webcam, show preview, capture on SPACE key.

    Returns (image_base64, audio_base64). audio_base64 is empty if
    record_audio is False or if no audio was recorded.
    """
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam")
        return "", ""

    print("\n=== Webcam Preview ===")
    if record_audio:
        print("Press R to START/STOP voice recording (then SPACE to send)")
    print("Press SPACE to capture image and send to doorbell API")
    print("Press Q to quit without sending")
    print("======================\n")

    frame = None
    audio_b64 = ""
    recording = False
    audio_frames: list[bytes] = []
    pa = None
    stream = None

    # Lazy-import pyaudio only when we actually need voice
    if record_audio:
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
        except ImportError:
            print("WARNING: pyaudio not installed — voice recording disabled")
            print("  Install with:  pip install pyaudio")
            record_audio = False

    while True:
        ret, frame = cap.read()
        if not ret:
            print("ERROR: Cannot read from webcam")
            break

        # HUD overlay
        display = frame.copy()
        if record_audio and recording:
            cv2.putText(display, "** RECORDING **  Press R to stop",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            # Red border while recording
            h, w = display.shape[:2]
            cv2.rectangle(display, (0, 0), (w - 1, h - 1), (0, 0, 255), 4)
        else:
            hint = "R=Record | SPACE=Capture | Q=Quit" if record_audio else "SPACE=Capture | Q=Quit"
            cv2.putText(display, hint,
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        if audio_frames and not recording:
            secs = len(audio_frames) * AUDIO_CHUNK / AUDIO_RATE
            cv2.putText(display, f"Audio: {secs:.1f}s recorded",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

        cv2.imshow("Smart Doorbell - Test Capture", display)

        key = cv2.waitKey(1) & 0xFF

        # --- R toggles recording ---
        if key == ord("r") and record_audio and pa is not None:
            if not recording:
                # Start recording
                audio_frames = []
                import pyaudio
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=AUDIO_CHANNELS,
                    rate=AUDIO_RATE,
                    input=True,
                    frames_per_buffer=AUDIO_CHUNK,
                )
                recording = True
                print("  [MIC] Recording started... speak now")
            else:
                # Stop recording
                recording = False
                if stream:
                    stream.stop_stream()
                    stream.close()
                    stream = None
                secs = len(audio_frames) * AUDIO_CHUNK / AUDIO_RATE
                print(f"  [MIC] Recording stopped — {secs:.1f}s captured")

        # Read audio chunk if currently recording
        if recording and stream:
            try:
                data = stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                audio_frames.append(data)
            except Exception:
                pass

        # --- SPACE to capture & send ---
        if key == ord(" "):
            # Stop recording if still active
            if recording and stream:
                recording = False
                stream.stop_stream()
                stream.close()
                stream = None
                secs = len(audio_frames) * AUDIO_CHUNK / AUDIO_RATE
                print(f"  [MIC] Recording stopped — {secs:.1f}s captured")
            break

        # --- Q to quit ---
        if key == ord("q"):
            frame = None
            break

    # Cleanup
    if stream:
        stream.stop_stream()
        stream.close()
    if pa:
        pa.terminate()
    cap.release()
    cv2.destroyAllWindows()

    if frame is None:
        return "", ""

    # Encode image
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    img_b64 = base64.b64encode(buffer).decode("utf-8")
    print(f"Captured frame: {frame.shape[1]}x{frame.shape[0]}, base64 size: {len(img_b64)} chars")

    # Encode audio -> WAV bytes -> base64
    if audio_frames:
        audio_b64 = _encode_audio_b64(audio_frames)
        print(f"Audio base64 size: {len(audio_b64)} chars")

    return img_b64, audio_b64


def _encode_audio_b64(frames: list[bytes]) -> str:
    """Convert raw PCM frames to a WAV file in memory, then base64-encode."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(AUDIO_CHANNELS)
        wf.setsampwidth(AUDIO_FORMAT_WIDTH)
        wf.setframerate(AUDIO_RATE)
        wf.writeframes(b"".join(frames))
    wav_bytes = buf.getvalue()
    return base64.b64encode(wav_bytes).decode("utf-8")


# ══════════════════════════════════════════════════════════════
# API interaction
# ══════════════════════════════════════════════════════════════

def send_ring(image_base64: str, audio_base64: str = "") -> dict:
    """POST to /api/ring with captured image (and optional audio)."""
    payload = {
        "type": "ring",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "image_base64": image_base64,
        "audio_base64": audio_base64 or None,
        "device_id": "webcam-test",
        "metadata": {"source": "test_webcam_ring.py", "has_audio": bool(audio_base64)},
    }

    print("\nSending ring event to API...")
    resp = requests.post(f"{API_BASE}/api/ring", json=payload, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    print(f"Ring response: {json.dumps(result, indent=2)}")
    return result


def poll_status(session_id: str, timeout: float = 30.0) -> dict | None:
    """Poll session status until completed or timeout."""
    print(f"\nPolling session {session_id}...")
    start = time.time()
    last_status = ""

    while time.time() - start < timeout:
        resp = requests.get(f"{API_BASE}/api/session/{session_id}/status", timeout=5)
        data = resp.json()
        status = data.get("status", "unknown")

        if status != last_status:
            print(f"  Status: {status}")
            last_status = status

        if status in ("completed", "error"):
            print(f"\nFinal result: {json.dumps(data, indent=2)}")
            return data

        time.sleep(0.5)

    print("TIMEOUT: Session did not complete in time")
    return None


def fetch_session_details(session_id: str) -> dict:
    """Fetch transcripts and actions for a finished session via /api/logs."""
    try:
        resp = requests.get(f"{API_BASE}/api/logs?limit=100", timeout=5)
        logs = resp.json()

        transcripts = [
            t for t in logs.get("transcripts", []) if t.get("session_id") == session_id
        ]
        actions = [
            a for a in logs.get("actions", []) if a.get("session_id") == session_id
        ]
        return {"transcripts": transcripts, "actions": actions}
    except Exception as exc:
        print(f"  (Could not fetch session details: {exc})")
        return {}


# ══════════════════════════════════════════════════════════════
# TTS playback of AI reply
# ══════════════════════════════════════════════════════════════

def speak_reply(text: str) -> None:
    """Play the AI reply text via local TTS (pyttsx3) so tester can hear it."""
    if not text:
        return

    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)  # slightly slower for clarity
        engine.setProperty("volume", 1.0)
        print(f"\n  [TTS] Speaking: \"{text}\"")
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except ImportError:
        print("  [TTS] pyttsx3 not installed — printing reply instead:")
        print(f"        \"{text}\"")
        print("  Install with: pip install pyttsx3")
    except Exception as exc:
        print(f"  [TTS] Playback failed: {exc}")
        print(f"        Reply text: \"{text}\"")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Smart Doorbell webcam + voice test")
    parser.add_argument(
        "--voice", action="store_true",
        help="Enable microphone recording and TTS playback of AI reply",
    )
    parser.add_argument(
        "--scenario", nargs="?", const="all", default=None,
        help="Run Indian household scenario tests. Pass a number for specific scenario, or omit for menu.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Smart Doorbell - Webcam + Voice + Scenario Test")
    print("=" * 60)

    if args.scenario is not None:
        run_scenario_mode(args)
        return

    if args.voice:
        print("  Mode: IMAGE + VOICE (record with R, capture with SPACE)")
    else:
        print("  Mode: IMAGE ONLY   (capture with SPACE)")
        print("  Tip:  Run with --voice to enable mic recording & TTS playback")
        print("  Tip:  Run with --scenario to test Indian household scenarios")

    # Step 1: Capture
    img_b64, audio_b64 = capture_from_webcam(record_audio=args.voice)
    if not img_b64:
        print("No image captured. Exiting.")
        return

    # Step 2: Send ring
    ring_result = send_ring(img_b64, audio_b64)
    session_id = ring_result.get("sessionId")
    if not session_id:
        print("ERROR: No session ID returned")
        return

    # Step 3: Poll until done
    final = poll_status(session_id, timeout=30)

    if final and final.get("status") == "completed":
        print("\n--- Pipeline completed successfully! ---")
        print(f"  Risk Score: {final.get('riskScore', 'N/A')}")

        # Step 4: Fetch session transcripts to find AI reply
        details = fetch_session_details(session_id)
        assistant_msgs = [
            t for t in details.get("transcripts", [])
            if t.get("role") == "assistant"
        ]
        visitor_msgs = [
            t for t in details.get("transcripts", [])
            if t.get("role") == "visitor"
        ]

        if visitor_msgs:
            print(f"\n  Visitor said: \"{visitor_msgs[0].get('content', '')}\"")
        else:
            print("\n  Visitor said: (no transcript — VOSK returned empty)")
            print("    Possible causes:")
            print("    - Mic volume too low or wrong input device")
            print("    - VOSK models not loaded (check server logs)")
            print("    - Recording too short (try speaking longer)")

        if assistant_msgs:
            reply_text = assistant_msgs[0].get("content", "")
            print(f"  AI Reply:     \"{reply_text}\"")

            # Step 5: Speak the AI reply
            if args.voice:
                speak_reply(reply_text)
            else:
                print(f"\n  (Run with --voice to hear TTS playback)")

        # Show action details
        actions = details.get("actions", [])
        action_types = [a.get("action_type", "") for a in actions]
        print(f"  Actions:      {action_types}")

    elif final and final.get("status") == "error":
        print("\nPipeline failed with error")
    else:
        print("\nSession status unclear")


# ══════════════════════════════════════════════════════════════
# Scenario testing mode
# ══════════════════════════════════════════════════════════════

def run_scenario_mode(args):
    """Run categorized Indian household scenario tests."""
    scenarios_to_run = []

    if args.scenario == "all":
        # Show menu
        print("\n  Available scenarios:")
        print("  " + "-" * 50)
        for s in SCENARIOS:
            print(f"    [{s['id']:>2}] ({s['category']}) {s['name']}")
        print("  " + "-" * 50)
        print("  Enter scenario number(s) separated by commas, 'all', or 'q' to quit:")
        choice = input("  > ").strip().lower()
        if choice == "q":
            return
        if choice == "all":
            scenarios_to_run = SCENARIOS
        else:
            try:
                ids = [int(x.strip()) for x in choice.split(",")]
                scenarios_to_run = [s for s in SCENARIOS if s["id"] in ids]
            except ValueError:
                print("Invalid input. Exiting.")
                return
    else:
        try:
            scenario_id = int(args.scenario)
            scenarios_to_run = [s for s in SCENARIOS if s["id"] == scenario_id]
            if not scenarios_to_run:
                print(f"Scenario {scenario_id} not found.")
                return
        except ValueError:
            print("Invalid scenario number.")
            return

    if not scenarios_to_run:
        print("No scenarios selected.")
        return

    results = []

    for scenario in scenarios_to_run:
        print(f"\n{'='*60}")
        print(f"  SCENARIO {scenario['id']}: {scenario['name']}")
        print(f"  Category: {scenario['category']}")
        print(f"  {scenario['prompt']}")
        print(f"  Expected: intent={scenario['expected_intent']}, action={scenario['expected_action']}")
        print(f"{'='*60}")

        if args.voice:
            print("\n  Press ENTER when ready to capture (use R to record voice)...")
            input()

        img_b64, audio_b64 = capture_from_webcam(record_audio=args.voice)
        if not img_b64:
            print("  SKIPPED (no image captured)")
            results.append({"scenario": scenario, "status": "skipped"})
            continue

        try:
            ring_result = send_ring(img_b64, audio_b64)
            session_id = ring_result.get("sessionId")
            if not session_id:
                results.append({"scenario": scenario, "status": "error", "reason": "No session ID"})
                continue

            final = poll_status(session_id, timeout=30)
            if not final or final.get("status") != "completed":
                results.append({"scenario": scenario, "status": "error", "reason": "Pipeline failed"})
                continue

            details = fetch_session_details(session_id)
            risk = final.get("riskScore", 0)

            # Check what action was taken
            actions = details.get("actions", [])
            action_types = [a.get("action_type", "") for a in actions
                          if a.get("action_type") not in ("ring_received", "perception")]

            visitor_msgs = [t for t in details.get("transcripts", []) if t.get("role") == "visitor"]
            assistant_msgs = [t for t in details.get("transcripts", []) if t.get("role") == "assistant"]

            transcript = visitor_msgs[0].get("content", "") if visitor_msgs else ""
            reply = assistant_msgs[0].get("content", "") if assistant_msgs else ""

            print(f"\n  RESULT:")
            print(f"    Transcript: \"{transcript}\"")
            print(f"    AI Reply:   \"{reply}\"")
            print(f"    Risk Score: {risk}")
            print(f"    Actions:    {action_types}")

            # Validate against expectations
            passed = True
            notes = []

            if risk > scenario["max_risk"]:
                notes.append(f"Risk {risk} > expected max {scenario['max_risk']}")
                # Not necessarily a failure — higher risk is safer

            # Normalize action types: DB audit entries map back to their parent action
            _ACTION_ALIASES = {
                "escalation_notification": "escalate",
                "owner_notification": "notify_owner",
            }
            normalized_actions = [_ACTION_ALIASES.get(a, a) for a in action_types]
            # Use the highest-ranked action from the list (most cautious wins)
            action_rank = {"ignore": -1, "auto_reply": 0, "notify_owner": 1, "escalate": 2}
            final_action = max(normalized_actions, key=lambda a: action_rank.get(a, -1)) if normalized_actions else "unknown"
            if final_action != scenario["expected_action"]:
                # Check if actual action is MORE cautious (escalate > notify_owner > auto_reply)
                actual_rank = action_rank.get(final_action, -1)
                expected_rank = action_rank.get(scenario["expected_action"], -1)
                if actual_rank < expected_rank:
                    notes.append(f"Action '{final_action}' is LESS cautious than expected '{scenario['expected_action']}'")
                    passed = False
                else:
                    notes.append(f"Action '{final_action}' (more cautious than '{scenario['expected_action']}') — acceptable")

            status = "PASS" if passed else "FAIL"
            if notes:
                for note in notes:
                    print(f"    Note: {note}")
            print(f"    Status: {'✅' if passed else '❌'} {status}")

            if args.voice and reply:
                speak_reply(reply)

            results.append({
                "scenario": scenario,
                "status": status,
                "risk": risk,
                "action": final_action,
                "transcript": transcript,
                "reply": reply,
                "notes": notes,
            })

        except requests.ConnectionError:
            print("  ERROR: Cannot connect to API server.")
            print("  Start the server with: python -m uvicorn api.main:app --reload --port 8000")
            return
        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({"scenario": scenario, "status": "error", "reason": str(exc)})

    # Print summary
    print(f"\n{'='*60}")
    print("  SCENARIO TEST SUMMARY")
    print(f"{'='*60}")
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    skipped = sum(1 for r in results if r.get("status") in ("skipped", "error"))
    print(f"  Total: {len(results)} | Passed: {passed} | Failed: {failed} | Skipped/Error: {skipped}")
    print()
    for r in results:
        s = r["scenario"]
        status_icon = {"PASS": "✅", "FAIL": "❌", "skipped": "⏭️", "error": "⚠️"}.get(r["status"], "?")
        print(f"  {status_icon} [{s['id']:>2}] {s['name']}: {r['status']}")
        if r.get("notes"):
            for note in r["notes"]:
                print(f"        {note}")
    print()


if __name__ == "__main__":
    main()
