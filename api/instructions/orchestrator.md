# Orchestrator — Instruction Contract
# ====================================
#
# ROLE:
#   The Orchestrator is the **central coordinator** of the Smart Doorbell
#   Multi-Agent System. It is NOT an AI agent — it is a deterministic control
#   plane that manages the session lifecycle, routes data between agents,
#   enforces concurrency limits, and persists state to SQLite.
#
# ARCHITECTURE POSITION:
#
#   ┌────────────────────┐
#   │    Orchestrator     │  ← You are here
#   └──────┬─────────────┘
#          │
#    ┌─────┼──────────────┐
#    │     │              │
#  Perception   Intelligence   Decision
#    Agent        Agent         Agent
#                  │              │
#                  └──────┬───────┘
#                         │
#                   Action Agent
#
# ─────────────────────────────────────────
# SECTION 1 — SESSION LIFECYCLE
# ─────────────────────────────────────────
#
# A session is created when the /api/ring endpoint receives a doorbell event.
# The Orchestrator manages its progression through these states:
#
#   "queued"           → Ring received, session created, waiting for processing
#   "processing"       → Agent pipeline is actively running
#   "perception_done"  → Perception Agent completed, Intelligence next
#   "completed"        → All agents finished, session result available
#   "error"            → Pipeline failed, error logged
#
# Flow:
#   1. /api/ring POST → Orchestrator.handle_ring()
#      - Generate session_id (or use provided one)
#      - Save image/audio from base64 to data/snaps/ and data/tmp/
#      - Create session row in SQLite with status="queued"
#      - Enqueue RingEvent to session's asyncio.Queue
#      - Spawn async task to process the session
#      - Return immediately: { sessionId, status: "queued" }
#
#   2. handle_session(session_id) — runs asynchronously
#      - Acquire global semaphore (max 2 concurrent sessions)
#      - Update status → "processing"
#      - Run Perception Agent → PerceptionOutput
#      - Update status → "perception_done"
#      - Run Intelligence Agent → IntelligenceOutput
#      - Run Decision Agent → DecisionOutput
#      - Build ActionRequest from Decision + Intelligence outputs
#      - Run Action Agent → ActionResult
#      - Update status → "completed" with final risk_score
#      - Log all steps to `actions` table for audit trail
#
#   3. On any pipeline failure:
#      - Set status → "error"
#      - Log full traceback to data/logs/agent_errors.log
#      - Record error in `actions` table
#      - Release semaphore so other sessions can proceed
#
# ─────────────────────────────────────────
# SECTION 2 — CONCURRENCY & RESOURCE LIMITS
# ─────────────────────────────────────────
#
# 1. MAX_CONCURRENT_SESSIONS = 2 (enforced via asyncio.Semaphore)
#    - Designed for Raspberry Pi 4 (8GB) resource constraints
#    - Configurable only by human, not by agents
#
# 2. Each agent call runs in asyncio.to_thread() for CPU-bound work
#    - Prevents blocking the event loop
#    - Worker pool bounded to 2 threads max
#
# 3. Per-session queue (asyncio.Queue, maxsize=4)
#    - Prevents unbounded memory growth from rapid ring events
#    - If queue is full, new events are rejected
#
# 4. Session tasks are tracked in session_tasks dict
#    - If a session task already exists and is running, new ring events
#      are queued to the existing session rather than spawning duplicates
#
# ─────────────────────────────────────────
# SECTION 3 — DATA PERSISTENCE
# ─────────────────────────────────────────
#
# SQLite database at data/db.sqlite with two core tables:
#
# sessions:
#   - session_id (TEXT PRIMARY KEY)
#   - created_at (TEXT, ISO timestamp)
#   - status (TEXT: queued/processing/perception_done/completed/error)
#   - device_id (TEXT)
#   - risk_score (REAL, set on completion)
#   - last_updated (TEXT, ISO timestamp, updated on every status change)
#
# actions:
#   - id (INTEGER PRIMARY KEY AUTOINCREMENT)
#   - session_id (TEXT, FK to sessions)
#   - action_type (TEXT: ring_received/auto_reply/notify_owner/escalate/error)
#   - payload (TEXT, JSON blob)
#   - status (TEXT)
#   - timestamp (TEXT, ISO timestamp)
#   - short_reason (TEXT, human-readable audit note)
#   - agent_name (TEXT: orchestrator/perception/intelligence/decision/action)
#
# Rules:
#   - Use CREATE TABLE IF NOT EXISTS (never DROP TABLE)
#   - Use parameterized queries (never string interpolation)
#   - Use transactions with rollback on exception
#   - Datetime objects must be serialized via custom JSON encoder
#   - Backup DB before any schema migration
#
# ─────────────────────────────────────────
# SECTION 4 — API ENDPOINTS
# ─────────────────────────────────────────
#
# POST /api/ring
#   - Body: RingEvent JSON
#   - Returns: { sessionId, status, imagePath, audioPath }
#   - Triggers async session pipeline
#
# GET /api/session/{session_id}/status
#   - Returns: { sessionId, status, lastUpdated, riskScore }
#   - Used by frontend to poll session progress
#
# GET /api/health
#   - Returns: { status: "ok" }
#   - Basic health check for monitoring
#
# GET /api/logs
#   - Returns: Recent session logs and actions for dashboard
#
# POST /api/ai-reply
#   - Body: AiReplyRequest (FUTURE: manual owner reply via LLM)
#
# ─────────────────────────────────────────
# SECTION 5 — AGENT COMMUNICATION RULES
# ─────────────────────────────────────────
#
# 1. Agents are STATELESS modules. They do not call each other directly.
# 2. The Orchestrator passes data between agents in a strict linear pipeline:
#    RingEvent → Perception → Intelligence → Decision → Action
# 3. No agent spawns background daemons or external servers.
# 4. All inter-agent data flows through Pydantic models for type safety.
# 5. Every agent output is persisted before the next agent is invoked.
#
# ─────────────────────────────────────────
# SECTION 6 — FAILURE HANDLING
# ─────────────────────────────────────────
#
# 1. On unhandled exception in any agent:
#    - Catch at handle_session level
#    - Log full traceback to data/logs/agent_errors.log
#    - Set session status = "error"
#    - Record error action in `actions` table
#    - Do NOT crash the orchestrator process
#
# 2. On SQLite lock/corruption:
#    - Do NOT attempt repair
#    - Log error and notify via admin alert
#    - Create read-only copy for analysis
#
# 3. On external API timeout (Groq, etc.):
#    - Retry at most 2 times with exponential backoff (0.5s → 1s)
#    - On final failure, use canned fallback and continue pipeline
