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

SECTION 1 — RUNTIME RESOURCE & SAFETY LIMITS
--------------------------------------------
1. Memory & Concurrency:
   - Max concurrent active sessions default = 2.
2. CPU usage:
   - Heavy CPU work must run in asyncio.to_thread() or bounded worker pool.
3. Disk usage:
   - Write files only under repository data/ directory and approved subfolders.
4. Network:
   - Allowed external API: Groq LLM API.
   - External HTTP default timeout 6–10 seconds.

SECTION 2 — DO NOT DELETE OR MODIFY DATA
-----------------------------------------
1. Do not delete files under data/.
2. SQLite constraints:
   - Never run DROP TABLE.
   - Never run DELETE without WHERE and human approval.
3. Backups:
   - Backup data/db.sqlite before schema migrations.

SECTION 3 — SAFE COMMUNICATION
------------------------------
1. Use orchestrator-managed asyncio.Queue communication.
2. Apply timeout and max 2 retries with exponential backoff for transient network errors.
3. On unhandled exceptions, log to data/logs/agent_errors.log and mark session status error.

SECTION 4 — SANITIZATION & TTS
------------------------------
1. If invoking local TTS subprocess:
   - use argument list,
   - shell=False,
   - sanitize dynamic text.

SECTION 5 — LOGGING & AUDIT
---------------------------
1. Agent logs go to data/logs/{agent_name}.log.
2. Do not log secrets, API keys, or raw PII.
3. Write action audit entries with session_id, agent_name, action, timestamp, short_reason.

SECTION 6 — BUSINESS LOGIC POLICY
---------------------------------
1. If risk_score >= 0.7 or anti_spoof_score >= 0.6:
   - escalation_required = True
   - decision must map to notify_owner or notify_watchman policy action.
2. Security escalation reply: "I have notified the owner and the security guard."

SECTION 7 — HUMAN APPROVAL
--------------------------
1. For requires_human=True actions, write pending action in actions table and do not execute.

END OF AGENTS SAFETY RULES
