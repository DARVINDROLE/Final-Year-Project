# Decision Agent — Instruction Contract
# ======================================
#
# ROLE:
#   The Decision Agent is the **policy and business-logic layer** of the Smart
#   Doorbell Multi-Agent System. It is the THIRD agent in the pipeline. It receives
#   the Intelligence Agent's risk assessment and maps it to a concrete action
#   using owner preferences, operating mode, and safety policies.
#
# WHY SEPARATE FROM INTELLIGENCE:
#   The Intelligence Agent performs AI reasoning (intent, risk scoring, NLP).
#   The Decision Agent applies BUSINESS RULES — vacation mode, auto-reply
#   preferences, escalation routing. Keeping these separate means you can
#   change owner policies without touching AI logic, and vice versa.
#
# ─────────────────────────────────────────
# SECTION 1 — INPUTS
# ─────────────────────────────────────────
#
# Receives an IntelligenceOutput from the Intelligence Agent:
#   - session_id           : Session identifier
#   - intent               : Classified visitor intent (delivery/help/visitor/unknown)
#   - reply_text           : Generated reply for the visitor
#   - risk_score           : Computed risk (0.0 = safe, 1.0 = dangerous)
#   - escalation_required  : Whether Intelligence flagged mandatory escalation
#   - tags                 : List of classification tags
#   - timestamp            : ISO timestamp
#
# FUTURE: Also receives owner preferences from DB:
#   - auto_reply_enabled   : Whether auto-reply is allowed
#   - vacation_mode        : Whether owner is away
#   - escalation_contacts  : List of people to notify on escalation
#
# ─────────────────────────────────────────
# SECTION 2 — DECISION RULES (evaluated in priority order)
# ─────────────────────────────────────────
#
# Rule 1 — ESCALATE (highest priority)
#   Condition: escalation_required == True OR risk_score >= 0.7
#   Action: final_action = "escalate"
#   Dispatch: { tts: true, notify_owner: true }
#   Reason: "risk >= threshold or escalation flag"
#   Note: This takes precedence over ALL other rules.
#         Weapons, high-risk visitors, and spoofing attempts always escalate.
#
# Rule 2 — AUTO-REPLY (low risk, owner allows it)
#   Condition: risk_score < 0.4
#   Action: final_action = "auto_reply"
#   Dispatch: { tts: true, notify_owner: false }
#   Reason: "risk < threshold"
#   Note: Auto-reply is only permitted when risk is clearly low.
#         The visitor hears the Intelligence Agent's generated reply via TTS.
#         FUTURE: Also check owner auto_reply preference before allowing.
#
# Rule 3 — NOTIFY OWNER (default, medium risk)
#   Condition: 0.4 <= risk_score < 0.7
#   Action: final_action = "notify_owner"
#   Dispatch: { tts: false, notify_owner: true }
#   Reason: "default medium-risk handling"
#   Note: Owner receives a push notification with snapshot and risk info.
#         No auto-reply played to the visitor.
#
# FUTURE RULES (Phase 4+):
#   - Vacation mode override: When vacation_mode=True, escalate if risk >= 0.5
#   - Time-based rules: Late-night visitors (22:00–06:00) lower the auto-reply
#     threshold to 0.3
#   - Repeated visitor: If same face detected 3+ times in 1 hour, escalate
#   - Custom keyword triggers from policy.yaml
#
# ─────────────────────────────────────────
# SECTION 3 — OUTPUT CONTRACT
# ─────────────────────────────────────────
#
# Must return a DecisionOutput matching this exact schema:
#
#   {
#     "session_id": "visitor_a3f7c891",
#     "final_action": "auto_reply",
#     "reason": "risk < threshold",
#     "dispatch": {
#       "tts": true,
#       "notify_owner": false
#     },
#     "timestamp": "2026-02-14T13:00:02+00:00"
#   }
#
# Valid values for final_action:
#   - "escalate"      : Alert owner + security, play security reply
#   - "auto_reply"    : Play TTS reply to visitor, no owner notification
#   - "notify_owner"  : Send notification to owner, no TTS to visitor
#
# This output is consumed by the Action Agent for execution.
#
# ─────────────────────────────────────────
# SECTION 4 — SAFETY & OPERATIONAL RULES
# ─────────────────────────────────────────
#
# 1. For tied matches between rules, ESCALATION ALWAYS WINS.
# 2. Decision Agent is purely rule-based — no ML, no API calls, no latency.
# 3. Decision Agent must never modify or override Intelligence Agent's risk_score.
# 4. Decision Agent is stateless — no memory of previous sessions.
# 5. FUTURE: Load policy file from api/policies/policy.yaml for configurable
#    thresholds and per-device rules.
# 6. Log all decisions to data/logs/decision_agent.log with session_id,
#    final_action, reason, and risk_score for audit trail.
