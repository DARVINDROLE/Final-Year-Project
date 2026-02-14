"""
Test script: Captures video + audio from webcam/mic and sends to /api/ring.
After pipeline completes, reads back the AI reply and plays it via TTS.

Run this while the API server is running:
    python -m uvicorn api.main:app --reload --port 8000

Usage:
    python api/tests/test_webcam_ring.py          # image only (original mode)
    python api/tests/test_webcam_ring.py --voice   # image + voice recording + TTS reply

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
    args = parser.parse_args()

    print("=" * 55)
    print("  Smart Doorbell - Webcam + Voice Test")
    print("=" * 55)

    if args.voice:
        print("  Mode: IMAGE + VOICE (record with R, capture with SPACE)")
    else:
        print("  Mode: IMAGE ONLY   (capture with SPACE)")
        print("  Tip:  Run with --voice to enable mic recording & TTS playback")

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

    elif final and final.get("status") == "error":
        print("\nPipeline failed with error")
    else:
        print("\nSession status unclear")


if __name__ == "__main__":
    main()
