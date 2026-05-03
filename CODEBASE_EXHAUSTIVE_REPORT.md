# Smart Doorbell Codebase: Exhaustive Implementation Report

## Scope and Grounding

This document describes the project as it is implemented in the repository, not as an idealized architecture. The active runtime path is the FastAPI application in `api/main.py`, backed by the orchestrator in `api/orchestrator.py`, the runtime agents in `api/agents/`, SQLite persistence in `api/db.py`, and the React frontend in `src/`. The older `api/index.py` file still exists because `vercel.json` rewrites API traffic there for serverless deployment, but the local and test-backed implementation path is `api/main.py`.

The repository therefore contains three categories of code:

1. Active product code that powers the running system.
2. Supporting or governance code that constrains agent behavior and documents policy.
3. Legacy or experimental code paths kept for compatibility, prior deployments, or model experimentation.

---

## 1. Project Overview (System Level)

### 1.1 What the system does

The project implements an AI-enabled smart doorbell system for Indian households. At runtime, it does four things in one end-to-end flow:

1. Captures a visitor image and optionally visitor speech from the door interface.
2. Interprets the visitor context using vision, speech recognition, intent classification, and risk scoring.
3. Decides whether to auto-reply, notify the owner, or escalate to security.
4. Stores the full interaction trail in SQLite and exposes it to the owner dashboard in near real time.

The user-facing product behavior is split between two web experiences:

1. A visitor-side doorbell page at `/doorbell`, implemented in `src/pages/Doorbell.tsx`.
2. An owner-side dashboard at `/dashboard`, implemented in `src/pages/Dashboard.tsx`.

### 1.2 Core problem the system solves

The system is designed to reduce the cognitive and physical load of answering the door, especially in scenarios where the homeowner is unavailable, cautious, or remote. The code specifically targets several real household problems:

1. Unwanted interruptions from low-risk visitors such as deliveries, sales visitors, or donation requests.
2. Social-engineering attacks such as OTP scams, financial fraud prompts, occupancy probing, and false identity claims.
3. Suspicious or threatening visitors, including cases where a weapon may be visible.
4. Remote interaction needs, where the owner wants to observe and answer visitors from a dashboard rather than opening the door.

### 1.3 End-to-end workflow

The implemented pipeline is:

1. A visitor presses the ring button on the doorbell page.
2. The browser captures one image from the webcam and records about three seconds of microphone audio.
3. The frontend sends a `POST /api/ring` request to the FastAPI backend.
4. The backend saves the image and audio, creates a session, and runs the full perception -> intelligence -> decision -> action pipeline synchronously.
5. The pipeline produces a spoken greeting or security response.
6. The owner dashboard is notified through the `owner` WebSocket channel.
7. The visitor can continue the conversation by speaking or typing; the frontend sends follow-up text through `POST /api/ai-reply`.
8. The owner may respond from the dashboard through `POST /api/owner-reply`, which is rebroadcast to the visitor-side session WebSocket.
9. All session state, transcripts, actions, and visitor metadata are written to SQLite.
10. If live camera streaming is active, the visitor page continuously uploads frames, and the backend performs periodic live weapon detection and person-presence checks in parallel with the main conversational flow.

### 1.4 Key capabilities actually present in code

#### Detection

Detection is implemented in two layers:

1. Snapshot-time perception in `api/agents/perception_agent.py`, which performs general object detection, weapon detection, speech recognition, emotion inference, context flag detection, and anti-spoof scoring.
2. Live-stream frame analysis in `api/main.py`, which periodically re-runs person detection and weapon detection on streamed JPEG frames.

#### Conversation

Conversation is implemented through:

1. Speech-to-text through Groq Whisper when `GROQ_API_KEY` is available.
2. Offline fallback speech recognition through VOSK models if present in `models/`.
3. Intent classification and risk scoring in `api/agents/intelligence_agent.py`.
4. Optional LLM response generation through Groq chat completions using `api/prompts/groq_system_prompt.txt`.
5. Multi-turn follow-up conversation through `Orchestrator.handle_ai_reply()`.

#### Alerting

Alerting occurs through three implemented mechanisms:

1. Action rows persisted in the `actions` table.
2. WebSocket broadcasts to the owner dashboard channel `owner`.
3. TTS generation for immediate visitor-facing spoken responses.

#### Logging

Logging exists at two levels:

1. Operational logging through Python `logging` and `data/logs/agent_errors.log`.
2. Structured audit logging through SQLite tables: `sessions`, `transcripts`, `visitors`, and `actions`.

### 1.5 System boundaries

#### Inside the repository and active runtime boundary

The following responsibilities are implemented inside this codebase:

1. Browser-based capture of image, microphone audio, and continuous camera frames.
2. Backend orchestration and business rules.
3. Local object and weapon detection using YOLO models when weights are available.
4. Local SQLite persistence.
5. Real-time owner notification over WebSocket.
6. TTS file generation and static serving.
7. Owner authentication and member management.

#### Outside the codebase or delegated to external dependencies

The following are not implemented internally and depend on external libraries or services:

1. Groq-hosted Whisper transcription.
2. Groq-hosted LLM chat completion.
3. Browser device drivers for webcam and microphone access.
4. Actual hardware relay or smart lock control.
5. Push notification services, SMS gateways, or email delivery systems.
6. TLS termination, reverse proxying, or hardened production deployment networking.

---

## 2. Codebase Structure (Folder and File Level)

### 2.1 Root-level structure

```text
/
  agents.md
  claude.md
  README.md
  PROJECT_WORKFLOW.md
  QUICK_REFERENCE.md
  FIXES_SUMMARY.md
  RESOLUTION_REPORT.md
  plan.md
  projects.md
  scenarios.md
  logs.txt
  debug_vosk.py
  test_fixes.py
  test_groq.py
  test_weapon_model.py
  package.json
  bun.lockb
  components.json
  eslint.config.js
  index.html
  postcss.config.js
  tailwind.config.ts
  tsconfig.json
  tsconfig.app.json
  tsconfig.node.json
  vite.config.ts
  vercel.json
  requirements.txt
  api/
  src/
  public/
  electron/
  data/
  captures/
  models/
  weapon_detection/
  fyp-api/
```

### 2.2 Root files and responsibilities

#### Governance and agent-safety files

- `claude.md`: repository-level rules for coding agents, including non-destructive behavior, database safety, subprocess safety, and human approval guidance.
- `agents.md`: runtime safety rules for project agents, including concurrency limits, disk constraints, escalation rules, and migration restrictions.

These files are not cosmetic. The runtime agent design mirrors them: `BaseAgent` in `api/agents/base_agent.py` refuses to run if the required agent instruction file is missing.

#### Build and frontend configuration files

- `package.json`: defines the React and Vite frontend dependencies and scripts.
- `vite.config.ts`: configures the Vite dev server on port `8080` and proxies `/api` requests to `http://127.0.0.1:8000`.
- `tailwind.config.ts`, `postcss.config.js`, `components.json`, `eslint.config.js`, `tsconfig*.json`: style system, UI component generation, linting, and TypeScript compilation configuration.
- `vercel.json`: rewrites `/api/*` requests to `api/index.py`, which is important because it means the Vercel deployment path targets the legacy monolithic API file rather than the active local FastAPI file.

#### Documentation and planning files

- `README.md`: main developer-facing overview of architecture, setup, routes, endpoints, and tests.
- `PROJECT_WORKFLOW.md`, `QUICK_REFERENCE.md`, `FIXES_SUMMARY.md`, `RESOLUTION_REPORT.md`, `plan.md`, `projects.md`, `scenarios.md`: human-authored planning and reporting artifacts. They are not imported into the active runtime, but comments and tests show that `scenarios.md` informed the Indian-household risk logic.

#### Ad hoc scripts and test helpers

- `debug_vosk.py`: manual debugging helper for speech recognition.
- `test_fixes.py`, `test_groq.py`, `test_weapon_model.py`: standalone validation scripts outside the main `api/tests/` suite.
- `requirements.txt`: a smaller root dependency file, likely inherited from earlier deployment paths, than the fuller backend dependency set in `api/requirements.txt`.

### 2.3 Backend structure: `api/`

```text
api/
  __init__.py
  main.py
  index.py
  orchestrator.py
  db.py
  models.py
  requirements.txt
  agents/
    __init__.py
    base_agent.py
    perception_agent.py
    intelligence_agent.py
    decision_agent.py
    action_agent.py
  instructions/
    README.md
    agents.md
    action.md
    decision.md
    intelligence.md
    orchestrator.md
    perception.md
  policies/
    policy.yaml
  prompts/
    groq_system_prompt.txt
  tests/
    test_all_agents.py
    test_intelligence_decision.py
    test_main.py
    test_perception.py
    test_webcam_ring.py
  utils/
    __init__.py
    hindi_normalize.py
    tts.py
```

#### `api/main.py`

Primary FastAPI application. Responsibilities:

1. Creates the FastAPI app and CORS middleware.
2. Mounts static file directories for snapshots, TTS output, and member photos.
3. Builds and stores the `Orchestrator` on startup.
4. Exposes authentication, member-management, ring, TTS, transcription, session, log, streaming, snapshot, and WebSocket endpoints.
5. Owns the live frame state dictionaries used for MJPEG and snapshot streaming.
6. Runs the inactivity checker that auto-ends visitor sessions when no person is visible.

#### `api/orchestrator.py`

Central coordinator. Responsibilities:

1. Creates and initializes the database.
2. Owns one instance each of `PerceptionAgent`, `IntelligenceAgent`, `DecisionAgent`, and `ActionAgent`.
3. Enforces `max_concurrent_sessions = 2` using `asyncio.Semaphore`.
4. Saves inbound image and audio files.
5. Creates and updates session records.
6. Runs the entire pipeline synchronously for `POST /api/ring`.
7. Persists perception output into transcripts, visitor metadata, and action rows.
8. Supports follow-up AI conversation via `handle_ai_reply()`.
9. Supports isolated STT via `transcribe_audio()`.

#### `api/db.py`

SQLite data-access layer. Responsibilities:

1. Initializes all database tables.
2. Handles session creation and updates.
3. Adds transcripts and action rows.
4. Stores visitor image path and summary.
5. Handles owner registration, password hashing, token creation, token verification, and logout token deletion.
6. Handles member CRUD operations.
7. Returns recent logs and session detail objects.

#### `api/models.py`

Pydantic schema definitions for all major backend payloads:

1. `RingEvent`
2. `ObjectDetection`
3. `PerceptionOutput`
4. `IntelligenceOutput`
5. `DecisionOutput`
6. `ActionRequest`
7. `AiReplyRequest`
8. `ActionResult`

#### `api/index.py`

Legacy monolithic FastAPI implementation built around an in-memory `SmartDoorbell` class and `langchain_groq`. It still matters because:

1. `vercel.json` points `/api/*` rewrites to this file.
2. It represents an older architecture before the multi-agent orchestrator and SQLite-backed audit trail.
3. It has less capability than `api/main.py`: no SQLite persistence, no agent pipeline, no live frame streaming, no member management, and weaker security separation.

#### `api/agents/`

- `base_agent.py`: loads and logs instruction files at startup; all runtime agents inherit from it.
- `perception_agent.py`: vision, STT, emotion, anti-spoof, context flags, snapshot annotation.
- `intelligence_agent.py`: intent classification, risk scoring, escalation requirement, canned or LLM-generated response.
- `decision_agent.py`: 12-rule business decision layer.
- `action_agent.py`: TTS generation, notification payload assembly, action logging.

#### `api/instructions/`

This directory is part of the runtime contract, not just developer documentation. `BaseAgent` requires these files to exist. Each file captures the human-authored behavioral policy for the corresponding agent.

#### `api/policies/policy.yaml`

Configurable decision thresholds and documented rule ordering for the decision layer.

#### `api/prompts/groq_system_prompt.txt`

System prompt that constrains LLM-generated replies. It explicitly prohibits revealing personal details, internal system details, occupancy, OTPs, financial information, or access permissions.

#### `api/tests/`

Behavioral verification for:

1. Individual agent logic.
2. Intelligence and decision integration.
3. FastAPI endpoint behavior.
4. Manual webcam scenario testing.

### 2.4 Frontend structure: `src/`

```text
src/
  App.tsx
  App.css
  index.css
  main.tsx
  vite-env.d.ts
  components/
    NavLink.tsx
    RingButton.tsx
    StatusIndicator.tsx
    TranscriptDisplay.tsx
    VisitorCard.tsx
    ui/
  contexts/
    AuthContext.tsx
  hooks/
    useAuth.ts
    use-mobile.tsx
    use-toast.ts
    useSpeechRecognition.ts
  lib/
    api.ts
    utils.ts
  pages/
    Index.tsx
    Login.tsx
    Doorbell.tsx
    Dashboard.tsx
    Members.tsx
    VisitorHistory.tsx
    NotFound.tsx
```

#### `src/App.tsx`

Frontend routing root. Responsibilities:

1. Creates the React Query client.
2. Wraps the app in tooltip and toast providers.
3. Wraps routes in `AuthProvider`.
4. Protects owner routes with `ProtectedRoute`.

#### `src/lib/api.ts`

The frontend network integration layer. Responsibilities:

1. Resolves the backend base URL dynamically for local or LAN access.
2. Stores the auth token in `localStorage`.
3. Implements all REST calls used by the UI.
4. Converts raw `/api/logs` payloads into UI-friendly `Visitor` objects.
5. Implements backend TTS playback with browser speech-synthesis fallback.
6. Opens WebSocket connections for owner and session channels.

#### `src/pages/Doorbell.tsx`

Visitor-facing interface. Responsibilities:

1. Requests webcam and microphone access.
2. Captures an image screenshot.
3. Records three seconds of initial audio before the first ring submission.
4. Opens a per-session WebSocket to receive owner replies and session-end events.
5. Streams continuous webcam frames to `/api/session/{id}/stream-frame` at 200 ms intervals.
6. Sends follow-up visitor messages via text or recorded voice.
7. Plays AI or owner replies with backend-generated audio or browser TTS.

#### `src/pages/Dashboard.tsx`

Owner-facing operational console. Responsibilities:

1. Loads visitor logs.
2. Connects to the `owner` WebSocket channel.
3. Shows new rings, active sessions, live stream polling, and weapon alerts.
4. Lets the owner inspect transcripts and respond by text or voice.
5. Uses a snapshot polling fallback through `/api/stream/{id}/snapshot` to display live visitor imagery.

#### `src/pages/Members.tsx`

Household member management interface. Responsibilities:

1. Lists member records.
2. Adds new members with optional face photo.
3. Edits member metadata.
4. Toggles `permitted` access status.
5. Deletes member records.

#### `src/pages/VisitorHistory.tsx`

Historical browsing UI. Responsibilities:

1. Loads visit history.
2. Filters by visitor type and search terms.
3. Groups sessions by date.
4. Opens detailed transcript dialogs.

#### `src/pages/Index.tsx`

Landing page that directs the user to the visitor entrance or owner login.

#### `src/pages/Login.tsx`

Combined registration and login page for owner accounts.

#### `src/components/`

Reusable UI building blocks. The most behaviorally significant one is `VisitorCard.tsx`, which renders status, type, timestamps, image preview, and quick actions for each visitor session.

### 2.5 Other major directories

#### `public/`

- `robots.txt`: static asset for web crawler policy.

#### `electron/`

- `main.cjs`: a minimal Electron shell that loads the frontend from `http://localhost:8080` in development or `dist/index.html` in production. It does not embed backend logic; it only wraps the UI.

#### `weapon_detection/`

Separate experimental or supporting scripts for the weapon model:

- `live_detection.py`: OpenCV webcam loop with YOLO-based live weapon detection and optional headless mode.
- `detecting-images.py`: one-off image detection and annotation utility.
- `models/` and `runs/`: model artifacts and training/inference outputs.

This directory is not the main runtime path for the web application, but its trained weights are loaded by `PerceptionAgent` from `weapon_detection/runs/detect/Normal_Compressed/weights/best.pt`.

#### `models/`

Holds offline VOSK speech-recognition models. The perception agent searches here for Indian English and Hindi models.

#### `data/`

Runtime-generated data. Important subdirectories:

- `data/snaps/`: saved visitor images and annotated snapshots.
- `data/tts/`: generated audio files and fallback text files.
- `data/logs/`: error and incident logs.
- `data/members/`: member face photos.
- `data/tmp/transcribe/`: temporary transcription audio files.
- `data/tmp/visitor_<session>/`: per-session temporary audio directories.

These are part of the active runtime and are served by FastAPI static mounts.

#### `captures/`

Manual or historical capture artifacts. Not part of the backend pipeline.

#### `fyp-api/`

Local Python virtual environment for the project. It is environment state, not source code.

---

## 3. Module-by-Module Deep Breakdown

### 3A. Vision Module (YOLO and detection)

#### 3A.1 Model loading logic

The perception layer is initialized in `PerceptionAgent.__init__()`.

It attempts to load three models or model families:

1. General object detector: `yolov8n.pt` from the repository root.
2. Weapon detector: `weapon_detection/runs/detect/Normal_Compressed/weights/best.pt`.
3. VOSK speech models from `models/`.

Model loading is guarded by two environment flags:

1. `DOORBELL_DISABLE_MODELS=1`: disables all heavy model loading.
2. `DOORBELL_DISABLE_YOLO=1`: disables YOLO loading only.

If the general YOLO model is not available, the code intentionally returns a stub result that assumes a person is present with confidence `0.6`. This avoids breaking the whole pipeline when the model weights are absent.

#### 3A.2 Input pipeline

There are two image input pipelines.

##### Snapshot pipeline

1. The doorbell frontend grabs a webcam screenshot.
2. The screenshot is base64-encoded in the browser.
3. `POST /api/ring` receives that payload.
4. The orchestrator decodes and saves the image to `data/snaps/{session_id}.jpg`.
5. `PerceptionAgent._detect_objects_sync()` runs YOLO on the saved image path.
6. `PerceptionAgent._weapon_detect_sync()` runs the weapon model on the same image path.

##### Live frame pipeline

1. The visitor page continuously calls `Webcam.getScreenshot()`.
2. Every 200 ms, it sends a base64-encoded JPEG frame to `POST /api/session/{session_id}/stream-frame`.
3. The backend decodes the frame bytes into an in-memory NumPy array using OpenCV or Pillow fallback.
4. The backend performs periodic person-detection and weapon-detection scans on these in-memory arrays.

#### 3A.3 Inference flow

For the main snapshot path:

1. `PerceptionAgent.process()` calls `_detect_objects_sync()` inside `asyncio.to_thread()`.
2. The general YOLO predictor runs with `imgsz=416`, `device="cpu"`, `half=False`, `verbose=False`.
3. Each detection is converted into `ObjectDetection(label, conf)`.
4. The agent records the maximum confidence observed and whether any label was `person`.
5. The same process is repeated for the weapon model, using `imgsz=640` and a default threshold of `0.55`.

For live frames:

1. `_run_person_detection_on_frame()` uses the general YOLO model with `classes=[0]` so only COCO class `person` is tested.
2. `_run_weapon_detection_on_frame()` runs the weapon detector and collects labels and top confidence.

#### 3A.4 Output structure

The structured vision output is folded into `PerceptionOutput`, which includes:

1. `person_detected`
2. `objects`
3. `vision_confidence`
4. `weapon_detected`
5. `weapon_confidence`
6. `weapon_labels`
7. `num_persons`
8. `face_visible`
9. `image_path`

#### 3A.5 Threshold logic

The implemented thresholds are:

1. Main weapon detection threshold: `0.55`.
2. Live stream weapon detection threshold: `WEAPON_CONF_THRESHOLD = 0.55`.
3. Live alert confirmation streak: `WEAPON_CONSECUTIVE_HITS = 2`.
4. Person detection confidence threshold in live mode: `0.40`.
5. Face-visible heuristic threshold: best detected person confidence must be at least `0.35`.

#### 3A.6 Edge optimizations and safety defaults

The code makes several explicit optimizations for CPU-bound or constrained hardware use:

1. All model inference is pushed into `asyncio.to_thread()` so the main event loop is not blocked.
2. General YOLO uses the smaller `yolov8n` checkpoint rather than a larger model.
3. Live frame scans are rate-limited instead of running on every incoming frame.
4. Frame decoding is in memory, avoiding disk I/O for live stream analysis.
5. Weapon alerts require consecutive hits to reduce single-frame false positives.

The safety defaults are deliberately conservative:

1. If live person detection fails, the backend assumes the person is still present so it does not auto-end the session incorrectly.
2. If the general vision model is missing, the code assumes a person exists rather than treating the visitor as absent.

### 3B. Audio Module (STT and TTS)

#### 3B.1 Audio capture flow

Audio capture happens in the browser, not on the backend.

1. `Doorbell.tsx` obtains microphone access through `navigator.mediaDevices.getUserMedia({ audio: true })`.
2. A `MediaRecorder` records audio in `audio/webm` format.
3. For the initial ring, the visitor page records approximately three seconds before submitting the ring request.
4. For follow-up speech, the user toggles recording and the recorded blob is later sent to `/api/transcribe`.
5. Owner voice reply recording in `Dashboard.tsx` works the same way, but the transcribed result is inserted into the reply text box rather than directly spoken.

#### 3B.2 Audio preprocessing

The browser sends base64-encoded `audio/webm` blobs. The backend:

1. Decodes base64.
2. Saves ring audio to `data/tmp/{session_id}/ring_audio.webm`.
3. Saves standalone transcription requests to `data/tmp/transcribe/audio_<id>.webm`.

The file extension matters because the code comments explicitly note that Groq Whisper needs the correct format hint.

#### 3B.3 STT pipeline

The implemented STT order is:

1. Groq Whisper first.
2. VOSK offline fallback second.
3. Stub transcript fallback last.

##### Groq Whisper path

`PerceptionAgent._stt_groq_whisper()`:

1. Opens the saved audio file in binary mode.
2. Calls `self._groq_client.audio.transcriptions.create()` with model `whisper-large-v3-turbo`.
3. Uses `response_format="verbose_json"` and `temperature=0.0`.
4. Auto-detects language by passing `language=None`.
5. Extracts transcript text and estimates confidence from `avg_logprob` if segment data exists.

##### VOSK fallback path

`PerceptionAgent._run_vosk_recognizer()`:

1. Opens the audio file with `wave.open()`.
2. Creates a `vosk.KaldiRecognizer` using the model and file sample rate.
3. Reads frames in chunks of `4000` bytes.
4. Accepts partial and final waveforms.
5. Concatenates recognized text and estimates confidence from word-level `conf` values if available.

##### Final fallback

If no STT engine is available, the code returns `("Audio received", 0.5)`.

#### 3B.4 Hindi normalization

The STT pipeline is immediately followed by `normalize_hindi_transcript()` from `api/utils/hindi_normalize.py`.

This function appends Romanized equivalents for matched Devanagari keywords, which is crucial because the downstream intent and risk logic uses English and Hinglish keyword lists. Without this normalization, phrases like `ओटीपी` would not match `otp`-based scam rules.

#### 3B.5 TTS generation and playback

The TTS path is implemented in `api/utils/tts.py` and used by `ActionAgent` and `/api/tts`.

The engine preference order is:

1. `edge-tts`.
2. `pyttsx3`.
3. `espeak`.
4. Text-file fallback.

The TTS utility:

1. Sanitizes text to remove control characters and limit length to 240 characters.
2. Detects Hindi by Unicode range or common Romanized Hindi tokens.
3. Uses Hindi voice `hi-IN-SwaraNeural` or English voice `en-IN-NeerjaNeural` for `edge-tts`.
4. Saves output to `data/tts/{session_id}.mp3` or `.wav`.
5. Returns a path that the backend exposes through `/static/tts`.

On the frontend, `speakText()` in `src/lib/api.ts` tries backend-generated audio first. If playback fails or the backend TTS endpoint is unavailable, it falls back to browser `speechSynthesis`.

#### 3B.6 Error handling for silence, unavailable audio, and engine failure

Implemented behaviors include:

1. Very small recorded blobs are treated as empty.
2. Missing STT engines return a stub transcript rather than failing the whole request.
3. TTS failure falls back to another TTS engine, then a text file, then browser speech.
4. Voice transcription failure returns the UI to `awaiting_input` with an error message.

### 3C. NLP and Conversation Module

#### 3C.1 Input

The intelligence layer consumes `PerceptionOutput`, which contains:

1. Visitor transcript.
2. Emotion label.
3. Anti-spoof score.
4. Detected objects.
5. Weapon status.
6. Context flags.
7. Person count.
8. Face visibility.

#### 3C.2 Prompt structure

The LLM prompt comes from `api/prompts/groq_system_prompt.txt`. Its constraints are concrete and security-oriented:

1. One short sentence only.
2. Match visitor language when possible.
3. Never reveal occupancy.
4. Never reveal personal information.
5. Never share OTPs, financial info, or allow entry.
6. Apply scenario-specific policies for delivery, government claims, staff, donation, aggression, child/elderly visitors, emergencies, and silent visitors.

When making a one-shot visitor reply, `IntelligenceAgent._build_llm_context()` constructs a structured context block containing detected objects, transcript, emotion, weapon status, person count, face visibility, and context flags.

When generating multi-turn replies, `generate_conversation_reply()` builds a message list composed of:

1. The system prompt.
2. Up to the last 10 history entries.
3. The latest owner or visitor utterance with explicit prefixing like `[Owner says]` or `[Visitor says]`.

#### 3C.3 API interaction

Groq chat calls are made through `self._groq_client.chat.completions.create()` with:

1. Model name from `GROQ_MODEL` or default `llama-3.3-70b-versatile`.
2. `temperature=0.2` for one-shot replies.
3. `temperature=0.3` for conversation replies.
4. `max_tokens=128` or `150` depending on the path.
5. Up to two retries with exponential backoff in the synchronous thread worker.

The asynchronous wrapper around the thread call applies an 8-second timeout, so external LLM latency cannot block the whole system indefinitely.

#### 3C.4 Intent extraction logic

Intent classification is rule-based, not LLM-based.

`_INTENT_KEYWORDS` in `api/agents/intelligence_agent.py` defines the mapping and priority order. The ordering is deliberate: dangerous categories appear first so that mixed phrases such as `delivery + otp` are classified as `scam_attempt` rather than `delivery`.

The implemented intent set is:

1. `scam_attempt`
2. `aggression`
3. `occupancy_probe`
4. `identity_claim`
5. `entry_request`
6. `government_claim`
7. `domestic_staff`
8. `help`
9. `child_elderly`
10. `religious_donation`
11. `sales_marketing`
12. `delivery`
13. `visitor`
14. `unknown` as the fallback when no keyword list matches

#### 3C.5 Response generation rules

Response generation is hybrid:

1. If escalation is required, the agent uses hard-coded escalation replies.
2. If escalation is not required and the transcript is short or the LLM is unavailable, the agent uses canned replies.
3. If the transcript has more than four words and the Groq client is available, the agent attempts an LLM-generated reply.
4. If the LLM call times out or fails, the code falls back to the canned reply.

This design keeps high-risk behavior deterministic while allowing more contextual low-risk conversation when the cloud model is available.

#### 3C.6 Emotion and suspicion handling

Emotion is inferred by keyword heuristics in `PerceptionAgent._infer_emotion()`, not from acoustic emotion analysis.

Supported emotion outputs are:

1. `aggressive`
2. `distressed`
3. `concerned`
4. `nervous`
5. `neutral`

Suspicion is modeled through three connected mechanisms:

1. `context_flags` such as `otp_request`, `occupancy_probe`, `claim_object_mismatch`, `identity_claim`, and `multi_person`.
2. `anti_spoof_score`, a heuristic score based on person visibility, transcript content, low confidence, and mismatch indicators.
3. `risk_score`, computed in the intelligence agent by blending vision confidence, spoof score, emotion, intent overrides, and context-flag risk additions.

### 3D. Backend (FastAPI)

#### 3D.1 Route structure

`api/main.py` groups the backend into five functional areas:

1. Startup and static serving.
2. Authentication.
3. Member management.
4. Core doorbell APIs.
5. Streaming and WebSocket endpoints.

#### 3D.2 Request and response validation

Validation uses Pydantic models for the main API bodies:

1. `RegisterRequest`
2. `LoginRequest`
3. `MemberCreate`
4. `MemberUpdate`
5. `TranscribeRequest`
6. `TTSRequest`
7. `RingEvent`
8. `AiReplyRequest`

#### 3D.3 Async handling

The backend is asynchronous at the HTTP layer, but much of the heavy work is delegated to threads. Important details:

1. `POST /api/ring` is asynchronous, but it waits for the full pipeline to finish before responding.
2. The orchestrator runs model inference and TTS generation in worker threads through `asyncio.to_thread()`.
3. A semaphore limits concurrent sessions to 2.
4. WebSocket broadcasts are scheduled with `asyncio.create_task()` so they do not hold up the main response path.

#### 3D.4 Logging endpoints and notification triggers

The backend exposes `GET /api/logs` to retrieve recent sessions, transcripts, actions, and visitors. Notifications are triggered by:

1. `POST /api/ring`, which broadcasts `new_ring` to the owner channel.
2. Live weapon detection, which broadcasts `weapon_alert` to both owner and session channels.
3. Auto-ending due to inactivity, which broadcasts `session_ended`.
4. `POST /api/ai-reply` and `POST /api/owner-reply`, which rebroadcast replies to the session channel.

### 3E. Mobile App (if applicable)

There is no mobile application in the active codebase.

The closest equivalents are:

1. A responsive React web application intended to be usable from a browser on desktop or mobile.
2. A minimal Electron shell in `electron/main.cjs` for desktop packaging.

Therefore, in report terms, the owner client is a web frontend, not a native mobile app.

### 3F. IoT or Device Control Layer

There is no GPIO, PIR sensor, relay, or smart-lock control layer in the active backend code.

What the repository implements instead is a browser-simulated device layer:

1. Webcam capture stands in for a doorbell camera.
2. Microphone recording stands in for a doorbell microphone.
3. The visitor page streams frames as if it were an edge doorbell device.

The optional `weapon_detection/live_detection.py` script uses a local webcam directly through OpenCV, but it remains an isolated utility script and is not integrated with GPIO or hardware actuation.

---

## 4. End-to-End Data Flow (Critical)

### 4.1 Step 1: Trigger event

#### Input

- Visitor presses the ring button on `Doorbell.tsx`.

#### Processing

1. Frontend state moves to `ringing`.
2. The page captures a still image if the webcam is ready.
3. The page records approximately three seconds of audio.

#### Output

- A base64 image and optional base64 audio blob are prepared for the backend.

#### Approximate time cost

- About 3 seconds fixed by the frontend audio-recording window.

### 4.2 Step 2: Image capture and backend intake

#### Input

- JSON body matching `RingEvent`.

#### Processing

1. `POST /api/ring` calls `Orchestrator.handle_ring()`.
2. The orchestrator generates a `visitor_<8hex>` session id if one is not provided.
3. It saves the image to `data/snaps` and audio to `data/tmp/<session>`.
4. It creates a session row with status `queued`.

#### Output

- Persisted media files and a queued session record.

#### Approximate time cost

- Usually sub-second for file decode and disk write.

### 4.3 Step 3: Detection and perception

#### Input

- Saved image path and optional audio path.

#### Processing

1. General object detection.
2. Weapon detection.
3. STT if audio exists.
4. Hindi normalization.
5. Person counting.
6. Face visibility heuristic.
7. Emotion inference.
8. Context-flag detection.
9. Anti-spoof scoring.
10. Annotated snapshot generation.

#### Output

- `PerceptionOutput`.

#### Approximate time cost

- Internally, each perception sub-call has an 8-second timeout, but the entire perception stage is capped by the orchestrator at 10 seconds.

### 4.4 Step 4: Intelligence reasoning

#### Input

- `PerceptionOutput`.

#### Processing

1. Intent classification.
2. Base risk calculation.
3. Weapon and dangerous-keyword overrides.
4. Context-flag risk increments.
5. Multi-person and hidden-face penalties.
6. Escalation determination.
7. Reply selection: escalation reply, canned reply, or LLM reply.

#### Output

- `IntelligenceOutput` containing `intent`, `risk_score`, `reply_text`, `escalation_required`, and tags.

#### Approximate time cost

- Up to 10 seconds because the orchestrator wraps this stage in `asyncio.wait_for(..., timeout=10)`.

### 4.5 Step 5: Decision branching

#### Input

- `IntelligenceOutput` plus perception-derived weapon/spoof/context fields.

#### Processing

- 12 ordered business rules in `DecisionAgent.process()` choose exactly one final action.

#### Output

- `DecisionOutput` with `final_action`, `reason`, and dispatch instructions.

#### Approximate time cost

- Up to 5 seconds by orchestrator timeout, though actual rule evaluation is effectively immediate.

### 4.6 Step 6: Action execution

#### Input

- `DecisionOutput`, `IntelligenceOutput`, `PerceptionOutput`, and `ActionRequest`.

#### Processing

1. Sanitizes TTS text.
2. Generates TTS if required.
3. Builds a notification payload.
4. Writes action rows to the database.

#### Output

- `ActionResult` plus persisted action logs and optional audio file.

#### Approximate time cost

- Up to 8 seconds due to the orchestrator timeout.

### 4.7 Step 7: Backend response to visitor page

#### Input

- Completed pipeline outputs.

#### Processing

1. The orchestrator reads the first assistant transcript back from the database.
2. The `/api/ring` response returns `sessionId`, `greeting`, status, and media paths.

#### Output

- Visitor page receives the greeting and starts speech playback.

#### Approximate time cost

- End-to-end backend hard upper bound after request arrival is about 33 seconds: 10s perception + 10s intelligence + 5s decision + 8s action.

### 4.8 Step 8: Owner notification

#### Input

- Session id and greeting from completed ring.

#### Processing

- `main.py` broadcasts a `new_ring` message to the `owner` WebSocket channel.

#### Output

- Dashboard receives a live notification and refreshes logs.

#### Approximate time cost

- Near real time after `/api/ring` completes.

### 4.9 Step 9: Ongoing conversation

#### Input

- Visitor follow-up typed message or transcribed voice message.

#### Processing

1. `Doorbell.tsx` sends text to `/api/ai-reply`.
2. The orchestrator stores the message as a transcript.
3. The intelligence agent generates a conversation reply using history.
4. The reply is stored and rebroadcast to the session WebSocket.

#### Output

- Visitor sees transcript updates and hears the reply.

### 4.10 Step 10: Live frame streaming and post-ring monitoring

#### Input

- Continuous `frame_base64` uploads from the visitor page.

#### Processing

1. Backend stores the latest JPEG bytes in memory.
2. Periodic person detection updates the `last_person_seen` timestamp.
3. Periodic weapon detection evaluates possible threats.
4. Owner dashboard polls snapshots for a pseudo-live video view.
5. Inactivity checker auto-ends the session after 20 seconds with no detected person.

#### Output

- Live dashboard imagery, weapon alerts, or session-ended notifications.

#### Approximate time cost

1. Visitor uploads frames at 5 FPS.
2. Person scan runs at most every 2 seconds.
3. Weapon scan runs at most every 0.4 seconds.
4. Dashboard polling fallback requests a snapshot every 250 ms, about 4 FPS.

---

## 5. Business Logic and Decision Engine

### 5.1 How the system decides normal versus suspicious

Suspicion is not a single boolean. It is built from multiple layers:

1. Intent category.
2. Emotion label.
3. Vision confidence.
4. Anti-spoof score.
5. Weapon detection.
6. Context flags.
7. Face visibility.
8. Group size.

### 5.2 Risk score computation

The base risk formula in `IntelligenceAgent.process()` is:

1. `0.5 * (1 - vision_confidence)`
2. `0.3 * anti_spoof_score`
3. `0.2 * emotion_weight`

Then the following overrides or adjustments are applied:

1. Weapon detected -> risk at least `0.75`.
2. Dangerous keywords -> risk at least `0.7`.
3. `scam_attempt` -> risk at least `0.85`.
4. `aggression` -> risk at least `0.80`.
5. `occupancy_probe` -> risk at least `0.70`.
6. `entry_request` -> risk at least `0.65`.
7. Hidden face -> add `0.20`.
8. More than two persons -> add `0.15`.
9. Context-flag weights such as `otp_request +0.50`, `occupancy_probe +0.40`, `financial_request +0.35`, and others from `_CONTEXT_FLAG_RISK_WEIGHTS`.

The score is then clamped into `[0.0, 1.0]` and rounded to three decimals.

### 5.3 Escalation logic

`escalation_required` becomes true when any of the following holds:

1. `risk_score >= 0.7`
2. Weapon detected
3. `anti_spoof_score >= 0.6`
4. Intent is `scam_attempt`
5. Intent is `aggression`

### 5.4 Decision rules

The decision layer applies 12 ordered rules:

1. Weapon detected -> `escalate` and notify owner and watchman.
2. Scam attempt or OTP request -> `escalate`.
3. Aggression -> `escalate`.
4. Occupancy probe -> `escalate`.
5. High risk or escalation flag -> `escalate`.
6. Anti-spoof score >= 0.6 -> `escalate`.
7. Face not visible -> `notify_owner`.
8. Identity, domestic staff, government, or entry claim -> `notify_owner`.
9. More than two persons -> `notify_owner`.
10. Child or elderly visitor -> `notify_owner`.
11. Low risk and auto-reply enabled -> `auto_reply`.
12. Otherwise -> `notify_owner`.

### 5.5 Auto-reply logic

Auto-reply is allowed only when:

1. `risk_score < auto_reply_max_risk`
2. Owner defaults allow `auto_reply_enabled = true`

The default threshold from policy is `0.4`. If `vacation_mode` were enabled, the active thresholds would tighten to `escalate_risk = 0.5` and `auto_reply_max_risk = 0.3`.

### 5.6 Fallback logic

The code includes fallbacks at every major layer:

1. Missing YOLO -> assume person present.
2. Missing Whisper -> use VOSK.
3. Missing VOSK -> return stub transcript.
4. Missing or failing LLM -> use canned reply.
5. Failing TTS engine -> try next engine, then text file, then browser TTS.
6. Live frame detection error -> do not end the session prematurely.
7. Pipeline exception -> log to `data/logs/agent_errors.log` and mark session as `error`.

---

## 6. Database and Data Models

### 6.1 Storage engine

The system uses SQLite through the `Database` class in `api/db.py`. The default file path is `data/db.sqlite`, configurable through `DOORBELL_DB_PATH`.

### 6.2 Tables and field-level explanation

#### `sessions`

Fields:

1. `id TEXT PRIMARY KEY`: session id such as `visitor_ab12cd34`.
2. `created_at TEXT`: ISO timestamp when the session was created.
3. `status TEXT`: lifecycle state such as `queued`, `processing`, `perception_done`, `intelligence_done`, `decision_done`, `completed`, or `error`.
4. `device_id TEXT`: source device identifier, for example `web-frontend`.
5. `last_updated TEXT`: most recent status update time.
6. `risk_score REAL DEFAULT 0`: final or latest computed risk.

#### `transcripts`

Fields:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `session_id TEXT`
3. `role TEXT`: `visitor`, `assistant`, or `owner` in backend storage.
4. `content TEXT`
5. `timestamp TEXT`

This table is the conversational timeline for each session.

#### `visitors`

Fields:

1. `session_id TEXT PRIMARY KEY`
2. `image_path TEXT`
3. `visitor_type TEXT`
4. `ai_summary TEXT`

The current runtime uses this table mainly to store the snapshot path and a short summary. At present, `visitor_type` is upserted as `unknown`, and `ai_summary` is stored as `emotion=<value>`. The richer classification shown in the frontend is therefore only partially realized in backend persistence.

#### `actions`

Fields:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `session_id TEXT`
3. `action_type TEXT`
4. `payload TEXT`: JSON-serialized action payload.
5. `status TEXT`
6. `timestamp TEXT`
7. `short_reason TEXT`
8. `agent_name TEXT`

This is the core audit-trail table.

#### `owners`

Fields:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `username TEXT UNIQUE NOT NULL`
3. `password_hash TEXT NOT NULL`
4. `salt TEXT NOT NULL`
5. `name TEXT DEFAULT ''`
6. `created_at TEXT`

#### `members`

Fields:

1. `id INTEGER PRIMARY KEY AUTOINCREMENT`
2. `owner_id INTEGER NOT NULL`
3. `name TEXT NOT NULL`
4. `phone TEXT DEFAULT ''`
5. `role TEXT DEFAULT 'family'`
6. `photo_path TEXT DEFAULT ''`
7. `permitted INTEGER DEFAULT 1`
8. `created_at TEXT`

This table is the household member registry managed from the frontend.

#### `tokens`

Fields:

1. `token TEXT PRIMARY KEY`
2. `owner_id INTEGER NOT NULL`
3. `created_at TEXT`

This table implements bearer-token sessions.

### 6.3 Relationships

The explicit foreign-key relationships are:

1. `members.owner_id -> owners.id`
2. `tokens.owner_id -> owners.id`

The `sessions`, `transcripts`, `visitors`, and `actions` tables are linked logically by `session_id`, but the code does not define explicit SQLite foreign-key constraints between all of them.

### 6.4 Data lifecycle

#### Session lifecycle

1. Create session row in `sessions` at ring intake.
2. Update status after perception, intelligence, decision, and action phases.
3. Save visitor transcript and assistant transcript.
4. Upsert visitor image and summary.
5. Save multiple action rows for ring receipt, perception, notification, escalation, and manual replies.
6. Retrieve detail through `get_session_detail()` for dashboard inspection.

#### Owner lifecycle

1. Register owner with salted PBKDF2 hash.
2. Create bearer token on login or registration.
3. Validate token on protected routes.
4. Delete token on logout.

#### Member lifecycle

1. Create member from owner dashboard.
2. Save optional member photo to `data/members`.
3. Update metadata or permission state.
4. Delete member row from database when removed.

---

## 7. API Design (Detailed)

### 7.1 Authentication endpoints

#### `POST /api/auth/register`

- Purpose: create a new owner account.
- Request body:
  - `username: string`
  - `password: string`
  - `name: string = ""`
- Response:
  - `user: { id, username, name }`
  - `token: string`
- Notes: returns HTTP 409 if username already exists.

#### `POST /api/auth/login`

- Purpose: authenticate owner and issue bearer token.
- Request body:
  - `username: string`
  - `password: string`
- Response:
  - `user: { id, username, name }`
  - `token: string`
- Notes: returns HTTP 401 on invalid credentials.

#### `POST /api/auth/logout`

- Purpose: invalidate current bearer token.
- Request header:
  - `Authorization: Bearer <token>` optional
- Response:
  - `{ "status": "ok" }`

#### `GET /api/auth/me`

- Purpose: validate bearer token and return current owner.
- Request header:
  - `Authorization: Bearer <token>` required
- Response:
  - `{ "user": { id, username, name } }`

### 7.2 Member management endpoints

#### `GET /api/members`

- Purpose: list members for authenticated owner.
- Auth: required.
- Response: array of member objects.

#### `POST /api/members`

- Purpose: create a member.
- Auth: required.
- Request body:
  - `name: string`
  - `phone: string = ""`
  - `role: string = "family"`
  - `photo_base64: string = ""`
- Response: created member object.

#### `PUT /api/members/{member_id}`

- Purpose: update member fields.
- Auth: required.
- Request body: any subset of `name`, `phone`, `role`, `permitted`, `photo_base64`.
- Response: `{ "status": "updated" }`

#### `DELETE /api/members/{member_id}`

- Purpose: delete member.
- Auth: required.
- Response: `{ "status": "deleted" }`

### 7.3 Core doorbell endpoints

#### `GET /api/health`

- Purpose: service health check.
- Response:
  - `{ "status": "ok", "service": "smart-doorbell-backend" }`

#### `POST /api/ring`

- Purpose: main doorbell entry point.
- Request body: `RingEvent`
  - `type: string = "ring"`
  - `session_id: string | null`
  - `timestamp: datetime`
  - `image_base64: string | null`
  - `audio_base64: string | null`
  - `device_id: string`
  - `metadata: object`
- Response:
  - `sessionId: string`
  - `greeting: string`
  - `status: string`
  - `imageUrl: string | null`
  - `imagePath: string`
  - `audioPath: string`

#### `POST /api/transcribe`

- Purpose: speech-to-text only.
- Request body:
  - `audio_base64: string`
- Response:
  - `transcript: string`
  - `confidence: number`

#### `POST /api/tts`

- Purpose: generate TTS audio file.
- Request body:
  - `text: string`
  - `session_id: string = ""`
- Response:
  - `audioUrl: string | null`
  - `sessionId: string`

#### `POST /api/ai-reply`

- Purpose: visitor or owner follow-up message routed through AI conversation logic.
- Request body:
  - `session_id: string`
  - `message: string`
  - `owner: boolean = true`
  - `dispatch_action: boolean = false`
- Response:
  - `sessionId: string`
  - `status: string`
  - `timestamp: string`
  - `reply: string`

#### `POST /api/owner-reply`

- Purpose: owner sends a direct reply to the session.
- Request body: same shape as `AiReplyRequest`.
- Response: same structure produced by `handle_ai_reply()`.
- Important implementation detail: the frontend sends auth headers, but the backend endpoint does not actually enforce authentication.

#### `GET /api/session/{session_id}/status`

- Purpose: lightweight session-state polling.
- Response:
  - `sessionId: string`
  - `status: string`
  - `lastUpdated: string`
  - `riskScore: number`

#### `GET /api/session/{session_id}/detail`

- Purpose: full session inspection.
- Response:
  - `session: object`
  - `visitor: object | null`
  - `transcripts: array`
  - `actions: array`

#### `GET /api/logs`

- Purpose: recent log retrieval for dashboard and history pages.
- Query parameter:
  - `limit: int = 50`
- Response:
  - `sessions: array`
  - `transcripts: array`
  - `actions: array`
  - `visitors: array`

### 7.4 Streaming endpoints

#### `POST /api/session/{session_id}/stream-frame`

- Purpose: receive one live JPEG frame for streaming and live threat analysis.
- Request body:
  - `frame_base64: string`
- Response:
  - `status: "frame received"`
  - `sessionId: string`
  - `weapon_detected: boolean`

#### `GET /api/stream/{session_id}`

- Purpose: MJPEG stream of the latest in-memory frames.
- Response media type:
  - `multipart/x-mixed-replace; boundary=frame`

#### `GET /api/stream/{session_id}/snapshot`

- Purpose: return the latest JPEG frame as a single image for polling fallback.
- Response media type:
  - `image/jpeg`

### 7.5 WebSocket endpoint

#### `WS /api/ws/{channel}`

- Purpose: real-time event delivery.
- Channels:
  - `owner`
  - `{session_id}`
- Outbound event types used in code:
  - `new_ring`
  - `weapon_alert`
  - `session_ended`
  - `ai_reply`
  - `owner_reply`
- Inbound message handling: not implemented; the loop currently receives text and ignores it.

---

## 8. System Architecture (Real Implementation View)

### 8.1 Edge versus cloud responsibilities

#### Edge or local responsibilities

1. UI rendering.
2. Webcam and microphone capture.
3. Snapshot and live-frame upload.
4. YOLO inference when model files are available locally.
5. SQLite persistence.
6. TTS generation when local engines are installed.
7. WebSocket coordination.

#### Cloud responsibilities

1. Whisper transcription through Groq.
2. Reply generation through Groq chat completions.

The architecture is therefore hybrid: local sensing and local control, cloud-assisted language interpretation and response quality.

### 8.2 Component interaction

The implementation view is:

1. `Doorbell.tsx` sends `RingEvent` to FastAPI.
2. `FastAPI /api/ring` invokes `Orchestrator.handle_ring()`.
3. The orchestrator invokes the four agents in sequence.
4. Database writes happen throughout the sequence.
5. `main.py` emits owner notifications over WebSocket after the pipeline returns.
6. `Dashboard.tsx` consumes logs, detail APIs, WebSocket updates, and snapshot polling.

### 8.3 Communication protocols

The repository uses three protocols:

1. REST over HTTP for command and query operations.
2. WebSocket for event push.
3. MJPEG or repeated JPEG snapshot fetches over HTTP for live camera viewing.

It does not use WebRTC.

### 8.4 Why this architecture fits the codebase goals

The architecture is consistent with a single-home deployment that values simplicity and local control:

1. SQLite avoids external infrastructure.
2. FastAPI allows REST, WebSocket, and static file serving in one process.
3. React in the browser provides instant access to camera and microphone APIs.
4. Cloud LLM services are used only where local heuristics would be weak or less natural.

---

## 9. Performance Characteristics

### 9.1 Latency-sensitive paths

#### Initial ring response

The slowest user-visible path is the first ring because it includes:

1. Three seconds of browser-side audio recording.
2. Image and audio upload.
3. Full synchronous pipeline execution.
4. TTS generation if required.

The backend timeouts enforce an upper bound of about 33 seconds after backend receipt, but the target behavior is clearly much faster under normal conditions.

#### Conversation reply

Follow-up conversation skips image analysis and directly uses transcript and LLM logic, so it is lighter than the initial ring path.

### 9.2 Bottlenecks visible in code

1. `POST /api/ring` is synchronous and blocks until the full pipeline finishes.
2. Cloud STT and cloud LLM calls can dominate total latency.
3. Model inference runs on CPU with `device="cpu"`.
4. Live frame uploads from the browser can add CPU and network overhead during an active session.
5. SQLite is acceptable for single-device workloads but will not scale well to many simultaneous active sessions.

### 9.3 Concurrency handling

Concurrency is intentionally constrained:

1. `max_concurrent_sessions = 2`.
2. A semaphore serializes the main pipeline beyond that limit.
3. Heavy work is moved into worker threads.
4. WebSocket broadcasts are fire-and-forget tasks.

This design explicitly matches the Raspberry Pi constraint described in governance documents and comments.

### 9.4 Memory and CPU usage patterns

1. YOLO models remain resident in memory after agent initialization.
2. Live stream frames are kept in memory in `_session_frames` rather than on disk.
3. Snapshot processing uses disk-backed images, while live monitoring uses in-memory arrays.
4. The browser continuously captures frames and can keep CPU busy on the client side during an active live stream.

---

## 10. Failure Handling and Edge Cases

### 10.1 No internet

If Groq is unavailable:

1. STT falls back to VOSK if models exist.
2. If VOSK also is unavailable, the system returns a stub transcript.
3. LLM reply generation falls back to canned replies.

The system therefore degrades but remains functional in a limited rule-based mode.

### 10.2 STT fails

Implemented behavior:

1. Groq Whisper errors are logged and the system tries VOSK.
2. If VOSK fails too, transcript becomes `"Audio received"` or empty.
3. The pipeline continues, so the visit can still be logged and classified from vision/context alone.

### 10.3 NLP fails

If Groq LLM generation fails:

1. The intelligence layer returns a canned reply.
2. Multi-turn conversation falls back to canned intent-based responses.

### 10.4 Detection fails

If general detection or weapon detection fails:

1. The code returns safe fallback values.
2. If the general model is missing entirely, it assumes a person exists.
3. If live person detection errors, the session is kept alive rather than auto-ended.

### 10.5 Hardware failure or permission denial

On the visitor frontend:

1. Camera permission denial displays a message but still allows ringing without video.
2. No camera found also degrades gracefully.
3. Microphone denial prevents voice capture but still permits typed conversation.

### 10.6 Pipeline exception

If any stage raises an exception that escapes its local fallbacks:

1. `Orchestrator._log_agent_error()` appends a JSON line to `data/logs/agent_errors.log`.
2. The session status is updated to `error`.

### 10.7 Session inactivity

If no person is visible for 20 seconds:

1. The inactivity loop marks the session completed.
2. A transcript entry is inserted indicating auto-end due to inactivity.
3. Owner and visitor WebSocket listeners are notified.

---

## 11. Security Implementation

### 11.1 Implemented security mechanisms

#### Authentication and credential handling

1. Passwords are hashed with PBKDF2-HMAC-SHA256 and 100,000 iterations.
2. Each owner account gets a per-user random salt.
3. Session tokens are random `token_urlsafe(32)` strings stored server-side.

#### Prompt and response safety

1. The system prompt prohibits revealing occupancy, personal details, OTPs, financial data, or door access.
2. Escalation replies are deterministic for high-risk cases.

#### TTS command safety

1. TTS text is sanitized.
2. `espeak` is invoked with argument lists and `shell=False`.

#### Threat heuristics

1. Weapon detection.
2. Occupancy-probe detection.
3. OTP scam detection.
4. Identity and authority claim skepticism.
5. Anti-spoof heuristics.

### 11.2 Security gaps visible in implementation

The repository also contains important security limitations that should be described honestly in an engineering report:

1. `CORS` is configured with `allow_origins=["*"]`.
2. `GET /api/logs`, `GET /api/session/{id}/status`, and `GET /api/session/{id}/detail` are not protected by authentication.
3. `POST /api/owner-reply` does not enforce authentication even though the frontend sends bearer headers.
4. Tokens do not expire; the `tokens` table stores `created_at` but verification does not check token age.
5. There is no rate limiting.
6. There is no TLS termination in application code.
7. Images, transcripts, and audio paths are stored unencrypted on disk.
8. Anti-spoofing is heuristic, not biometric liveness detection.

These are not hypothetical concerns; they follow directly from the route code and database logic.

---

## 12. Scalability and Limitations

### 12.1 Single-device versus multi-device support

The implemented system is primarily single-site and low-concurrency:

1. Session concurrency is capped at 2.
2. Static file paths and SQLite state assume one local backend instance.
3. There is no device registry, tenant separation, or per-doorbell fleet management.

### 12.2 Backend scaling limits

1. SQLite becomes a contention point under concurrent writes.
2. The orchestrator is process-local and keeps in-memory session queues and live frame buffers.
3. WebSocket state is stored in-memory in `ConnectionManager.active`, so horizontal scaling would require shared state or sticky sessions.

### 12.3 Model constraints on Raspberry Pi or low-power hardware

The code is written with low-resource deployment in mind, but it still has limits:

1. CPU-only YOLO inference will be slower on a Raspberry Pi than on a laptop.
2. Continuous live-frame analysis can consume noticeable CPU.
3. Groq dependence improves quality but introduces network sensitivity.
4. The repo includes PyTorch, OpenCV, and Ultralytics, which are heavy dependencies for edge hardware.

### 12.4 Functional limitations

1. No native mobile app.
2. No GPIO lock control or PIR trigger integration.
3. No push notification provider integration.
4. No owner preference storage beyond what is hard-coded in policy defaults.
5. No face recognition matching against `members`; member photos are stored, but no recognition pipeline consumes them.
6. `visitor_type` persistence is not fully implemented beyond `unknown`.
7. The Vercel deployment path still targets the older `api/index.py`, creating a split between local runtime and serverless configuration.

---

## 13. Engineering Decisions (Very Important)

### 13.1 Why YOLOv8n was chosen in practice

The code loads `yolov8n.pt`, not a larger YOLO variant. That implies a deliberate design choice favoring:

1. Small model size.
2. CPU feasibility.
3. Lower memory pressure.
4. Faster edge inference compared with larger checkpoints.

This is consistent with the repository comments about Raspberry Pi-friendly limits and the explicit use of `device="cpu"`.

### 13.2 Why FastAPI fits the implementation

FastAPI was a strong fit because the project requires in one server:

1. JSON APIs.
2. Pydantic validation.
3. WebSocket support.
4. Static file serving.
5. Asynchronous background behavior.

The code uses all of these features directly in `api/main.py`.

### 13.3 Why the architecture is edge plus cloud

The code clearly divides responsibilities:

1. Vision and persistence stay local for privacy, immediacy, and offline partial operation.
2. STT and LLM calls move to Groq for better multilingual transcription and better short conversational responses.

This hybrid design provides better quality than a purely local rule engine while preserving fallback behavior if the cloud path is unavailable.

### 13.4 Why SQLite was chosen

SQLite is consistent with:

1. Single-home deployment.
2. Simple local installation.
3. No infrastructure dependency.
4. Easy audit-trail storage for sessions and actions.

### 13.5 Why `edge-tts` was selected as primary TTS

The code prioritizes `edge-tts` because it offers:

1. Better voice quality than offline defaults.
2. Good Indian English and Hindi neural voices.
3. File-based output that the frontend can play through normal browser audio.

### 13.6 Why rules and LLM are combined

The project does not trust the LLM for everything. The code keeps the critical security path rule-based:

1. Intent classification is deterministic.
2. Escalation decisions are deterministic.
3. Only lower-risk conversational phrasing is optionally LLM-generated.

This is an important engineering decision because it reduces the chance of a generative model making an unsafe access decision.

---

## 14. Product Perspective Layer (Mandatory)

### 14.1 Visitor experience flow

From a product point of view, the visitor sees:

1. A doorbell interface with ring button, microphone support, and optional camera.
2. A quick AI-generated greeting after ringing.
3. The ability to speak or type follow-up messages.
4. Spoken responses from the system or owner.
5. Automatic session closure if they leave and are no longer visible.

The interaction is intentionally short and transactional. The product tries to answer practical door-step scenarios without exposing the household.

### 14.2 Owner experience flow

The owner sees:

1. A login or registration flow.
2. A dashboard with active visitors, recent visitors, session counts, and live session cards.
3. Real-time notifications when someone rings.
4. A pseudo-live camera view via snapshot polling.
5. Full transcript inspection.
6. Quick text or voice reply controls.
7. Weapon alert banners if the live stream detects a threat.
8. A member management page for household records.
9. A visitor history page for audit and review.

### 14.3 Value delivered

#### Security value

1. Reduces the risk of revealing occupancy or personal information.
2. Escalates scam-like, aggressive, or weapon-linked interactions.
3. Keeps a persistent record of what happened.

#### Convenience value

1. Handles routine low-risk visitors automatically.
2. Lets the owner reply remotely through a web dashboard.
3. Supports Hindi, English, and Hinglish interaction paths.

#### Automation value

1. Automatically detects common visitor categories.
2. Automatically speaks replies.
3. Automatically ends inactive sessions.
4. Automatically logs the entire interaction trail.

---

## Synthesis: What the system really is

In implementation terms, this project is not just a smart doorbell UI. It is a compact event-driven security workflow engine built around a synchronous multi-agent pipeline.

The core system identity is:

1. A browser-based edge capture client.
2. A FastAPI orchestration service.
3. A four-stage AI decision pipeline.
4. A SQLite-backed audit system.
5. A real-time owner supervision dashboard.

Its strongest implemented qualities are:

1. Clear separation of perception, reasoning, decision, and action concerns.
2. Strong scenario-specific business logic for Indian household threats.
3. Graceful degradation when cloud AI or local models are unavailable.
4. A usable owner-facing product flow tied directly to backend state.

Its most important current technical limitations are:

1. Partial security hardening on API access.
2. Limited scalability beyond a single-household deployment.
3. No native hardware control layer.
4. Split deployment story between `api/main.py` and `api/index.py`.

For an academic engineering report, the repository supports a strong narrative around hybrid edge-cloud AI, structured agent orchestration, applied household security logic, and a full-stack implementation from sensing through action and audit.