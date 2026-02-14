# Welcome to your Lovable project

## Project info

**URL**: https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID

## How can I edit this code?

There are several ways of editing your application.

**Use Lovable**

Simply visit the [Lovable Project](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and start prompting.

Changes made via Lovable will be committed automatically to this repo.

**Use your preferred IDE**

If you want to work locally using your own IDE, you can clone this repo and push changes. Pushed changes will also be reflected in Lovable.

The only requirement is having Node.js & npm installed - [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating)

Follow these steps:

```sh
# Step 1: Clone the repository using the project's Git URL.
git clone <YOUR_GIT_URL>

# Step 2: Navigate to the project directory.
cd <YOUR_PROJECT_NAME>

# Step 3: Install the necessary dependencies.
npm i

# Step 4: Start the development server with auto-reloading and an instant preview.
npm run dev
```

**Edit a file directly in GitHub**

- Navigate to the desired file(s).
- Click the "Edit" button (pencil icon) at the top right of the file view.
- Make your changes and commit the changes.

**Use GitHub Codespaces**

- Navigate to the main page of your repository.
- Click on the "Code" button (green button) near the top right.
- Select the "Codespaces" tab.
- Click on "New codespace" to launch a new Codespace environment.
- Edit files directly within the Codespace and commit and push your changes once you're done.

## What technologies are used for this project?

This project is built with:

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS
- FastAPI (Python backend)
- SQLite (persistence)
- YOLOv8 (object & weapon detection)
- VOSK (offline speech-to-text)
- Groq API (LLM intelligence)

---

## Backend Setup (API)

### Prerequisites

- Python 3.11 installed (`py -3.11` on Windows)
- VOSK models in `models/` (optional, for STT)

### Create virtual environment

```powershell
# From project root
py -3.11 -m venv fyp-api
fyp-api\Scripts\activate
pip install -r api/requirements.txt
```

### Create required data folders

```powershell
mkdir data\snaps, data\tts, data\logs, data\tmp -Force
```

### Environment variables

Create a `.env` file in project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

### Start the API server

```powershell
fyp-api\Scripts\activate
python -m uvicorn api.main:app --reload --port 8000
```

API docs available at: http://127.0.0.1:8000/docs

### Run tests

```powershell
fyp-api\Scripts\activate
python -m pytest api/tests/ -v
```

### Webcam test (live camera → full agent pipeline)

Start the API server first, then in a second terminal:

```powershell
fyp-api\Scripts\activate
python api/tests/test_webcam_ring.py
```

- Webcam preview opens
- Press **SPACE** to capture and send to the doorbell API
- Press **Q** to quit
- Polls session status until pipeline completes

### Manual API test (Swagger UI)

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

### VOSK models (for speech-to-text)

Download from https://alphacephei.com/vosk/models and extract into `models/`:

```
models/
├── vosk-model-small-en-in-0.4/    # Indian English
└── vosk-model-small-hi-0.22/      # Hindi
```

---

## How can I deploy this project?

Simply open [Lovable](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and click on Share -> Publish.

## Can I connect a custom domain to my Lovable project?

Yes, you can!

To connect a domain, navigate to Project > Settings > Domains and click Connect Domain.

Read more here: [Setting up a custom domain](https://docs.lovable.dev/features/custom-domain#custom-domain)
