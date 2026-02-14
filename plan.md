# Multi-Agent Conversion Plan — Phase-by-phase, implementation-ready (for Claude / Codex / other coding agents)

*Based on your current Smart Doorbell project.* 

This MD is written so an automated coding agent (Claude, Codex, GPT-Engineer) can **follow each phase and create the whole system**. It assumes:

* You will use the **Groq API** for the LLM/intelligence agent.
* All code must **run on an 8GB Raspberry Pi 4** (CPU-first, light models).
* **SQLite** for persistence.
* **No external message broker** (local async/event-bus pattern to keep Pi-friendly).
* Each agent must have its own `instructions/*.md` file under `api/instructions/` (human- & agent-readable).
* No deployment instructions needed.

---

# Quick summary (one line)

Split the monolithic backend into 4 agents (Perception, Intelligence, Decision, Action) plus a lightweight Orchestrator that routes events, all inside `api/` using SQLite and an in-process async event bus. Each agent is a Python module/class with its instruction file.

---

# Repo layout (target)

```
/project-root
├─ frontend/                         # existing React app (unchanged except API base updates)
└─ api/
   ├─ orchestrator.py               # FastAPI app + event loop + session manager
   ├─ agents/
   │  ├─ base_agent.py
   │  ├─ perception_agent.py
   │  ├─ intelligence_agent.py
   │  ├─ decision_agent.py
   │  ├─ action_agent.py
   ├─ instructions/
   │  ├─ perception.md
   │  ├─ intelligence.md
   │  ├─ decision.md
   │  ├─ action.md
   ├─ db.py                          # sqlite wrapper, migrations
   ├─ models.py                      # pydantic message schemas
   ├─ utils.py                       # helper functions (image save, audio, tts helpers)
   ├─ prompts/
   │  └─ groq_system_prompt.txt
   ├─ requirements.txt
   └─ tests/
      ├─ test_orchestrator.py
      ├─ test_perception.py
      └─ ...
```

---

# Communication pattern (Pi-friendly)

* Agents do **not** run as separate docker services. They are **modular Python classes** loaded by orchestrator.
* Orchestrator coordinates with **asyncio.Queues** per session, routes events, awaits agent responses with timeouts.
* All messages use the JSON schemas below (enforce via Pydantic models in `models.py`).

### Message schemas (canonical)

`RingEvent` (frontend → orchestrator)

```json
{
  "type":"ring",
  "session_id":"visitor_<uuid>",
  "timestamp":"ISO8601",
  "image_base64": "<optional>",
  "audio_base64": "<optional>",
  "device_id":"frontdoor-01",
  "metadata": {"rssi": -50}
}
```

`PerceptionOutput`

```json
{
  "session_id":"visitor_<uuid>",
  "person_detected": true,
  "objects":[{"label":"person","conf":0.92},{"label":"package","conf":0.79}],
  "vision_confidence":0.85,
  "transcript":"I have an Amazon delivery",
  "stt_confidence":0.93,
  "emotion":"neutral",
  "anti_spoof_score":0.05,
  "image_path":"/data/snaps/visitor_<uuid>.jpg",
  "timestamp":"ISO8601"
}
```

`IntelligenceOutput`

```json
{
  "session_id":"visitor_<uuid>",
  "intent":"delivery",
  "reply_text":"Please leave the package at the doorstep.",
  "risk_score":0.32,
  "escalation_required": false,
  "tags":["delivery","friendly"],
  "timestamp":"ISO8601"
}
```

`DecisionOutput`

```json
{
  "session_id":"visitor_<uuid>",
  "final_action":"auto_reply",   // auto_reply | notify_owner | call_owner | ignore | escalate
  "reason":"risk < threshold && auto_reply_on",
  "dispatch": {"tts":true,"notify_owner":true},
  "timestamp":"ISO8601"
}
```

`ActionRequest` (to Action Agent)

```json
{
  "session_id":"visitor_<uuid>",
  "tts_text":"Please leave the package at the doorstep.",
  "image_path":"/data/snaps/visitor_<uuid>.jpg",
  "notify_payload":{"owner_id":"user_42","priority":"normal"},
  "timestamp":"ISO8601"
}
```

---

# SQLite schema (file: `db.py` with migrations)

Run-once SQL (example):

```sql
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT,
  status TEXT,
  device_id TEXT,
  last_updated TEXT,
  risk_score REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transcripts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  role TEXT,
  content TEXT,
  timestamp TEXT
);

CREATE TABLE IF NOT EXISTS visitors (
  session_id TEXT PRIMARY KEY,
  image_path TEXT,
  visitor_type TEXT,
  ai_summary TEXT
);

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  action_type TEXT,
  payload TEXT,
  status TEXT,
  timestamp TEXT
);
```

---

# Phase plan (very detailed)

> Each phase below includes: **what to implement**, **file(s) to create/update**, **tests**, **perf/PI tips**, and **instructions file content** to drop under `api/instructions/`.

---

## Phase 0 — Prep & skeleton (0.5–1 day)

**Goal:** Repo skeleton, requirements, CI/test skeleton.

**Do:**

* Create `api/requirements.txt` minimal:

  ```
  fastapi
  uvicorn[standard]
  pydantic
  sqlite3   # stdlib, no pip
  pillow
  numpy
  ultralytics   # yolov8
  soundfile
  vosk           # or faster-whisper if available on Pi
  requests
  aiofiles
  groq
  pytest
  ```

  *Note:* pick STT library based on Pi build; include VOSK small model recommendation in instruction file.

* Create `api/orchestrator.py` (FastAPI app skeleton) with `/api/ring`, `/api/ai-reply`, `/api/logs`, `/api/session/{id}/status` endpoints.

* Create `api/models.py` with Pydantic models for the schemas above.

**Tests:**

* `tests/test_orchestrator.py`: test `/api/ring` returns session_id and created session in SQLite.

**Instruction file:**

* Add `api/instructions/README.md` that explains each instructions file naming and that agent code must load its instruction file.

---

## Phase 1 — Orchestrator & base agent (1–2 days)

**Goal:** Implement the orchestrator, BaseAgent, session state machine, local async event bus.

**What to implement**

* `api/orchestrator.py`:

  * On startup, initialize DB connection, create in-memory `session_queues: Dict[session_id, asyncio.Queue]`.
  * POST `/api/ring`:

    * Validate payload (RingEvent model).
    * Create `session_id` and insert session row to SQLite.
    * Save base64 image to disk `data/snaps/{session_id}.jpg` (use `aiofiles`).
    * Put event onto `session_queues[session_id]`.
    * Spawn a background coroutine `handle_session(session_id)` that sequentially:

      1. await perception_agent.process(event) with timeout
      2. persist PerceptionOutput, append to transcripts
      3. call intelligence_agent.process(perception_output)
      4. persist IntelligenceOutput
      5. call decision_agent.process(intel_output)
      6. persist DecisionOutput
      7. queue action_agent.handle(action_request)
      8. update session status
  * Provide WebSocket `/api/ws/session/{id}` to stream state updates to frontend (optional but recommended).
* `api/agents/base_agent.py`:

  * `BaseAgent` that loads `instructions/*.md` at init and exposes `instructions_text`.

**Tests:**

* Integration test that posts a sample ring, then polls `/api/session/{id}/status` and confirms status changes from `queued` → `perception_done` → `completed` (mock agent implementations used).

**Pi tips**

* Use `asyncio.create_task` but cap concurrent sessions (e.g., semaphore with max_concurrent_sessions=2) to avoid OOM.

**instructions/orchestrator.md** (short): describe session lifecycle and event bus contract.

---

## Phase 2 — Perception Agent (2–4 days)

**Goal:** Implement `PerceptionAgent` that runs YOLOv8n (CPU), STT (VOSK or whisper-tiny alternative), emotion heuristics, anti-spoof.

**Files**

* `api/agents/perception_agent.py` (class `PerceptionAgent(BaseAgent)` exposing `async def process(self, ring_event) -> PerceptionOutput`)

**Key implementation details (code sketch)**

```python
from ultralytics import YOLO
model = YOLO("yolov8n.pt")  # yolov8n small model

async def run_yolo(image_path):
    results = model(image_path, imgsz=640)  # CPU
    # parse results: results[0].boxes.xyxy, .names, .probs
```

**STT**

* Option A (recommended on Pi): VOSK small model (offline).
* Option B: faster-whisper/whisper.cpp if you can cross-compile; provide fallback to remote STT.

**Anti-spoof**

* Basic heuristics:

  * `if not person_detected: anti_spoof_score = 0.9`
  * `if vision_confidence < 0.4: anti_spoof_score += 0.2`
  * (Optional) if short video frames available: compute frame diffs > threshold → live.

**Outputs**

* Save a small annotated snapshot `data/snaps/visitor_<id>_annot.jpg`.
* Return `PerceptionOutput` Pydantic model.

**instructions/perception.md** (full file content must include):

* Precise step-by-step required output JSON.
* CPU-only model selection (yolov8n).
* Files to write and locations.
* Timeouts (e.g., 6s per image).

**Tests**

* Unit test that uses a deterministic test image and asserts `person_detected` true/false, and correct structure.

**Pi tips**

* Use `imgsz=416` or 640; prefer smaller size to reduce CPU/time.
* Use `model.predict(source, device='cpu', half=False)`; disable `cuda`.
* Use `ultralytics` 8n weights; convert to ONNX if needed for extra speed.

---

## Phase 3 — Intelligence Agent (Groq LLM) (2–4 days)

**Goal:** Build LLM-backed reasoning service that takes `PerceptionOutput` and returns `IntelligenceOutput` (intent, reply_text, risk_score).

**Files**

* `api/agents/intelligence_agent.py`

**Flow**

1. Accept `PerceptionOutput`.
2. Run rule-based fast intent classifier (keywords: "package", "delivery", "friend", "solicitor", "help", "open", etc.). If high-confidence, skip LLM.
3. Compute a baseline `risk_score` from perception fields using configurable weights: `risk = α*(1-vision_conf) + β*anti_spoof + γ*(emotion_score)`.
4. If ambiguous or reply_text required, call Groq API with system prompt and a compact context (last 3 transcript messages) to generate `reply_text`. Use short prompts to keep tokens low.

**Groq call example (pseudo)**

```python
from groq import Groq
client = Groq(api_key=os.environ["GROQ_API_KEY"])
resp = client.predict(
    model="llama-3.3-70b-versatile",
    prompt=system_prompt + "\n\n" + user_context,
    max_tokens=128,
    temperature=0.2
)
reply_text = resp.output_text.strip()
```

*(Wrap in a retry with exponential backoff; enforce 6s overall timeout on Pi.)*

**Instruction file:** `api/instructions/intelligence.md` must include:

* Groq API usage details (environment variable name: `GROQ_API_KEY`).
* System prompt file usage: `api/prompts/groq_system_prompt.txt`.
* Token/timeout limits, fallback behavior (if Groq fails -> use canned reply based on intent).

**Prompts**

* Provide `api/prompts/groq_system_prompt.txt` with clear rules:

  * respond in one short sentence,
  * do not reveal personal info,
  * security escalation phrase: "I have notified the owner and the security guard" if suspicious,
  * language detection: answer in visitor's language (Hindi/English).

**Tests**

* Unit tests for rule-based classifier.
* Integration test mocking Groq response.

**Pi tips**

* Avoid sending long histories to Groq — only last 2-3 messages and perception summary.
* Cache identical prompts/responses if repeated.

---

## Phase 4 — Decision Agent (1–2 days)

**Goal:** Convert outputs into actions using business rules (vacation mode, owner prefs).

**Files**

* `api/agents/decision_agent.py`
* `api/policies/policy.yaml` (human-editable rules)

**Design**

* Decision agent loads `policy.yaml` at startup and evaluates `IntelligenceOutput` against rules (use tiny rule evaluator or simple Python boolean expressions parsed safely).
* Example rules (policy.yaml):

```yaml
escalate_if:
  - condition: "risk_score >= 0.7"
    action: "notify_watchman"
auto_reply_if:
  - condition: "risk_score < 0.4 and auto_reply == true"
    action: "auto_reply"
```

* Owner preferences stored in `sessions` or `visitors` table and consulted at decision time.

**instructions/decision.md**

* Describe policy file format.
* Explain evaluation order and tie-breaker logic.

**Tests**

* Unit tests for policy evaluation.

---

## Phase 5 — Action Agent (1–2 days)

**Goal:** Execute final actions — TTS playback, owner notify (FCM stub), logging to SQLite.

**Files**

* `api/agents/action_agent.py`
* `api/utils/tts.py` (two modes)

  * Edge TTS: use `espeak`/`pico2wave` available on Pi and run subprocess to play audio locally.
  * Cloud TTS (optional): not required.

**Responsibilities**

* If `final_action == 'auto_reply'` → call TTS helper to play phrase on Pi (local speaker) or produce audio file path and return `played`.
* If notify_owner → create `actions` row and (for now) write owner notification to a local queue file or log; frontend `GET /api/logs` can show pending notifications. (You can wire a simple push later.)
* Save transcripts and action logs in SQLite.

**instructions/action.md**

* TTS playback command examples for Pi: `pico2wave` or `espeak`.
* Where audio files should be saved (`data/tts/{session}.wav`).
* Security: sanitize text before TTS to avoid injecting shell commands.

**Tests**

* Mock TTS path; unit test creation of `actions` row and mark status.

---

## Phase 6 — Frontend wiring & APIs (0.5–1 day)

**Goal:** Minimal change to frontend: point to orchestrator endpoints and show session status.

**APIs to expose from orchestrator**

* `POST /api/ring` — same as before
* `POST /api/ai-reply` — route owner typed reply into transcript and optionally to intelligence or action
* `GET /api/logs` — return sessions and transcript rows from SQLite
* `GET /api/session/{id}/status` — returns last known step & last messages
* `WebSocket /api/ws/session/{id}` — stream state changes (optional)

**Frontend changes**

* Update `api.ts` to use new endpoints.
* Add small UI indicator showing pipeline stage (Perception → Intel → Decision → Action).
* Add manual override buttons that POST to `/api/ai-reply` with `owner=true`.

**Tests**

* Frontend integration test that simulates a ring and checks session lifecycle via status endpoint.

---

## Phase 7 — Tests, acceptance, and hardening (2–3 days)

**Unit tests**

* Each agent class tests.
  **Integration tests**
* Using pytest with SQLite test DB and sample image/audio fixtures.
  **Acceptance criteria**
* Perception produces expected JSON shape for test image.
* Intelligence produces reply_text and risk_score.
* Decision maps risk->action according to policy.
* Action logs and TTS file produce expected side effects.
* System runs under Pi memory constraints: test with 1–2 concurrent sessions.

**Performance targets (Pi)**

* YOLOv8n inference (CPU): aim < 1.5–3s per image (depends on image size). Use `imgsz=416` to reduce time.
* STT (VOSK): ~0.5–2x real-time depending on model size.
* Groq calls: external network latency; keep prompt size small and rely on rule fallback for low-latency cases.

---

## Phase 8 — Acceptance tests & demo scenarios (1 day)

Write scripts under `api/tests/` to simulate:

1. Delivery: image with courier, audio "I have a package".
2. Solicitor: audio "Can I speak to the owner?"
3. Unknown / suspicious: no person_detected or low vision_confidence.

Each must complete end-to-end and assert expected `final_action`.



---

# `api/instructions/*` templates (exact content to include)

### `api/instructions/perception.md`

```
Perception Agent Instructions
-----------------------------
- Load this file at startup and keep text available as 'instructions'.
- Inputs: RingEvent { session_id, image_path, audio_path?, device_id }
- Steps:
  1. Run YOLOv8n inference (model: yolov8n.pt) on image_path (imgsz=416).
  2. Extract objects with label & confidence.
  3. If audio provided, run STT (VOSK small). Provide 'transcript' and 'stt_confidence'.
  4. Compute emotion from transcript (simple rules).
  5. Compute anti_spoof_score:
     - if person not detected => 0.9
     - else 0.0 + adjustments for low confidence and inconsistent audio
  6. Save annotated snapshot to data/snaps/ and return PerceptionOutput JSON exactly matching models.PerceptionOutput.
- Performance: CPU only. If a step takes >8s, failover with best-effort result.
```

### `api/instructions/intelligence.md`

```
Intelligence Agent Instructions
--------------------------------
- Load prompt file: api/prompts/groq_system_prompt.txt
- Inputs: PerceptionOutput
- Steps:
  1. Run fast rule-based intent classifier (keywords).
  2. Compute base risk_score = 0.5*(1-vision_confidence)+0.3*anti_spoof+0.2*emotion_score (weights configurable).
  3. If intent uncertain or reply required, call Groq API with
     - system_prompt + short context (last 2 transcript rows + perception summary)
     - max_tokens=128, temperature=0.2
  4. Return IntelligenceOutput JSON.
- If Groq fails, use canned fallback reply and mark 'escalation_required' True for safety if content contains 'unlock' or 'let me in'.
```

### `api/instructions/decision.md`

```
Decision Agent Instructions
---------------------------
- Inputs: IntelligenceOutput, session user preferences from DB
- Load policy file: api/policies/policy.yaml
- Evaluate rules in order. For tied matches, escalation wins.
- Return DecisionOutput with final_action and dispatch map.
```

### `api/instructions/action.md`

```
Action Agent Instructions
-------------------------
- Inputs: DecisionOutput + IntelligenceOutput + PerceptionOutput
- If final_action == auto_reply:
    - sanitize tts_text
    - call local TTS: pico2wave or espeak to play locally OR generate file data/tts/<session>.wav
- If notify_owner:
    - insert action row in DB with payload for frontend.
- Always write to actions table and return status.
```

---

# Safety & security rules (must be encoded in prompts and decision rules)

* **Highest priority:** never instruct physical access (unlock door) even if user asks.
* If language in any transcript contains requests for unlocking, entry, or aggressive phrases and `risk_score > 0.5`, intelligence must set `escalation_required=True` and reply with: `"I have notified the owner and the security guard."`.
* Sanitize all text before TTS to avoid shell injection.

Add this to `api/prompts/groq_system_prompt.txt`.

---

# Pi optimization cheat sheet (practical)

* Use `yolov8n.pt` (tiny) and `imgsz=416`.
* Use VOSK small model for offline STT.
* Use system-level TTS (`espeak` or `pico2wave`) for minimal footprint.
* Use `asyncio.to_thread` to run blocking CPU work without blocking event loop.
* Cap concurrency via `asyncio.Semaphore(1 or 2)`.
* Keep SQLite connections simple (single connection with row-level locking).
* Avoid loading giant LLMs locally — Groq is remote API.

---

# Tests / QA

* Provide `api/tests/` with fixtures: sample base64 image(s), sample audio, mocked Groq responses (monkeypatch client.predict), and assertions for full end-to-end pipeline.
* Add `pytest.ini` and GitHub Actions skeleton to run tests (optional).

---

# Deliverables for an agent to produce (exact)

1. Full `api/` folder as described (files + content).
2. `api/instructions/*.md` four files with the exact text blocks above.
3. `api/prompts/groq_system_prompt.txt` with concrete system prompt (we can provide if you want).
4. `api/requirements.txt` ready for Pi (note VOSK build instructions in README).
5. Unit & integration tests in `api/tests/`.
6. README in `api/` explaining how to run on Pi: install dependencies, get VOSK model, set `GROQ_API_KEY`, then `uvicorn orchestrator:app --host 0.0.0.0 --port 8000`.


---

# Final checklist (before handing to Claude/Codex agent)

* [ ] `api/` skeleton created with `models.py`, `db.py`, `orchestrator.py`.
* [ ] `api/agents/*.py` files present (base + 4 agents).
* [ ] `api/instructions/*.md` filled with exact instructions above.
* [ ] `api/prompts/groq_system_prompt.txt` created and referenced by `intelligence_agent`.
* [ ] `api/requirements.txt` created and Pi notes included in README.
* [ ] Tests exist and run locally with `pytest`.
* [ ] Environment variable `GROQ_API_KEY` documented.

---

