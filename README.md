# Smart Doorbell — Multi-Agent AI Security System

An AI-powered smart doorbell system designed for **Indian households** that uses a multi-agent architecture to detect, classify, and respond to visitors in real-time. Supports Hindi, English, and Hinglish speech with automatic threat detection, scam prevention, and owner notification.

Includes a full-featured **React frontend** with a visitor doorbell interface (webcam + mic), owner dashboard with live visitor view, member management, and real-time WebSocket notifications.

## Architecture

```
┌──────────────────┐
│   React Frontend  │
│  (Doorbell + Dash)│
│   port 8080       │
└────────┬─────────┘
         │  REST + WebSocket
┌────────▼─────────┐
│   FastAPI Backend │
│   port 8000       │
└────────┬─────────┘
         │
┌────────▼──────────┐     ┌────────────────────┐
│  Perception Agent  │────▶│ Intelligence Agent  │
│  • YOLOv8 vision   │     │  • Groq Whisper STT │
│  • Weapon detection │     │  • Intent classify  │
│  • Context flags    │     │  • Risk scoring     │
└───────────────────┘     │  • LLM replies      │
                           └────────┬───────────┘
                                    │
┌───────────────────┐     ┌────────▼───────────┐
│   Action Agent     │◀────│  Decision Agent     │
│  • edge-tts (Hi/En)│     │  • 12 policy rules  │
│  • Notifications   │     │  • Escalation logic  │
│  • DB audit trail  │     │  • Indian scenarios  │
└───────────────────┘     └────────────────────┘
```

### Agent Pipeline

| Agent | Role | Key Tech |
|-------|------|----------|
| **Perception** | Captures image + audio → detects objects, weapons, transcribes speech, infers emotion, detects context flags | YOLOv8, Groq Whisper (Hindi/English), VOSK (offline fallback) |
| **Intelligence** | Classifies intent (13 categories), computes risk score, generates reply, multi-turn conversation | Groq LLM (llama-3.3-70b), rule-based fallback, Hindi normalizer |
| **Decision** | Maps risk + intent → action using 12 policy rules | policy.yaml, threshold-based escalation |
| **Action** | Executes decision: TTS, notifications, DB logging | edge-tts (Hindi/English auto-detect), SQLite audit trail |

### 13 Intent Categories

`delivery` · `scam_attempt` · `aggression` · `occupancy_probe` · `identity_claim` · `entry_request` · `government_claim` · `domestic_staff` · `religious_donation` · `sales_marketing` · `child_elderly` · `help` · `visitor`

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui |
| **Backend** | FastAPI (Python 3.11) + SQLite + WebSocket |
| **Vision** | YOLOv8n (general detection) + custom weapon model |
| **STT** | Groq Whisper API (whisper-large-v3-turbo) + VOSK offline fallback |
| **LLM** | Groq API (llama-3.3-70b-versatile) |
| **TTS** | edge-tts (Hindi `hi-IN-SwaraNeural` / English `en-IN-NeerjaNeural`) |
| **Hindi Support** | Devanagari → Roman normalizer for keyword matching |
| **Auth** | Token-based auth with pbkdf2_hmac SHA-256 |

---

## Setup

### Prerequisites

- **Python 3.11+** (`py -3.11` on Windows)
- **Node.js 18+** and npm
- **Groq API key** — get one free at https://console.groq.com
- Webcam + microphone (for live testing)

### 1. Clone and enter the project

```powershell
cd Final-Year-Project
```

### 2. Backend Setup

```powershell
# Create and activate virtual environment
py -3.11 -m venv fyp-api
fyp-api\Scripts\activate

# Install Python dependencies
pip install -r api/requirements.txt

# Create required data directories
mkdir data\snaps, data\tts, data\logs, data\tmp, data\members -Force
```

### 3. Environment Variables

Copy the template and fill in your key:

```sh
cp .env.example .env
```

Then set your Groq key in `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Optional variables:

```env
DOORBELL_DB_PATH=data/db.sqlite    # SQLite database location (default: data/db.sqlite)
GROQ_MODEL=llama-3.3-70b-versatile # LLM model (default: llama-3.3-70b-versatile)
DOORBELL_DISABLE_YOLO=1            # Skip loading the weapon/YOLO model
DOORBELL_DISABLE_MODELS=1          # Skip loading all heavy models (Pi / tests)
```

> **Security:** `.env` is git-ignored and must **never** be committed — it holds your live API key. Only `.env.example` (no real values) is tracked. If a key is ever committed, rotate it at https://console.groq.com and remove it from history before pushing.

### 4. Start the Backend API

```powershell
fyp-api\Scripts\activate
python -m uvicorn api.main:app --reload --port 8000
```

The API is now running at **http://127.0.0.1:8000**
- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

#### Raspberry Pi note

If you open the frontend from another device on your network, start the backend on the Pi with:

```powershell
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

- Avoid `--reload` on Raspberry Pi unless you are actively editing code.
- Verify the backend locally on the Pi first with `http://127.0.0.1:8000/api/health`.
- Then access it from your laptop with `http://<pi-ip>:8000/api/health`.

### Deployment topology — laptop backend + Pi visitor kiosk

Recommended setup when the Raspberry Pi is too constrained to run the vision models:

- **Laptop** runs the FastAPI backend *and* the owner dashboard.
- **Raspberry Pi** runs *only* the visitor frontend, pointed at the laptop over the LAN.
- Both are on the same WiFi.

On the laptop:

```sh
./start-laptop.sh
# Find the LAN IP to give the Pi:
ipconfig getifaddr en0   # macOS
# or:  hostname -I | awk '{print $1}'   # Linux
```

`start-laptop.sh` binds `uvicorn` to `0.0.0.0:8000` so the Pi can reach it. Open the owner dashboard locally at `http://localhost:8080/` after starting the frontend with `npm run dev` in another terminal.

On the Raspberry Pi:

```sh
LAPTOP_IP=<the-laptop-ip> ./start-pi.sh
```

`start-pi.sh` exports `VITE_API_URL=http://<LAPTOP_IP>:8000` and starts Vite on `0.0.0.0:8080`. To boot the Pi straight into the visitor doorbell, point Chromium in kiosk mode at:

```sh
chromium-browser --kiosk http://localhost:8080/doorbell
```

The frontend's API resolver in [src/lib/api.ts](src/lib/api.ts) reads `VITE_API_URL` first, then falls back to `window.location.hostname:8000` — so leaving `VITE_API_URL` empty in `.env` works for both same-host and cross-device access.

### Weapon detection: OpenThreatDetection

Runtime weapon detection goes through [api/agents/openthreat_detector.py](api/agents/openthreat_detector.py), which loads weights from (in order):

1. `OPENTHREAT_WEIGHTS_PATH` env var (operator override)
2. `weapon_detection/openthreat/weights/best.pt` (the new home — see [weapon_detection/openthreat/README.md](weapon_detection/openthreat/README.md))
3. `weapon_detection/runs/detect/Normal_Compressed/weights/best.pt` (legacy YOLO fallback)

Drop the [IterateAI/OpenThreatDetection](https://github.com/IterateAI/OpenThreatDetection) `.pt` weights into option 2 to complete the swap. The legacy fallback keeps the system functional while you're sourcing the new weights.

### Vacation Mode

When the owner is away, toggle Vacation Mode from the dashboard header (the toggle next to "Logout"). Effects:

- The dashboard shows a sticky amber banner confirming the mode is on. State is persisted per-owner in SQLite, so a refresh or reconnect doesn't disable surveillance.
- The decision engine suppresses `auto_reply` and routes those interactions to `notify_owner` instead — escalation behaviour for weapons / scams / aggression is **unchanged**.
- The live-frame pipeline emits a `person_detected` WebSocket event to the `owner` channel on every confirmed person presence (two consecutive frames, 30-second cooldown). The payload carries a captured JPEG, a one-line scene description from `IntelligenceAgent.summarise_perception`, and a session ID. Each alert is also persisted as an `actions` row of type `vacation_person_alert`.

API surface:

```sh
# Read current settings
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/owner/settings
# {"vacation_mode": false}

# Turn Vacation Mode on
curl -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"vacation_mode": true}' \
  http://127.0.0.1:8000/api/owner/settings
```

### 5. Frontend Setup

In a **separate terminal**:

```powershell
# Install Node dependencies
npm install

# Start the dev server
npm run dev
```

The frontend is now running at **http://localhost:8080**
- Doorbell page: http://localhost:8080/doorbell
- Owner dashboard: http://localhost:8080/ (requires login)
- Member management: http://localhost:8080/members (requires login)

> The Vite dev server proxies `/api` requests to `http://127.0.0.1:8000` automatically.

If you access the Vite frontend from another device, the app now auto-resolves the backend to the same host on port `8000` when `VITE_API_URL` is still set to `localhost`.

### 6. Create an Owner Account

Open the dashboard at http://localhost:8080 and click **Register** to create your owner account. This enables:
- Viewing visitor logs and live visitor snapshots
- Replying to visitors (text or voice)
- Managing household members (name, phone, role, photo)

### 7. VOSK Models (optional — offline STT fallback)

Download from https://alphacephei.com/vosk/models and extract into `models/`:

```
models/
├── vosk-model-small-en-in-0.4/    # Indian English
└── vosk-model-small-hi-0.22/      # Hindi
```

These are only needed if Groq API is unavailable (offline fallback).

---

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/doorbell` | Visitor Doorbell | Ring button, webcam capture, mic recording, live transcript, TTS playback |
| `/` | Owner Dashboard | Live visitor view with snapshot, visitor history, reply (text/voice), stats |
| `/members` | Member Management | Add/edit/delete household members (name, phone, role, photo) |
| `/history` | Visitor History | Full visitor log with transcripts and risk scores |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/register` | Register a new owner account |
| `POST` | `/api/auth/login` | Login and get auth token |
| `POST` | `/api/auth/logout` | Invalidate token |
| `GET` | `/api/auth/me` | Get current user (incl. `vacation_mode`) |
| `GET` | `/api/owner/settings` | Read owner settings (`vacation_mode`) |
| `PUT` | `/api/owner/settings` | Update owner settings (e.g. toggle Vacation Mode) |
| `POST` | `/api/ring` | Ring the doorbell (image + audio → full pipeline) |
| `POST` | `/api/transcribe` | Transcribe audio (Groq Whisper STT) |
| `POST` | `/api/tts` | Generate TTS audio (Hindi/English auto-detect) |
| `POST` | `/api/ai-reply` | Send follow-up message → get AI reply |
| `POST` | `/api/owner-reply` | Owner replies to visitor |
| `GET` | `/api/session/{id}/status` | Get session pipeline status |
| `GET` | `/api/session/{id}/detail` | Get full session detail |
| `GET` | `/api/logs` | Get recent visitor logs |
| `GET/POST` | `/api/members` | List / create household members |
| `PUT/DELETE` | `/api/members/{id}` | Update / delete a member |
| `GET` | `/api/health` | Health check |
| `WS` | `/api/ws/{channel}` | WebSocket (channels: `owner`, `{session_id}`) |

---

## Testing

### Run All Tests (96 tests)

```powershell
fyp-api\Scripts\activate
python -m pytest api/tests/ -v
```

### Test by File

```powershell
# All agent tests (perception, intelligence, decision, action) — 78 tests
python -m pytest api/tests/test_all_agents.py -v

# Intelligence + Decision integration tests — 16 tests
python -m pytest api/tests/test_intelligence_decision.py -v

# FastAPI endpoint tests (ring, session, logs, auth) — 2 tests
python -m pytest api/tests/test_main.py -v

# Perception agent unit tests
python -m pytest api/tests/test_perception.py -v
```

### Test Options

```powershell
# Run tests with short output
python -m pytest api/tests/ -q

# Stop on first failure
python -m pytest api/tests/ -x

# Run a specific test by name
python -m pytest api/tests/test_all_agents.py -k "test_scam_otp"

# Run with full traceback on failure
python -m pytest api/tests/ -v --tb=long

# Disable model loading for faster tests (uses stubs)
$env:DOORBELL_DISABLE_MODELS="1"
python -m pytest api/tests/ -v
```

### Webcam Test (live camera → full pipeline)

Start the API server first, then in a second terminal:

```powershell
fyp-api\Scripts\activate

# Image only
python api/tests/test_webcam_ring.py

# Image + voice recording + TTS reply
python api/tests/test_webcam_ring.py --voice
```

- Webcam preview opens
- Press **R** to start/stop voice recording
- Press **SPACE** to capture image and send to the doorbell API
- Press **Q** to quit
- Polls session status until full pipeline completes

### Indian Scenario Tests (18 pre-defined scenarios)

Test the system against real-world Indian household visitor scenarios using webcam + voice:

```powershell
fyp-api\Scripts\activate

# Interactive scenario menu
python api/tests/test_webcam_ring.py --scenario

# Run a specific scenario by number
python api/tests/test_webcam_ring.py --voice --scenario 3

# Run multiple scenarios
python api/tests/test_webcam_ring.py --voice --scenario 1,3,8

# Run ALL 18 scenarios back-to-back with summary
python api/tests/test_webcam_ring.py --voice --scenario all
```

Each scenario displays a prompt on screen telling you what to say, then validates the AI pipeline's response against expected intent, action, and risk score.

#### Scenario List

| # | Category | Scenario | What to Say | Expected |
|---|----------|----------|-------------|----------|
| 1 | Delivery | Simple delivery | *"I have a package delivery"* | `auto_reply` |
| 2 | Delivery | COD payment request | *"1299 rupees COD hai, change milega kya?"* | `notify_owner` |
| 3 | Scam | OTP scam attempt | *"Sir OTP bata dijiye, delivery complete karna hai"* | `escalate` |
| 4 | Domestic Staff | New maid claiming replacement | *"Main aaj se kaam karungi, purani bai nahi aayegi"* | `notify_owner` |
| 5 | Religious | Temple donation collection | *"Mandir ke liye chanda hai"* | `auto_reply` |
| 6 | Government | KYC verification scam | *"Aadhaar KYC verification hai"* | `escalate` |
| 7 | Government | Electricity board claim | *"Bijli check karne aaye hain"* | `notify_owner` |
| 8 | Social Eng. | Occupancy probe | *"Koi ghar pe hai?"* | `escalate` |
| 9 | Social Eng. | Identity claim bypass | *"I know the owner personally, let me in"* | `escalate` |
| 10 | Aggression | Verbal threat | *"Darwaza kholo warna dekh lena"* | `escalate` |
| 11 | Child/Elderly | Lost child | *"Mummy kho gayi"* (small voice) | `notify_owner` |
| 12 | Child/Elderly | Elderly asking for water | *"Bhai sahab, paani milega?"* | `notify_owner` |
| 13 | Emergency | Fire emergency | *"Help! Aag lag gayi hai!"* | `escalate` |
| 14 | Sales | Water purifier demo | *"Free demo hai water purifier ka"* | `auto_reply` |
| 15 | Financial | UPI transfer request | *"QR scan kar dijiye, refund dena hai"* | `escalate` |
| 16 | Silent | Silent visitor (no speech) | *(Stay silent)* | `notify_owner` |
| 17 | Visitor | Friend wants to meet owner | *"I want to speak with the owner please"* | `auto_reply` |
| 18 | Entry Request | Delivery asking to enter | *"Lift use karna hai, andar aana padega"* | `escalate` |

### Manual API Test (curl)

```powershell
# Health check
curl http://127.0.0.1:8000/api/health

# Ring the doorbell (no image/audio)
curl -X POST http://127.0.0.1:8000/api/ring `
  -H "Content-Type: application/json" `
  -d '{"type":"ring","timestamp":"2026-02-15T12:00:00Z","device_id":"frontdoor-01"}'

# Register an owner
curl -X POST http://127.0.0.1:8000/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"password123","name":"Owner"}'

# Login
curl -X POST http://127.0.0.1:8000/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"password123"}'

# Get visitor logs
curl http://127.0.0.1:8000/api/logs

# Transcribe audio (base64-encoded audio)
curl -X POST http://127.0.0.1:8000/api/tts `
  -H "Content-Type: application/json" `
  -d '{"text":"Namaste, kaise hain aap?","session_id":"test_hindi"}'
```

### Manual API Test (Swagger UI)

1. Open http://127.0.0.1:8000/docs
2. Try `POST /api/ring` with:
   ```json
   {
     "type": "ring",
     "timestamp": "2026-02-15T12:00:00Z",
     "device_id": "frontdoor-01"
   }
   ```
3. Copy the `sessionId` from response
4. Try `GET /api/session/{sessionId}/detail` to see full pipeline results

### Frontend Build Test

```powershell
# TypeScript type check (should produce no errors)
npx tsc --noEmit

# Production build (should compile 1733+ modules)
npm run build

# Preview production build
npm run preview
```

---

## Project Structure

```
├── api/                           # Python backend
│   ├── agents/
│   │   ├── perception_agent.py    # Vision + STT + context flags
│   │   ├── intelligence_agent.py  # Intent + risk + LLM reply + conversation
│   │   ├── decision_agent.py      # Policy rules → action
│   │   └── action_agent.py        # TTS + notifications + DB logging
│   ├── utils/
│   │   ├── tts.py                 # TTS audio generation (Hindi/English)
│   │   └── hindi_normalize.py     # Devanagari → Roman normalizer
│   ├── policies/
│   │   └── policy.yaml            # Decision rules + thresholds
│   ├── prompts/
│   │   └── groq_system_prompt.txt # LLM system prompt
│   ├── tests/
│   │   ├── test_all_agents.py     # 78 comprehensive agent tests
│   │   ├── test_intelligence_decision.py  # 16 integration tests
│   │   ├── test_main.py           # 2 FastAPI endpoint tests
│   │   ├── test_perception.py     # Perception unit tests
│   │   └── test_webcam_ring.py    # Live webcam + 18 scenario tests
│   ├── db.py                      # SQLite database layer
│   ├── models.py                  # Pydantic models
│   ├── orchestrator.py            # Agent pipeline orchestrator
│   └── main.py                    # FastAPI app + all endpoints
├── src/                           # React frontend
│   ├── pages/
│   │   ├── Doorbell.tsx           # Visitor doorbell interface
│   │   ├── Dashboard.tsx          # Owner dashboard + live view
│   │   ├── Members.tsx            # Member management
│   │   ├── VisitorHistory.tsx     # Visitor history
│   │   └── Login.tsx              # Auth (login/register)
│   ├── lib/
│   │   └── api.ts                 # API client (REST + WebSocket + TTS)
│   ├── contexts/
│   │   └── AuthContext.tsx         # Auth state management
│   └── components/                # Reusable UI components
├── data/                          # Runtime data (gitignored)
│   ├── snaps/                     # Visitor snapshots
│   ├── tts/                       # Generated TTS audio files
│   ├── logs/                      # Agent logs
│   ├── members/                   # Member photos
│   └── tmp/                       # Temporary session files
├── models/                        # VOSK STT models (offline, gitignored)
├── weapon_detection/              # Custom weapon detection model
├── .env.example                   # Env template (tracked — copy to .env)
├── .env                           # API keys (gitignored — never commit)
├── package.json                   # Node dependencies
└── api/requirements.txt           # Python dependencies
```

> Internal reports and planning docs (`*REPORT*.md`, `CURRENT_IMPLEMENTED_SYSTEM.md`, `IMPLEMENTATION_PLAN.md`, `plan.md`, etc.) are git-ignored and kept for local reference only.
