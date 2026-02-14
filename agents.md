
```markdown
# agents.md
# SAFE RUNTIME AND DEVELOPMENT RULES FOR PROJECT AGENTS
#
# Purpose:
#   These are the conservative runtime and development constraints that the project's
#   agents (Perception, Intelligence, Decision, Action, Orchestrator) must follow at runtime.
#   The file is referenced by agent code and must be loaded at startup.
#
# Placement:
#   Put this file under `api/instructions/agents.md` and require each agent to load and log
#   the contents on startup; the agent must refuse to run if the file is missing.

─────────────────────────────────────────
SECTION 1 — RUNTIME RESOURCE & SAFETY LIMITS
─────────────────────────────────────────

1. Memory & Concurrency:
   - On Raspberry Pi 4 (8 GB), max concurrent "active sessions" default = 2.
   - Each agent must respect a global semaphore provided by the orchestrator:
     `MAX_CONCURRENT_SESSIONS = 2` (configurable only by human).

2. CPU usage:
   - All heavy CPU work (YOLO inference, STT) must be run inside `asyncio.to_thread()` or
     a bounded worker pool (ThreadPoolExecutor with max_workers <= 2).

3. Disk usage:
   - Do not write files outside the repository `data/` directory.
   - `data/` subfolders permitted: `snaps/`, `tts/`, `logs/`, `tmp/`.
   - No writes to system folders like `/tmp` (unless explicitly allowed), `/etc`, `/var`.

4. Network:
   - Allowed external APIs: Groq LLM API only (api host in config).
   - All other external calls require human approval.
   - Timeout for external HTTP calls: 6–10 seconds default.

─────────────────────────────────────────
SECTION 2 — DO NOT DELETE OR MODIFY DATA
─────────────────────────────────────────

1. No agent should delete files under `data/`.
   - Agents may create new files; for updates use `safe_write_file()` from claude.md.
   - If temporary data needed, write to `data/tmp/{session_id}` and remove only that session's tmp files after the session completes using safe removal helper that verifies path prefix. Even then, prefer leaving tmp files and letting human-run maintenance remove old tmp files.

2. SQLite constraints:
   - NEVER run `DROP TABLE` or `DELETE FROM <table>` without a WHERE clause and human approval.
   - Use `CREATE TABLE IF NOT EXISTS` for schema changes.
   - For schema evolution use additive migrations only: `ALTER TABLE ADD COLUMN ...` (no column drops).

3. Backups:
   - Agents must create a DB backup before any schema migration:
     - Copy `data/db.sqlite` → `data/db.sqlite.bak.<timestamp>` using `shutil.copy2`.
     - Do not delete or rotate backups automatically.

─────────────────────────────────────────
SECTION 3 — SAFE INTER-PROCESS / IN-PROC COMMUNICATION
─────────────────────────────────────────

1. Communication pattern:
   - Use orchestrator-managed `asyncio.Queue` and await responses with timeouts.
   - Do not spawn new background daemons or external servers.

2. Timeouts & retries:
   - Every `await` or external call must have a timeout.
   - Retry policy: at most 2 retries with exponential backoff (e.g., 0.5s → 1s) for transient network errors.

3. Failure handling:
   - On unhandled exceptions in an agent, log the error to `data/logs/agent_errors.log` and mark session `status = "error"` with safe error message. Do not crash orchestrator process.

─────────────────────────────────────────
SECTION 4 — SANITIZATION & TTS (SHELL USAGE)
─────────────────────────────────────────

1. Shell and subprocess:
   - If invoking TTS via system utility (e.g., `espeak`, `pico2wave`) MUST use safe subprocess call:
     - Use argument list (no `shell=True`).
     - Sanitize all dynamic inputs: remove newlines, control characters, and dangerous substrings.
     - Example safe call pattern provided below.

2. Example safe TTS helper:

```python
import subprocess, shlex, html

def sanitize_tts_text(text: str) -> str:
    # minimal sanitization: strip control chars and limit length
    safe = "".join(ch for ch in text if ch.isprintable())
    safe = safe.replace('"', "'")
    max_len = 240
    return safe[:max_len]

def play_tts_espeak(text: str, voice: str = "en"):
    safe_text = sanitize_tts_text(text)
    args = ["espeak", "-v", voice, safe_text]
    # Must use subprocess.run with shell=False
    subprocess.run(args, check=False, timeout=10)
````

─────────────────────────────────────────
SECTION 5 — LOGGING, AUDIT, & TELEMETRY
─────────────────────────────────────────

1. Logging:

   * All agents must log to `data/logs/{agent_name}.log`.
   * Do not log secrets, API keys, or full transcripts unless redaction is applied.
   * Log level: default INFO, errors logged with stack traces.

2. Audit trail:

   * For each session write an audit entry to `actions` table with:

     * session_id, agent_name, action, timestamp, short_reason.
   * Do not include raw PII in audit message.

─────────────────────────────────────────
SECTION 6 — CODE GENERATION RULES FOR AGENTS
─────────────────────────────────────────

When agents generate or modify code (e.g., for plugins or dynamic rules):

1. Never auto-execute newly generated code. Generation is allowed, but execution requires:

   * Unit tests provided.
   * Human approval for running it.

2. Generated code must adhere to repository style and include docstrings and tests.

3. Agents must not spawn new modules that import `os.system`, `subprocess.Popen` (except via safe helper with explicit safe wrappers).

─────────────────────────────────────────
SECTION 7 — OPERATIONAL POLICIES (BUSINESS LOGIC)
─────────────────────────────────────────

1. Escalation policy for suspicious events:

   * If `risk_score >= 0.7` or `anti_spoof_score >= 0.6`:

     * Intelligence must set `escalation_required = True`.
     * Decision agent must map escalation to `notify_owner` or `notify_watchman` per policy.yaml.
     * Reply must not include confidential info. Use canned security reply:

       * "I have notified the owner and the security guard."

2. Auto-reply:

   * Allowed only for `risk_score < 0.4` and owner `auto_reply` preference set.
   * Always log that an auto-reply was sent.

─────────────────────────────────────────
SECTION 8 — UPGRADES & MIGRATIONS
─────────────────────────────────────────

1. No agent should perform migrations automatically in production.

   * Generate migration SQL as a file in `migrations/` and require human to run and backup DB first.

2. Versioning:

   * Maintain `api/MIGRATION_README.md` with migration steps, required backups, and explicit human approval steps.

─────────────────────────────────────────
SECTION 9 — WHEN SOMETHING GOES WRONG
─────────────────────────────────────────

1. If the agent encounters any action that would modify or delete data, it must:

   * Abort the operation.
   * Write a short incident report to `data/logs/incidents.log` with timestamp and context.
   * Notify the orchestrator (which must surface an admin alert via the UI).

2. If SQLite is locked or corrupted, do NOT attempt repair; notify human with safe message and create a read-only copy of the DB file for analysis.

─────────────────────────────────────────
SECTION 10 — HUMAN-IN-THE-LOOP & APPROVAL
─────────────────────────────────────────

1. Implement a simple human approval flow:

   * For actions flagged `requires_human = True`, write pending item to `actions` table and do not execute.
   * Provide admin UI / endpoint for humans to approve one-off actions.

─────────────────────────────────────────
END OF AGENTS SAFETY RULES
─────────────────────────────────────────

```