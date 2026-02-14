# Intelligence Agent — Instruction Contract
# ==========================================
#
# ROLE:
#   The Intelligence Agent is the **reasoning and risk assessment layer** of the
#   Smart Doorbell Multi-Agent System. It is the SECOND agent in the pipeline,
#   receiving structured perception data and producing intent classification,
#   risk scoring, response generation, and escalation decisions.
#
# WHAT IT COMBINES (consolidated from separate agents):
#   - Natural Language Processing / intent classification
#   - Suspicion and risk scoring model
#   - Behavioral anomaly detection
#   - Conversational reply generation (LLM-powered via Groq API)
#
# WHY COMBINED:
#   Suspicion is inherently contextual — words, emotion, and vision cues ALL
#   contribute to risk. If separated, the outputs would need to be recombined
#   anyway. Keeping reasoning and security assessment together avoids redundant
#   data passing and ensures holistic evaluation.
#
# ─────────────────────────────────────────
# SECTION 1 — INPUTS
# ─────────────────────────────────────────
#
# Receives a PerceptionOutput from the Perception Agent containing:
#   - session_id         : Session identifier
#   - person_detected    : Whether a person was seen (bool)
#   - objects            : List of detected objects [{label, conf}]
#   - vision_confidence  : Confidence of person detection (0.0–1.0)
#   - transcript         : STT transcript of visitor speech
#   - stt_confidence     : Confidence of STT transcription (0.0–1.0)
#   - emotion            : Detected emotion ("neutral", "aggressive", "distressed")
#   - anti_spoof_score   : Spoofing likelihood (0.0–1.0)
#   - weapon_detected    : Whether a weapon was detected (bool)
#   - weapon_confidence  : Confidence of weapon detection (0.0–1.0)
#   - weapon_labels      : List of weapon class names detected
#   - image_path         : Path to snapshot image
#   - timestamp          : ISO timestamp of perception
#
# ─────────────────────────────────────────
# SECTION 2 — PROCESSING PIPELINE
# ─────────────────────────────────────────
#
# Step 1 — Intent Classification (Rule-Based, Fast)
#   - Classify visitor intent from transcript keywords:
#     * "delivery" : package, delivery, courier, amazon, parcel, ups, fedex
#     * "help"     : help, emergency, urgent, accident
#     * "visitor"  : owner, speak, talk, friend, family, appointment
#     * "unknown"  : default if no keywords match
#   - This runs locally with zero latency (no API call needed).
#
# Step 2 — Risk Score Computation
#   - Composite weighted formula:
#     risk_score = 0.5 × (1 − vision_confidence)
#                + 0.3 × anti_spoof_score
#                + 0.2 × emotion_score
#
#   - Where emotion_score:
#     * "aggressive" = 0.6
#     * "distressed" = 0.4
#     * "neutral"    = 0.2
#
#   - WEAPON OVERRIDE: If weapon_detected == True, force risk_score >= 0.75
#     regardless of other factors. Weapons always escalate.
#
#   - Final risk_score is clamped to range [0.0, 1.0], rounded to 3 decimals.
#
# Step 3 — Escalation Decision
#   - Set escalation_required = True if:
#     * risk_score >= 0.7, OR
#     * weapon_detected == True, OR
#     * Transcript contains dangerous keywords: "unlock", "let me in", "open the door"
#   - When escalated, use CANNED SECURITY REPLY (never reveal internal logic):
#     "I have notified the owner and the security guard."
#
# Step 4 — Reply Generation
#   - For non-escalated sessions:
#     * "delivery" intent → "Please leave the package at the doorstep."
#     * "help" intent → "I'm alerting the owner right away."
#     * "visitor" intent → "Please wait while I notify the owner."
#     * "unknown" intent → "Please wait while I notify the owner."
#   - For uncertain intents or conversation mode, calls Groq LLM API with:
#     * System prompt from api/prompts/groq_system_prompt.txt
#     * Context: detected objects + transcript + emotion + risk level
#     * Parameters: max_tokens=128, temperature=0.2, model from GROQ_MODEL env
#     * Timeout: 8 seconds, 2 retries with exponential backoff
#     * On API failure: fall back to canned reply
#   - Requires GROQ_API_KEY environment variable set.
#   - If GROQ_API_KEY is not set, falls back to fully rule-based mode.
#
# ─────────────────────────────────────────
# SECTION 3 — OUTPUT CONTRACT
# ─────────────────────────────────────────
#
# Must return an IntelligenceOutput matching this exact schema:
#
#   {
#     "session_id": "visitor_a3f7c891",
#     "intent": "delivery",
#     "reply_text": "Please leave the package at the doorstep.",
#     "risk_score": 0.32,
#     "escalation_required": false,
#     "tags": ["delivery"],
#     "timestamp": "2026-02-14T13:00:01+00:00"
#   }
#
# This output is consumed directly by the Decision Agent.
#
# ─────────────────────────────────────────
# SECTION 4 — SAFETY & OPERATIONAL RULES
# ─────────────────────────────────────────
#
# 1. NEVER reveal internal risk scores, model logic, or system details in
#    reply_text. Replies must be conversational and safe for any visitor.
# 2. NEVER include confidential information in escalation replies.
# 3. When calling Groq API:
#    - Sanitize all data inserted into prompts (strip binary, limit length)
#    - Use request timeout of 6–10 seconds
#    - Retry at most 2 times with exponential backoff
#    - Log only metadata (intent, risk_score), never raw API keys
# 4. If any step fails unexpectedly, default to escalation (fail-safe).
# 5. All processing is stateless — no session memory beyond current input.
# 6. Log errors to data/logs/intelligence_agent.log.
