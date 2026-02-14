# Action Agent — Instruction Contract
# ====================================
#
# ROLE:
#   The Action Agent is the **execution layer** of the Smart Doorbell Multi-Agent
#   System. It is the FOURTH and FINAL agent in the pipeline. It receives the
#   Decision Agent's action directive and EXECUTES it — playing TTS, sending
#   notifications, logging events, and storing snapshots.
#
# WHAT IT COMBINES (consolidated from separate executors):
#   - TTS playback / file generation (espeak / pico2wave)
#   - Mobile push notification dispatch
#   - Watchman/security alert routing
#   - Snapshot and transcript logging to database
#   - Call initiation (future)
#
# WHY COMBINED:
#   All of these are side-effect-producing actions that follow the same decision.
#   Keeping them in one agent ensures atomic execution — either the full action
#   set completes, or the failure is consistently logged.
#
# ─────────────────────────────────────────
# SECTION 1 — INPUTS
# ─────────────────────────────────────────
#
# The Action Agent receives ALL upstream outputs for maximum context:
#
#   - DecisionOutput      : final_action, reason, dispatch map
#   - IntelligenceOutput  : reply_text, risk_score, intent, escalation flag
#   - PerceptionOutput    : image_path, transcript, weapon_detected, objects
#   - ActionRequest       : session_id, tts_text (sanitized reply to speak)
#
# ─────────────────────────────────────────
# SECTION 2 — ACTION HANDLERS
# ─────────────────────────────────────────
#
# Handler 1 — AUTO-REPLY (final_action == "auto_reply")
#   Triggered when: Decision Agent determines risk is low enough for auto-response
#   Steps:
#     1. Sanitize tts_text (strip control chars, limit to 240 chars, escape quotes)
#     2. Write TTS preview text to data/tts/{session_id}.txt
#     3. FUTURE: Invoke local TTS engine (espeak/pico2wave) via safe subprocess:
#        - Use argument list (NO shell=True)
#        - Timeout: 10 seconds
#        - Output to data/tts/{session_id}.wav
#     4. Return ActionResult with status="played", payload={tts_file: path}
#
# Handler 2 — NOTIFY OWNER (final_action == "notify_owner")
#   Triggered when: Medium risk, owner should decide
#   Steps:
#     1. Build notification payload:
#        - message: Intelligence Agent's reply_text
#        - risk_score: for owner's awareness
#        - image_path: snapshot for visual context
#     2. Insert action row into DB `actions` table for frontend to poll
#     3. FUTURE: Send push notification via mobile notification service
#     4. Return ActionResult with status="queued", action_type="notify_owner"
#
# Handler 3 — ESCALATE (final_action == "escalate")
#   Triggered when: High risk, weapon detected, or mandatory escalation
#   Steps:
#     1. Build escalation payload (same as notify_owner but marked urgent):
#        - message: Canned security reply text
#        - risk_score: the elevated score
#        - image_path: snapshot as evidence
#     2. Insert URGENT action row into DB `actions` table
#     3. FUTURE: Also alert security guard / watchman contact
#     4. FUTURE: Play security reply TTS to visitor
#     5. Return ActionResult with status="queued", action_type="escalate"
#
# Handler 4 — FALLBACK (unknown final_action)
#   If the action type is not recognized:
#     - Return ActionResult with status="ignored", empty payload
#     - Log a warning — this should never happen in normal operation
#
# ─────────────────────────────────────────
# SECTION 3 — OUTPUT CONTRACT
# ─────────────────────────────────────────
#
# Must return an ActionResult matching this exact schema:
#
#   {
#     "session_id": "visitor_a3f7c891",
#     "status": "played",
#     "action_type": "auto_reply",
#     "payload": {
#       "tts_file": "data/tts/visitor_a3f7c891.txt"
#     },
#     "timestamp": "2026-02-14T13:00:03+00:00"
#   }
#
# Valid status values:
#   - "played"   : TTS was generated/played successfully
#   - "queued"   : Notification queued for owner/security
#   - "ignored"  : Action type not recognized, no-op
#
# This output is the final result logged by the Orchestrator to close the session.
#
# ─────────────────────────────────────────
# SECTION 4 — TTS SAFETY (CRITICAL)
# ─────────────────────────────────────────
#
# TTS text sanitization is MANDATORY before any subprocess invocation:
#
# 1. Strip all non-printable / control characters
# 2. Replace double quotes with single quotes
# 3. Limit text to 240 characters maximum
# 4. NEVER use shell=True for subprocess calls
# 5. ALWAYS use argument list: ["espeak", "-v", "en", sanitized_text]
# 6. Set subprocess timeout to 10 seconds
# 7. Never pass user-controlled data directly to shell
#
# Safe pattern (must follow exactly):
#   args = ["espeak", "-v", voice, sanitized_text]
#   subprocess.run(args, check=False, timeout=10, shell=False)
#
# ─────────────────────────────────────────
# SECTION 5 — SAFETY & OPERATIONAL RULES
# ─────────────────────────────────────────
#
# 1. All file writes go ONLY to data/tts/ or data/snaps/. No other directories.
# 2. Every action MUST be logged to the `actions` table in SQLite with:
#    session_id, action_type, payload, status, timestamp, short_reason, agent_name
# 3. Never delete files or database rows.
# 4. Action Agent does NOT make risk decisions — it only EXECUTES what the
#    Decision Agent has already determined.
# 5. If execution of any action fails, log the error and return a failed
#    ActionResult. Do not retry autonomously.
# 6. Log errors to data/logs/action_agent.log.
