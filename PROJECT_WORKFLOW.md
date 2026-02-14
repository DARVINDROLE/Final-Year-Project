# Smart Doorbell System - Complete Project Workflow

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Architecture Overview](#architecture-overview)
4. [Frontend-Backend Connection](#frontend-backend-connection)
5. [Backend Details](#backend-details)
6. [Frontend Details](#frontend-details)
7. [Complete Workflows](#complete-workflows)
8. [Data Flow](#data-flow)
9. [Deployment Configuration](#deployment-configuration)

---

## 🎯 Project Overview

This is an intelligent Smart Doorbell System that uses AI to interact with visitors at the door. The system consists of:
- **Frontend**: React + TypeScript + Vite application with a webcam interface for visitors
- **Backend**: FastAPI Python server using LangChain and Groq LLM for AI responses
- **Deployment**: Vercel (Frontend + Serverless Backend)

**Key Features**:
- AI-powered conversation with visitors
- Real-time speech recognition and text-to-speech
- Webcam image capture
- Visitor log management
- Owner dashboard with visitor history
- Multi-language support (English & Hindi)

---

## 🛠 Technology Stack

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **UI Library**: Shadcn/ui (Radix UI components)
- **Styling**: Tailwind CSS
- **Routing**: React Router v6
- **State Management**: React Query (@tanstack/react-query)
- **Webcam**: react-webcam
- **Speech Recognition**: Web Speech API (browser native)
- **Text-to-Speech**: Web Speech Synthesis API (browser native)

### Backend
- **Framework**: FastAPI
- **Server**: Uvicorn
- **AI/LLM**: LangChain + Groq (llama-3.3-70b-versatile model)
- **Data Validation**: Pydantic
- **Environment**: python-dotenv
- **CORS**: FastAPI CORS Middleware

### Deployment
- **Platform**: Vercel
- **Frontend**: Static site generation
- **Backend**: Serverless Functions (Python)

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         VERCEL PLATFORM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────────────┐         ┌────────────────────────┐  │
│  │   FRONTEND (React)     │         │  BACKEND (FastAPI)     │  │
│  │   Port: 8080 (dev)     │────────▶│  Serverless Function   │  │
│  │                        │  HTTP   │                        │  │
│  │  - Doorbell UI         │ Requests│  - AI Response Engine  │  │
│  │  - Dashboard           │◀────────│  - Session Management  │  │
│  │  - Visitor History     │  JSON   │  - Visitor Logs        │  │
│  │  - Webcam Capture      │         │                        │  │
│  │  - Speech Recognition  │         │                        │  │
│  │  - TTS (Browser-based) │         │                        │  │
│  └───────────────────────┘         └────────────────────────┘  │
│           │                                    │                 │
│           │                                    │                 │
└───────────┼────────────────────────────────────┼─────────────────┘
            │                                    │
            ▼                                    ▼
     User's Browser                        Groq AI API
     - WebRTC Camera                    (LLM: llama-3.3-70b)
     - Web Speech API
```

---

## 🔗 Frontend-Backend Connection

### Development Environment
In development, the frontend runs on `http://localhost:8080` and connects to the backend on `http://localhost:8000` via **Vite Proxy**.

**Vite Configuration** (`vite.config.ts`):
```typescript
proxy: {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    secure: false,
  },
}
```

### Production Environment
In production on Vercel, both frontend and backend are served from the same domain using **Vercel Rewrites**.

**Vercel Configuration** (`vercel.json`):
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

### API Base URL Logic
The frontend uses environment-aware API URLs (`src/lib/api.ts`):
```typescript
const API_BASE_URL = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_URL || '');
```
- **Development**: Uses Vite proxy (empty string → proxied to localhost:8000)
- **Production**: Uses relative paths (empty string → same domain)

---

## 🔧 Backend Details

### File Structure
```
api/
├── index.py          # Main FastAPI application
├── requirements.txt  # Python dependencies
└── __pycache__/     # Compiled Python files
```

### Core Components

#### 1. **SmartDoorbell Class**
The main AI engine that handles visitor interactions.

**Initialization**:
```python
def __init__(self, api_key: str):
    self.llm = ChatGroq(
        temperature=0.7,
        groq_api_key=api_key,
        model_name="llama-3.3-70b-versatile"
    )
    self.sessions = {}  # In-memory session storage
    self.logs = []      # In-memory visitor logs
```

**Key Features**:
- Uses **LangChain** to manage conversation history
- Each visitor gets a unique session ID
- Maintains conversation context throughout the session
- Stores all interactions in logs

**AI System Prompt**:
The AI is configured with specific behavioral rules:
- Respond in **one short sentence only**
- Match the **visitor's language** (Hindi or English)
- Handle different visitor types:
  - **Delivery**: Direct to parcel box
  - **Friend/Family**: Notify owner
  - **Solicitor**: Politely decline
  - **Neighbor**: Greet and ask if urgent
- **Security Protocol**: If suspicious behavior detected, respond with "I have notified the owner and security guard"
- Never reveal personal or security information

#### 2. **API Endpoints**

##### `GET /api/health`
**Purpose**: Health check endpoint

**Response**:
```json
{
  "status": "ok",
  "service": "smart-doorbell-backend"
}
```

##### `POST /api/ring`
**Purpose**: Initiated when visitor presses doorbell button

**Input**:
```json
{
  "image": "data:image/jpeg;base64,..." // Optional base64 image
}
```

**Process**:
1. Generate unique session ID (format: `visitor_<8-char-uuid>`)
2. Create initial greeting message via LLM
3. Store image URL (or use placeholder)
4. Initialize visitor log entry
5. Return session details

**Output**:
```json
{
  "sessionId": "visitor_abc12345",
  "greeting": "Hello! Welcome to the Kandell residence. How may I help you?",
  "imageUrl": "/placeholder.svg"
}
```

##### `POST /api/ai-reply`
**Purpose**: Process visitor's message and generate AI response

**Input**:
```json
{
  "sessionId": "visitor_abc12345",
  "message": "I have a package delivery"
}
```

**Process**:
1. Retrieve session conversation history
2. Add visitor message to history
3. Send conversation to LLM (Groq)
4. Get AI response
5. Update conversation history
6. Update visitor logs
7. Return response

**Output**:
```json
{
  "reply": "Thank you! Please place the package in the Parcel Box on the left.",
  "summary": "Visitor interaction",
  "visitorType": "unknown"
}
```

##### `POST /api/tts`
**Purpose**: Text-to-speech endpoint (currently disabled - frontend handles TTS)

**Status**: Returns success but no server-side audio processing

##### `POST /api/capture-image`
**Purpose**: Image capture endpoint (returns placeholder)

**Output**:
```json
{
  "imageUrl": "/placeholder.svg"
}
```

##### `GET /api/logs`
**Purpose**: Retrieve all visitor interaction logs

**Output**:
```json
[
  {
    "id": "visitor_abc12345",
    "timestamp": "2026-02-14T10:30:00.123Z",
    "imageUrl": "/placeholder.svg",
    "transcript": [
      {
        "role": "doorbell",
        "content": "Hello! Welcome...",
        "timestamp": "2026-02-14T10:30:00.123Z"
      },
      {
        "role": "visitor",
        "content": "I have a package",
        "timestamp": "2026-02-14T10:30:15.456Z"
      }
    ],
    "status": "active",
    "aiSummary": "Visitor interaction",
    "visitorType": "unknown"
  }
]
```

##### `POST /api/owner-reply`
**Purpose**: Allow owner to send message to visitor

**Input**:
```json
{
  "sessionId": "visitor_abc12345",
  "message": "I'll be there in 5 minutes"
}
```

**Process**:
1. Find visitor log by session ID
2. Append owner's message to transcript
3. Mark message with `[Owner]` prefix

**Output**:
```json
{
  "status": "success"
}
```

#### 3. **Session Management**

**In-Memory Storage**:
```python
self.sessions = {
  "visitor_abc12345": [
    SystemMessage(content="You are the Smart Doorbell AI..."),
    HumanMessage(content="Hello"),
    AIMessage(content="Hello! How may I help you?")
  ]
}
```

**Note**: Sessions are stored in memory and reset on cold starts (Vercel serverless limitation)

#### 4. **LangChain Integration**

**Flow**:
1. System prompt defines AI behavior
2. Conversation history maintained per session
3. Each new message is added to history
4. Full history sent to LLM for context-aware responses
5. LLM response added to history

**Example**:
```python
def get_response(self, visitor_input: str, session_id: str):
    history = self._get_session_history(session_id)  # Get conversation history
    history.append(HumanMessage(content=visitor_input))  # Add visitor message
    
    response = self.llm.invoke(history)  # Send to LLM
    history.append(response)  # Add AI response to history
    
    return response.content
```

---

## 💻 Frontend Details

### File Structure
```
src/
├── main.tsx              # App entry point
├── App.tsx               # Main app with routing
├── lib/
│   ├── api.ts           # API communication layer
│   └── utils.ts         # Utility functions
├── hooks/
│   ├── useSpeechRecognition.ts  # Speech recognition hook
│   └── use-toast.ts     # Toast notifications
├── pages/
│   ├── Index.tsx        # Landing page
│   ├── Doorbell.tsx     # Main doorbell interface
│   ├── Dashboard.tsx    # Owner dashboard
│   ├── VisitorHistory.tsx  # Visitor history
│   ├── Login.tsx        # Authentication
│   └── NotFound.tsx     # 404 page
└── components/
    ├── RingButton.tsx   # Doorbell button component
    ├── StatusIndicator.tsx  # Status display
    ├── TranscriptDisplay.tsx  # Conversation display
    ├── VisitorCard.tsx  # Visitor card component
    └── ui/              # Shadcn/ui components
```

### Key Components

#### 1. **API Layer** (`src/lib/api.ts`)

**Main Functions**:

##### `ringDoorbell(image?: string)`
- Sends POST request to `/api/ring`
- Passes base64-encoded webcam image
- Returns session ID and greeting message
- Fallback to mock data if backend unavailable

##### `getAIReply(sessionId: string, message: string)`
- Sends POST request to `/api/ai-reply`
- Sends visitor's message with session ID
- Returns AI-generated response
- Fallback to mock response on error

##### `speakText(text: string)`
- Uses browser's **Web Speech Synthesis API**
- No backend dependency
- Creates utterance with text
- Speaks using browser's TTS engine

##### `getVisitorLogs()`
- Fetches all visitor logs from `/api/logs`
- Returns array of visitor objects
- Fallback to mock data for demo

##### `ownerReply(sessionId: string, message: string)`
- Sends owner's message to `/api/owner-reply`
- Appends message to visitor's transcript

##### Authentication Functions:
- `login(username, password)` - Simple demo authentication
- `logout()` - Clears localStorage token
- `isAuthenticated()` - Checks for valid token

#### 2. **Speech Recognition Hook** (`src/hooks/useSpeechRecognition.ts`)

Uses browser's **Web Speech API**:
```typescript
const recognition = new webkitSpeechRecognition(); // or SpeechRecognition
recognition.continuous = false;
recognition.interimResults = false;
recognition.lang = 'en-US';
```

**Features**:
- Start/stop listening
- Automatic result callback
- Error handling
- State management (isListening)

#### 3. **Doorbell Page** (`src/pages/Doorbell.tsx`)

**State Machine**:
```
idle → ringing → greeting → speaking → awaiting_input → processing → speaking → awaiting_input
```

**State Flow**:
1. **idle**: Initial state, waiting for doorbell ring
2. **ringing**: Connecting to backend, capturing image
3. **greeting**: Receiving greeting from backend
4. **speaking**: Playing TTS audio
5. **awaiting_input**: Listening for visitor's speech
6. **processing**: Sending message to AI, waiting for response

**Key Features**:
- Webcam integration via `react-webcam`
- Real-time camera preview
- Automatic speech recognition when `awaiting_input`
- Manual text input option
- Transcript display with timestamps
- Status indicator for current state
- Fullscreen mode support
- Camera error handling

**Main Functions**:

##### `handleRing()`
1. Set state to "ringing"
2. Capture webcam screenshot
3. Call `ringDoorbell(imageSrc)` API
4. Receive session ID and greeting
5. Display greeting in transcript
6. Speak greeting using TTS
7. Transition to "awaiting_input" state
8. Start listening for visitor

##### `handleSendMessage(message)`
1. Add visitor message to transcript
2. Set state to "processing"
3. Call `getAIReply(sessionId, message)` API
4. Receive AI response
5. Add AI response to transcript
6. Speak response using TTS
7. Return to "awaiting_input" state
8. Resume listening

#### 4. **Dashboard Page** (`src/pages/Dashboard.tsx`)

**Features**:
- Display active visitors (status: 'active')
- Display recent visitors (status: 'completed')
- View detailed visitor logs
- Send replies to active visitors
- Refresh visitor list
- Navigate to full history
- Emergency alert button
- Logout functionality

**Protection**: Route protected by `isAuthenticated()` check

**Key Functions**:

##### `loadVisitors()`
- Calls `getVisitorLogs()` API
- Updates visitor state
- Handles loading state

##### `handleRespond(visitor)`
- Opens reply modal
- Allows owner to type message
- Calls `ownerReply()` API
- Sends message to visitor

#### 5. **Visitor History Page** (`src/pages/VisitorHistory.tsx`)

**Features**:
- Complete history of all visitors
- Filter by visitor type (delivery, friend, solicitor, neighbor)
- Search functionality
- Sort by date
- Detailed transcript view
- Pagination support

---

## 🔄 Complete Workflows

### Workflow 1: Visitor Rings Doorbell

```
┌─────────────┐
│   VISITOR   │
│  (Browser)  │
└──────┬──────┘
       │
       │ 1. Opens /doorbell page
       ▼
┌─────────────────────────────────────┐
│  FRONTEND: Doorbell.tsx             │
│  State: idle                        │
│  - Webcam initializes               │
│  - Request camera permissions       │
└──────────────┬──────────────────────┘
               │
               │ 2. Visitor clicks Ring Button
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: handleRing()             │
│  - State → ringing                  │
│  - Capture webcam screenshot        │
│  - webcamRef.current.getScreenshot()│
└──────────────┬──────────────────────┘
               │
               │ 3. POST /api/ring { image: "data:image/..." }
               ▼
┌─────────────────────────────────────┐
│  BACKEND: /api/ring endpoint        │
│  - Generate session ID              │
│  - Store image URL                  │
│  - Call doorbell.get_response()     │
│    with "The doorbell button        │
│    was pressed."                    │
└──────────────┬──────────────────────┘
               │
               │ 4. LangChain + Groq LLM
               ▼
┌─────────────────────────────────────┐
│  AI ENGINE: SmartDoorbell           │
│  - Load system prompt               │
│  - Generate greeting                │
│  - Create session history           │
│  - Update logs                      │
└──────────────┬──────────────────────┘
               │
               │ 5. Returns { sessionId, greeting, imageUrl }
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: Receives response        │
│  - Store sessionId                  │
│  - State → speaking                 │
│  - Add greeting to transcript       │
│  - Call speakText(greeting)         │
└──────────────┬──────────────────────┘
               │
               │ 6. Browser TTS plays audio
               ▼
┌─────────────────────────────────────┐
│  BROWSER: Web Speech Synthesis      │
│  - speechSynthesis.speak()          │
│  - Plays AI greeting                │
└──────────────┬──────────────────────┘
               │
               │ 7. TTS complete
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: After TTS                │
│  - State → awaiting_input           │
│  - Start speech recognition         │
│  - startListening()                 │
└──────────────┬──────────────────────┘
               │
               │ 8. Listening for visitor
               ▼
       ┌───────────────┐
       │ READY FOR     │
       │ CONVERSATION  │
       └───────────────┘
```

### Workflow 2: Visitor Speaks

```
┌─────────────┐
│   VISITOR   │
│   Speaks    │
└──────┬──────┘
       │
       │ 1. "I have a package for delivery"
       ▼
┌─────────────────────────────────────┐
│  BROWSER: Web Speech Recognition    │
│  - webkitSpeechRecognition          │
│  - Captures audio                   │
│  - Converts to text                 │
└──────────────┬──────────────────────┘
               │
               │ 2. onResult callback
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: handleSendMessage()      │
│  - Add visitor msg to transcript    │
│  - State → processing               │
└──────────────┬──────────────────────┘
               │
               │ 3. POST /api/ai-reply
               │    { sessionId, message }
               ▼
┌─────────────────────────────────────┐
│  BACKEND: /api/ai-reply endpoint    │
│  - Retrieve session history         │
│  - Append visitor message           │
└──────────────┬──────────────────────┘
               │
               │ 4. Send to LLM with history
               ▼
┌─────────────────────────────────────┐
│  GROQ AI: llama-3.3-70b-versatile   │
│  Input: Full conversation history   │
│  - System prompt                    │
│  - Previous messages                │
│  - New visitor message              │
│                                     │
│  AI Processing:                     │
│  - Analyze message                  │
│  - Detect language                  │
│  - Identify visitor type            │
│  - Check for security concerns      │
│  - Generate appropriate response    │
└──────────────┬──────────────────────┘
               │
               │ 5. AI generates response
               │    "Please place the package
               │     in the Parcel Box on the left."
               ▼
┌─────────────────────────────────────┐
│  BACKEND: Process response          │
│  - Append to session history        │
│  - Update visitor logs              │
│  - Add to transcript                │
└──────────────┬──────────────────────┘
               │
               │ 6. Returns { reply, summary, visitorType }
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: Receives AI reply        │
│  - Add to transcript                │
│  - State → speaking                 │
│  - Call speakText(reply)            │
└──────────────┬──────────────────────┘
               │
               │ 7. Browser TTS
               ▼
┌─────────────────────────────────────┐
│  BROWSER: Speaks AI response        │
└──────────────┬──────────────────────┘
               │
               │ 8. Complete
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: Resume listening         │
│  - State → awaiting_input           │
│  - startListening()                 │
└─────────────────────────────────────┘
```

### Workflow 3: Owner Views Dashboard

```
┌─────────────┐
│    OWNER    │
│  (Browser)  │
└──────┬──────┘
       │
       │ 1. Opens /dashboard
       ▼
┌─────────────────────────────────────┐
│  FRONTEND: Dashboard.tsx            │
│  - Check isAuthenticated()          │
│  - Redirect to /login if not auth   │
└──────────────┬──────────────────────┘
               │
               │ 2. Authenticated
               │    Call loadVisitors()
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: API call                 │
│  - GET /api/logs                    │
└──────────────┬──────────────────────┘
               │
               │ 3. Request visitor logs
               ▼
┌─────────────────────────────────────┐
│  BACKEND: /api/logs endpoint        │
│  - Return doorbell.logs array       │
│  - All visitor sessions             │
│  - Complete transcripts             │
└──────────────┬──────────────────────┘
               │
               │ 4. Returns visitor logs array
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: Display visitors         │
│  - Filter active visitors           │
│  - Show recent visitors             │
│  - Display transcripts              │
│  - Show visitor images              │
└──────────────┬──────────────────────┘
               │
               │ 5. Owner clicks "Respond"
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: handleRespond()          │
│  - Open reply modal                 │
│  - Owner types message              │
└──────────────┬──────────────────────┘
               │
               │ 6. POST /api/owner-reply
               │    { sessionId, message }
               ▼
┌─────────────────────────────────────┐
│  BACKEND: /api/owner-reply endpoint │
│  - Find visitor log by session ID   │
│  - Append [Owner] message           │
│  - Update transcript                │
└──────────────┬──────────────────────┘
               │
               │ 7. Returns { status: "success" }
               ▼
┌─────────────────────────────────────┐
│  FRONTEND: Message sent             │
│  - Display success toast            │
│  - Refresh visitor logs             │
│  - Close modal                      │
└─────────────────────────────────────┘
```

---

## 📊 Data Flow

### Data Types

#### Visitor Object
```typescript
interface Visitor {
  id: string;                    // Session ID (e.g., "visitor_abc12345")
  timestamp: string;             // ISO timestamp
  imageUrl: string | null;       // Webcam capture or placeholder
  transcript: TranscriptEntry[]; // Conversation history
  status: 'active' | 'completed' | 'ignored';
  aiSummary: string;            // AI-generated summary
  visitorType: 'delivery' | 'friend' | 'solicitor' | 'neighbor' | 'unknown';
}
```

#### Transcript Entry
```typescript
interface TranscriptEntry {
  role: 'visitor' | 'doorbell';  // Who spoke
  content: string;               // Message content
  timestamp: string;             // ISO timestamp
}
```

### Data Storage

**Backend (In-Memory)**:
```python
# Session conversation histories
self.sessions = {
  "visitor_abc123": [SystemMessage(...), HumanMessage(...), AIMessage(...)]
}

# Visitor logs
self.logs = [
  {
    "id": "visitor_abc123",
    "timestamp": "2026-02-14T10:30:00",
    "imageUrl": "/placeholder.svg",
    "transcript": [...],
    "status": "active",
    "aiSummary": "Delivery person",
    "visitorType": "delivery"
  }
]
```

**Frontend (React State)**:
- `sessionId`: Current visitor session
- `transcript`: Current conversation
- `state`: Doorbell state machine
- `visitors`: All visitor logs (Dashboard)

**Browser Storage**:
- `localStorage.doorbell_token`: Authentication token

---

## 🚀 Deployment Configuration

### Vercel Deployment

**Structure**:
```
/                    → Frontend (React SPA)
/api/*              → Backend (Python Serverless Functions)
```

**Vercel JSON** (`vercel.json`):
```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/index.py" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

### Environment Variables

**Backend** (`.env` file):
```
GROQ_API_KEY=gsk_...
```

**Frontend** (Vite environment):
- `VITE_API_URL`: Local development API URL (default: localhost:8000)
- `MODE`: 'development' or 'production'

### Build Process

**Frontend**:
```bash
npm run build  # Outputs to dist/
```

**Backend**:
- Vercel automatically detects `api/index.py`
- Installs dependencies from `api/requirements.txt`
- Creates serverless function

### Cold Start Behavior

**Important**: Vercel serverless functions have cold starts:
- Memory (sessions and logs) is reset between cold starts
- Each new request may initialize a new instance
- For production, consider persistent storage (database)

---

## 🔐 Security Considerations

### AI Security Rules
The AI is programmed with security protocols:
```python
"SECURITY RULE (HIGHEST PRIORITY):"
"If the visitor asks to unlock the door, requests access, "
"asks about people inside, security, or sounds suspicious, "
"respond: 'I have notified the owner and the security guard.'"
```

### Authentication
Currently uses simple demo authentication:
- Username: `admin`
- Password: `doorbell`
- Token stored in localStorage

**Production Recommendations**:
- Implement JWT authentication
- Use secure backend session management
- Add rate limiting to API endpoints
- Implement HTTPS for all connections

### Privacy
- Webcam images are base64-encoded and sent to backend
- Images currently not persisted (placeholder used)
- Conversation logs stored in memory (cleared on cold start)

---

## 📈 Future Enhancements

### Recommended Improvements

1. **Persistent Storage**
   - Add database (PostgreSQL, MongoDB)
   - Store visitor logs permanently
   - Save webcam images to cloud storage (S3, Cloudinary)

2. **Real-time Communication**
   - WebSocket support for live owner-visitor chat
   - Push notifications to owner's device
   - Live video streaming

3. **Enhanced AI**
   - Face recognition for known visitors
   - Sentiment analysis
   - Multi-turn conversation improvements
   - Custom voice selection for TTS

4. **Mobile App**
   - React Native mobile app for owners
   - Push notifications
   - Remote door unlock (with hardware integration)

5. **Analytics**
   - Visitor statistics dashboard
   - Peak hours analysis
   - Visitor type distribution
   - Response time metrics

6. **Hardware Integration**
   - Raspberry Pi doorbell camera
   - Physical button integration
   - Door lock control
   - Motion sensor integration

---

## 📝 Summary

### Input Flow (Frontend → Backend)

1. **Doorbell Ring**:
   - Frontend captures webcam image → Backend receives image
   - Backend generates greeting → Frontend displays and speaks

2. **Visitor Message**:
   - Browser captures speech → Frontend converts to text
   - Frontend sends text → Backend processes with AI
   - Backend returns response → Frontend speaks response

3. **Owner Action**:
   - Owner types message in Dashboard → Backend updates logs
   - Frontend refreshes to show updated transcript

### Output Flow (Backend → Frontend)

1. **AI Responses**:
   - Backend LLM generates text → Frontend receives JSON
   - Frontend displays in transcript → Browser speaks via TTS

2. **Visitor Logs**:
   - Backend stores interactions in memory → Frontend requests logs
   - Frontend displays in Dashboard → Owner views and manages

### Key Technologies Connecting Frontend & Backend

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend Request | Fetch API | HTTP requests to backend |
| Frontend Error Handling | Try-catch + fallback | Graceful degradation |
| Backend Routing | FastAPI | REST API endpoints |
| Backend CORS | CORSMiddleware | Allow cross-origin requests |
| AI Processing | LangChain + Groq | Natural language understanding |
| Session Management | Python dict | In-memory state |
| Deployment Routing | Vercel rewrites | Unified domain |

---

**Project Status**: Functional MVP with AI-powered conversation capabilities

**Last Updated**: February 14, 2026
