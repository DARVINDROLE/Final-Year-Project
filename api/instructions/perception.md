# Perception Agent — Instruction Contract
# ========================================
#
# ROLE:
#   The Perception Agent is the **multimodal sensing layer** of the Smart Doorbell
#   Multi-Agent System. It is the FIRST agent in the pipeline. It receives raw
#   sensor data (camera snapshot, microphone audio) from the Orchestrator and
#   produces a structured, machine-readable perception report for downstream agents.
#
# WHAT IT COMBINES (consolidated from separate agents):
#   - Object detection (YOLOv8n general model)
#   - Weapon detection (custom-trained YOLOv8 model)
#   - Speech-to-Text transcription (VOSK small model)
#   - Emotion/tone inference (rule-based from transcript)
#   - Anti-spoofing heuristics (cross-modal consistency checks)
#
# WHY COMBINED:
#   All of these are sensor-input processors that operate before reasoning.
#   Combining them reduces inter-agent latency and message-passing overhead.
#   A single multimodal perception layer produces one clean output for the
#   Intelligence Agent to reason over.
#
# ─────────────────────────────────────────
# SECTION 1 — INPUTS
# ─────────────────────────────────────────
#
# The agent receives a RingEvent from the Orchestrator with:
#   - session_id   : Unique session identifier (e.g. "visitor_a3f7c891")
#   - image_path   : Path to the doorbell camera snapshot (JPEG), or empty string
#   - audio_path   : Path to recorded audio clip (WAV), or None
#   - device_id    : Identifier of the doorbell device
#   - metadata     : Optional dict with signal info (e.g. {"rssi": -50})
#
# ─────────────────────────────────────────
# SECTION 2 — PROCESSING PIPELINE
# ─────────────────────────────────────────
#
# Step 1 — General Object Detection (YOLOv8n)
#   - Model: yolov8n.pt (Nano variant, CPU-optimized)
#   - Input: image_path (imgsz=416)
#   - Extract: list of detected objects [{label, conf}]
#   - Determine: person_detected (True if any "person" with conf >= 0.4)
#   - Determine: vision_confidence (highest "person" confidence, or 0.0)
#   - Fallback: If image_path is empty or model unavailable, return
#     person_detected=False, objects=[], vision_confidence=0.0
#
# Step 2 — Weapon Detection (Custom YOLOv8 model)
#   - Model: weapon_detection/runs/detect/Normal_Compressed/weights/best.pt
#   - Input: same image_path (imgsz=416)
#   - Extract: weapon_detected (bool), weapon_confidence (float),
#     weapon_labels (list of detected weapon class names)
#   - Fallback: If model unavailable or image empty, return
#     weapon_detected=False, weapon_confidence=0.0, weapon_labels=[]
#
# Step 3 — Speech-to-Text (VOSK)
#   - Model: vosk-model-small-en-us (auto-downloaded on first use)
#   - Input: audio_path (WAV format, 16kHz mono preferred)
#   - Output: transcript (str), stt_confidence (float 0.0–1.0)
#   - SKIP this step entirely if audio_path is None or empty
#   - Fallback: On STT failure, return transcript="", stt_confidence=0.0
#
# Step 4 — Emotion Inference
#   - Method: Rule-based keyword analysis on transcript text
#   - Categories: "aggressive", "distressed", "neutral"
#   - Keywords for aggressive: angry, threatening, offensive language
#   - Keywords for distressed: help, emergency, please, scared
#   - Default: "neutral"
#
# Step 5 — Anti-Spoof Score Computation
#   - Purpose: Detect if the doorbell press may be spoofed (no real person)
#   - Formula:
#     * No person detected → anti_spoof_score = 0.9 (high suspicion)
#     * Person detected but low confidence (< 0.5) → +0.3
#     * Audio present but no meaningful transcript → +0.2
#     * Audio absent entirely → +0.1
#   - Range: 0.0 (genuine) to 1.0 (likely spoofed)
#
# ─────────────────────────────────────────
# SECTION 3 — OUTPUT CONTRACT
# ─────────────────────────────────────────
#
# Must return a PerceptionOutput matching this exact schema:
#
#   {
#     "session_id": "visitor_a3f7c891",
#     "person_detected": true,
#     "objects": [{"label": "person", "conf": 0.92}, {"label": "package", "conf": 0.78}],
#     "vision_confidence": 0.92,
#     "transcript": "I have an Amazon delivery",
#     "stt_confidence": 0.85,
#     "emotion": "neutral",
#     "anti_spoof_score": 0.0,
#     "weapon_detected": false,
#     "weapon_confidence": 0.0,
#     "weapon_labels": [],
#     "image_path": "data/snaps/visitor_a3f7c891.jpg",
#     "timestamp": "2026-02-14T13:00:00+00:00"
#   }
#
# This output is consumed directly by the Intelligence Agent.
#
# ─────────────────────────────────────────
# SECTION 4 — PERFORMANCE & SAFETY CONSTRAINTS
# ─────────────────────────────────────────
#
# 1. CPU-only execution. No GPU dependencies allowed.
# 2. All inference MUST run inside asyncio.to_thread() to avoid blocking
#    the event loop.
# 3. Each step has an 8-second timeout (asyncio.wait_for). If a step
#    exceeds this, return best-effort partial results rather than crashing.
# 4. Models are loaded once at startup, not per-request.
# 5. If DOORBELL_DISABLE_MODELS=1 is set, skip model loading entirely
#    (used for testing without ML dependencies).
# 6. Written output files go ONLY to data/snaps/ (snapshots) or
#    data/tmp/{session_id}/ (temporary audio processing).
# 7. Never delete files. Never write outside the data/ directory.
# 8. Log errors to data/logs/perception_agent.log, not to stdout.
