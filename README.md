# Smart Doorbell — Multi-Agent AI Security System

An AI-powered smart doorbell system designed for **Indian households** that uses a multi-agent architecture to detect, classify, and respond to visitors in real-time. Supports Hindi, English, and Hinglish speech with automatic threat detection, scam prevention, and owner notification.

## Architecture

```
┌─────────────┐     ┌───────────────────┐     ┌────────────────────┐
│  Doorbell    │────▶│  Perception Agent  │────▶│ Intelligence Agent │
│  (Camera +   │     │  • YOLOv8 vision   │     │  • Groq Whisper STT│
│   Mic)       │     │  • Weapon detection │     │  • Intent classify │
└─────────────┘     │  • Context flags    │     │  • Risk scoring    │
                    └───────────────────┘     │  • LLM replies     │
                                              └────────┬───────────┘
                                                       │
                    ┌───────────────────┐     ┌────────▼───────────┐
                    │   Action Agent     │◀────│  Decision Agent    │
                    │  • TTS generation  │     │  • 12 policy rules │
                    │  • Notifications   │     │  • Escalation logic│
                    │  • DB audit trail  │     │  • Indian scenarios│
                    └───────────────────┘     └────────────────────┘
```

### Agent Pipeline

| Agent | Role | Key Tech |
|-------|------|----------|
| **Perception** | Captures image + audio → detects objects, weapons, transcribes speech, infers emotion, detects context flags | YOLOv8, Groq Whisper (Hindi/English), VOSK (offline fallback) |
| **Intelligence** | Classifies intent (13 categories), computes risk score, generates reply | Groq LLM (llama-3.3-70b), rule-based fallback, Hindi normalizer |
| **Decision** | Maps risk + intent → action using 12 policy rules | policy.yaml, threshold-based escalation |
| **Action** | Executes decision: TTS, notifications, DB logging | pyttsx3/espeak TTS, SQLite audit trail |

### 13 Intent Categories

`delivery` · `scam_attempt` · `aggression` · `occupancy_probe` · `identity_claim` · `entry_request` · `government_claim` · `domestic_staff` · `religious_donation` · `sales_marketing` · `child_elderly` · `help` · `visitor`

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS + shadcn-ui
- **Backend**: FastAPI (Python 3.11) + SQLite
- **Vision**: YOLOv8n (general detection) + custom weapon model
- **STT**: Groq Whisper API (whisper-large-v3-turbo) with VOSK offline fallback
- **LLM**: Groq API (llama-3.3-70b-versatile)
- **TTS**: pyttsx3 (Windows) / espeak (Raspberry Pi)
- **Hindi Support**: Devanagari → Roman normalizer for keyword matching

---

## Setup

### Prerequisites

- Python 3.11+ (`py -3.11` on Windows)
- Node.js 18+ and npm
- Webcam + microphone (for live testing)

### Backend (API)

```powershell
# Create virtual environment
py -3.11 -m venv fyp-api
fyp-api\Scripts\activate
pip install -r api/requirements.txt

# Create data directories
mkdir data\snaps, data\tts, data\logs, data\tmp -Force
```

### Environment Variables

Create a `.env` file in project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

### Start the API Server

```powershell
fyp-api\Scripts\activate
python -m uvicorn api.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

### Frontend

```sh
npm install
npm run dev
```

### VOSK Models (offline STT fallback)

Download from https://alphacephei.com/vosk/models and extract into `models/`:

```
models/
├── vosk-model-small-en-in-0.4/    # Indian English
└── vosk-model-small-hi-0.22/      # Hindi
```

---

## Testing

### Unit Tests (96 tests)

```powershell
fyp-api\Scripts\activate
$env:DOORBELL_DISABLE_MODELS="1"
python -m pytest api/tests/ -v
```

Tests cover all 4 agents, 13 intents, 12 decision rules, TTS utility, Hindi normalization, and end-to-end pipeline integration.

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

#### Example: Running Scenario 3 (OTP Scam)

```powershell
python api/tests/test_webcam_ring.py --voice --scenario 3
```

```
============================================================
  SCENARIO 3: OTP scam attempt
  Category: scam
  Say: 'Sir OTP bata dijiye, delivery complete karna hai'
  Expected: intent=scam_attempt, action=escalate
============================================================

  [MIC] Recording started... speak now
  [MIC] Recording stopped — 4.4s captured

  RESULT:
    Transcript: "सर ओटीपी बता दिजे डिलिवरी कमप्लीट करना है"
    AI Reply:   "I cannot share any OTP, bank details, or personal information.
                 The owner has been notified."
    Risk Score: 1.0
    Actions:    ['escalate', 'escalation_notification']
    Status: ✅ PASS
```

The system correctly:
1. Transcribed Hindi speech via Groq Whisper
2. Normalized Devanagari → Roman keywords (`ओटीपी` → `otp`)
3. Classified intent as `scam_attempt` (risk: 1.0)
4. Escalated with security notification
5. Replied with a safe canned message (no OTP/bank info shared)

### Manual API Test (Swagger UI)

1. Open http://127.0.0.1:8000/docs
2. Try `POST /api/ring` with:
   ```json
   {
     "type": "ring",
     "timestamp": "2026-02-14T12:00:00Z",
     "device_id": "frontdoor-01"
   }
   ```
3. Copy the `sessionId` from response
4. Try `GET /api/session/{sessionId}/status` to watch pipeline progress

---

## Project Structure

```
api/
├── agents/
│   ├── perception_agent.py    # Vision + STT + context flags
│   ├── intelligence_agent.py  # Intent + risk + LLM reply
│   ├── decision_agent.py      # Policy rules → action
│   └── action_agent.py        # TTS + notifications + DB logging
├── utils/
│   ├── tts.py                 # TTS audio generation
│   └── hindi_normalize.py     # Devanagari → Roman normalizer
├── policies/
│   └── policy.yaml            # Decision rules + thresholds
├── prompts/
│   └── groq_system_prompt.txt # LLM system prompt (45 rules)
├── tests/
│   ├── test_all_agents.py     # 78 comprehensive agent tests
│   ├── test_intelligence_decision.py
│   ├── test_webcam_ring.py    # Live webcam + 18 scenario tests
│   └── ...
├── db.py                      # SQLite database layer
├── models.py                  # Pydantic models
├── orchestrator.py            # Agent pipeline orchestrator
└── main.py                    # FastAPI app
src/                           # React frontend
weapon_detection/              # Custom weapon detection model
models/                        # VOSK STT models
```
