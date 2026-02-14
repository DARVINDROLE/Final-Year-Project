"""
Test script: Captures a frame from your webcam and sends it to /api/ring.
Run this while the API server is running (uvicorn api.main:app --port 8000).

Usage:
    python api/tests/test_webcam_ring.py

Requirements:
    pip install opencv-python requests
"""

import base64
import json
import time

import cv2
import requests

API_BASE = "http://127.0.0.1:8000"


def capture_from_webcam() -> str:
    """Open webcam, show preview, capture on SPACE key, return base64 JPEG."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Cannot open webcam")
        return ""

    print("=== Webcam Preview ===")
    print("Press SPACE to capture and send to doorbell API")
    print("Press Q to quit without sending")
    print("======================")

    frame = None
    while True:
        ret, frame = cap.read()
        if not ret:
            print("ERROR: Cannot read from webcam")
            break

        # Show preview with instructions
        display = frame.copy()
        cv2.putText(display, "SPACE = Capture & Ring | Q = Quit", (10, 30),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Smart Doorbell - Test Capture", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):  # SPACE
            break
        elif key == ord("q"):
            frame = None
            break

    cap.release()
    cv2.destroyAllWindows()

    if frame is None:
        return ""

    # Encode frame as JPEG base64
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buffer).decode("utf-8")
    print(f"Captured frame: {frame.shape[1]}x{frame.shape[0]}, base64 size: {len(b64)} chars")
    return b64


def send_ring(image_base64: str) -> dict:
    """POST to /api/ring with captured image."""
    payload = {
        "type": "ring",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "image_base64": image_base64,
        "audio_base64": None,
        "device_id": "webcam-test",
        "metadata": {"source": "test_webcam_ring.py"},
    }

    print("\nSending ring event to API...")
    resp = requests.post(f"{API_BASE}/api/ring", json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    print(f"Ring response: {json.dumps(result, indent=2)}")
    return result


def poll_status(session_id: str, timeout: float = 15.0):
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


def main():
    print("=" * 50)
    print("  Smart Doorbell - Webcam Test")
    print("=" * 50)

    # Step 1: Capture
    image_b64 = capture_from_webcam()
    if not image_b64:
        print("No image captured. Exiting.")
        return

    # Step 2: Send ring
    ring_result = send_ring(image_b64)
    session_id = ring_result.get("sessionId")
    if not session_id:
        print("ERROR: No session ID returned")
        return

    # Step 3: Poll until done
    final = poll_status(session_id)

    if final and final.get("status") == "completed":
        print("\n✓ Pipeline completed successfully!")
        print(f"  Risk Score: {final.get('riskScore', 'N/A')}")
    elif final and final.get("status") == "error":
        print("\n✗ Pipeline failed with error")
    else:
        print("\n? Session status unclear")


if __name__ == "__main__":
    main()
