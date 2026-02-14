
This is very good already.
But Indian household door interactions are **much more chaotic and socially nuanced** than basic delivery / suspicious / speak-to-owner flows.

Below is a **structured list of realistic Indian edge cases** across:

* Delivery
* Domestic staff
* Religious / community
* Utilities
* Government
* Neighbors
* Sales
* Emergencies
* Cultural nuances
* Multi-language
* Social manipulation attempts
* Emotional pressure
* Scam patterns
* Festival scenarios
* Night-time interactions
* Children / elderly
* Social engineering

These will help you harden your system prompt logic and decision model.

---

# 🏠 CATEGORY 1: Delivery Edge Cases (India-Specific)

### 1️⃣ Cash-on-Delivery (COD) but exact change required

Visitor:
“Sir, 1299 rupees COD hai, change milega kya?”

Edge case:
They pressure you to confirm availability of cash.

⚠️ Risk: Indirectly probing financial info.

---

### 2️⃣ Delivery for Neighbor

“Flat 402 ka parcel galti se yahan aa gaya.”

Edge case:
They may request you to accept it.

⚠️ Risk: Social engineering.

---

### 3️⃣ Delivery Requiring OTP

“Sir OTP bata dijiye, delivery complete karna hai.”

⚠️ Extremely common scam vector.

System must **never share OTP logic**.

---

### 4️⃣ Late Night Delivery

11:30 PM delivery claim.

⚠️ Risk escalates at unusual hours.

---

### 5️⃣ Fake Courier Without Uniform

Objects: no package, no courier bag.

Transcript: “Amazon delivery.”

⚠️ Risk mismatch between objects and claim.

---

### 6️⃣ Delivery Asking to Enter Building

“Lift use karna hai, andar aana padega.”

Rule violation risk.

---

# 👵 CATEGORY 2: Domestic Staff / Service Personnel

### 7️⃣ Maid Arrived Early

“Aaj thoda jaldi aa gayi hoon.”

Harmless but timing anomaly.

---

### 8️⃣ New Maid Claiming Replacement

“Main aaj se kaam karungi, purani bai nahi aayegi.”

⚠️ Risk: unknown person claiming staff change.

---

### 9️⃣ Cook Asking for Advance

“Owner ne bola paise le lo.”

⚠️ Social manipulation.

---

### 🔟 Driver Asking for Keys

“Car ki chaabi de do.”

Direct access request.

---

# 🛕 CATEGORY 3: Religious / Cultural

### 1️⃣ Temple Donation Collection

“Mandir ke liye chanda hai.”

Common in India.

⚠️ Could be legitimate or scam.

---

### 2️⃣ Festival Donation (Ganpati, Durga Puja)

“Society ka collection hai.”

---

### 3️⃣ Priest Visit (Pandit ji)

“Ghar pe havan hai kya?”

---

### 4️⃣ Beggar / Alms Request

“Bhagwan ke naam pe kuch de do.”

Emotionally manipulative.

---

# 🏢 CATEGORY 4: Government / Utilities

### 5️⃣ Electricity Board Claim

“Bijli check karne aaye hain.”

---

### 6️⃣ Gas Cylinder Verification

“Gas leak check karna hai.”

⚠️ Entry request risk.

---

### 7️⃣ Water Board Fine Notice

“Meter reading lena hai.”

---

### 8️⃣ Aadhaar / KYC Update

“KYC verification hai.”

⚠️ Very common scam.

---

# 👨‍💼 CATEGORY 5: Sales / Aggressive Marketing

### 9️⃣ Water Purifier Sales

“Free demo hai.”

---

### 🔟 Real Estate Agent

“Flat sell karna hai kya?”

---

### 11️⃣ Insurance Agent

“Policy discuss karni hai.”

---

### 12️⃣ Broadband Upgrade

“Fiber install karna hai.”

---

# 🚨 CATEGORY 6: Emergencies

### 13️⃣ Someone Claiming Accident

“Unke relative hospital mein hai.”

⚠️ Emotional manipulation.

---

### 14️⃣ Police at Door

“Police se aaye hain.”

Must respond carefully without revealing info.

---

### 15️⃣ Fire Emergency Nearby

“Aag lag gayi hai.”

Should trigger emergency logic.

---

### 16️⃣ Child at Door Crying

“Uncle ghar pe nahi hain.”

High empathy + safety.

---

# 🧠 CATEGORY 7: Social Engineering Attempts

### 17️⃣ “Owner told me to collect money”

Common scam.

---

### 18️⃣ “I’m from bank, account verification”

Scam.

---

### 19️⃣ “I know the owner personally”

Trying to bypass system.

---

### 20️⃣ Asking if Anyone Is Home

“Koi ghar pe hai?”

⚠️ Major security probe.

System must never reveal occupancy.

---

# 😠 CATEGORY 8: Aggression / Threat

### 21️⃣ Verbal Abuse

“Darwaza kholo warna dekh lena.”

Must immediately escalate.

---

### 22️⃣ Repeated Ringing

Possible harassment.

---

### 23️⃣ Drunk Person

Slurred speech + aggressive tone.

---

# 👶 CATEGORY 9: Children / Elderly

### 24️⃣ Lost Child

“Mummy kho gayi.”

Emergency handling.

---

### 25️⃣ Elderly Asking for Help

“Paani milega?”

Empathy + safe boundary.

---

# 🌙 CATEGORY 10: Night-Time Scenarios

### 26️⃣ Midnight Bell Ring

Suspicious by default.

---

### 27️⃣ Power Cut Situation

Visitor says electricity gone.

---

# 📦 CATEGORY 11: Package Issues

### 28️⃣ Wrong Address Complaint

“Ye galat jagah hai.”

---

### 29️⃣ Damaged Package

“Sign karna padega.”

Signature request risk.

---

### 30️⃣ Payment Already Done Claim

“Online paid hai.”

Must defer to owner.

---

# 💬 CATEGORY 12: Language Switching

### 31️⃣ Hinglish Mix

“Bhaiya delivery hai, gate kholo.”

---

### 32️⃣ Pure Hindi

“Kripya darwaza kholiye.”

---

### 33️⃣ Tamil / Bengali / Marathi

System should gracefully default if unsupported.

---

# 🔄 CATEGORY 13: Multi-Person Interaction

### 34️⃣ Two People at Door, Only One Speaking

Risk assessment complexity.

---

### 35️⃣ Group of Young Men Claiming Delivery

Higher suspicion.

---

# 🎭 CATEGORY 14: Deception Through Emotion

### 36️⃣ Crying + Urgent Tone

“Bahut zaroori hai.”

---

### 37️⃣ Pretending to Be Relative

“Main chacha hoon.”

---

# 🧾 CATEGORY 15: Financial Manipulation

### 38️⃣ Asking to Transfer UPI

“QR scan kar dijiye.”

---

### 39️⃣ Asking for Bank Details

“Refund ke liye account number.”

---

### 40️⃣ Fake Refund Delivery

“Refund dena hai.”

---

# ⚖️ CATEGORY 16: Legal/Authority Edge

### 41️⃣ Court Notice

“Legal notice hai.”

---

### 42️⃣ Tax Officer

“Inspection hai.”

---

# 🧍 CATEGORY 17: Silent Visitor

### 43️⃣ No Speech, Just Standing

Emotion neutral, low transcript.

Decision must rely on vision.

---

# 📹 CATEGORY 18: Camera Blocking

### 44️⃣ Face Not Visible

High spoof risk.

---

# 🔊 CATEGORY 19: Background Noise

### 45️⃣ Loud crowd noise

May indicate group.

---

# 🏗 CATEGORY 20: Construction Workers

### 46️⃣ Claiming maintenance work.

---

# 💥 CATEGORY 21: Combined Edge Cases

Example:

* 10:30 PM
* No uniform
* Claims delivery
* Asking for OTP
* Emotion nervous
* Risk high

System must escalate instantly.

---

# 🧩 Suggested Improvements to Your RULES

You may consider adding:

### Additional Security Rule:

> If the visitor asks whether anyone is home, respond:
> "Please wait while I notify the owner."

### OTP Rule:

> Never share any OTP or verification code.

### Occupancy Rule:

> Never confirm if the owner is home.

### Identity Claim Rule:

> Do not trust claims of personal relationship.

### Multi-visit Escalation:

> If repeated visits occur within short interval, escalate.

---

# 🔥 If You Want Advanced Hardening

I can:

* Convert all above into structured training examples (JSON format)
* Generate a risk-weight matrix for Indian context
* Expand your system prompt to 2.0 hardened version
* Create a decision-tree for Intelligence Agent
* Provide adversarial test prompts to test your Groq LLM

Tell me what level you want:
1️⃣ Basic hardened
2️⃣ Production hardened
3️⃣ Research-grade security hardened


Excellent — this is how you move from MVP → hardened intelligent system.

Below you’ll get:

1. ✅ **Structured Training Examples (JSON format)**
2. ✅ **Risk-Weight Matrix (Indian Context Optimized)**
3. ✅ **Decision Tree for Intelligence Agent (MD file)**

This is production-grade Indian household hardening.

---

# ✅ PART 1 — STRUCTURED TRAINING EXAMPLES (JSON)

Format:

```json
{
  "id": "unique_case_id",
  "category": "...",
  "time_context": "...",
  "detected_objects": [...],
  "transcript": "...",
  "emotion": "...",
  "risk_factors": [...],
  "expected_intent": "...",
  "expected_action": "...",
  "risk_level": 0.0-1.0
}
```

---

## 📦 DELIVERY CASES

```json
[
  {
    "id": "delivery_cod_change",
    "category": "delivery",
    "time_context": "day",
    "detected_objects": ["person", "package"],
    "transcript": "1299 rupees COD hai, change milega kya?",
    "emotion": "neutral",
    "risk_factors": ["cash_request"],
    "expected_intent": "delivery_cod",
    "expected_action": "notify_owner",
    "risk_level": 0.45
  },
  {
    "id": "delivery_otp_request",
    "category": "delivery",
    "time_context": "day",
    "detected_objects": ["person", "package"],
    "transcript": "Sir OTP bata dijiye delivery complete karna hai",
    "emotion": "neutral",
    "risk_factors": ["otp_request", "scam_pattern"],
    "expected_intent": "delivery_verification",
    "expected_action": "escalate",
    "risk_level": 0.85
  },
  {
    "id": "fake_delivery_no_package",
    "category": "delivery",
    "time_context": "night",
    "detected_objects": ["person"],
    "transcript": "Amazon delivery hai",
    "emotion": "nervous",
    "risk_factors": ["no_package_detected", "time_anomaly"],
    "expected_intent": "suspicious_delivery",
    "expected_action": "escalate",
    "risk_level": 0.92
  }
]
```

---

## 👵 DOMESTIC STAFF CASES

```json
[
  {
    "id": "new_maid_unknown",
    "category": "domestic_staff",
    "time_context": "morning",
    "detected_objects": ["person"],
    "transcript": "Main aaj se kaam karungi, purani bai nahi aayegi",
    "emotion": "neutral",
    "risk_factors": ["identity_change"],
    "expected_intent": "staff_claim",
    "expected_action": "notify_owner",
    "risk_level": 0.60
  }
]
```

---

## 🛕 RELIGIOUS / DONATION

```json
[
  {
    "id": "temple_donation",
    "category": "religious",
    "time_context": "day",
    "detected_objects": ["person"],
    "transcript": "Mandir ke liye chanda hai",
    "emotion": "calm",
    "risk_factors": [],
    "expected_intent": "donation_request",
    "expected_action": "notify_owner",
    "risk_level": 0.35
  }
]
```

---

## 🏢 GOVERNMENT / SCAM

```json
[
  {
    "id": "kyc_scam",
    "category": "government_claim",
    "time_context": "day",
    "detected_objects": ["person"],
    "transcript": "Aadhaar KYC verification hai",
    "emotion": "neutral",
    "risk_factors": ["financial_probe"],
    "expected_intent": "identity_verification_claim",
    "expected_action": "notify_owner",
    "risk_level": 0.70
  }
]
```

---

## 🚨 AGGRESSION

```json
[
  {
    "id": "verbal_threat",
    "category": "aggression",
    "time_context": "night",
    "detected_objects": ["person"],
    "transcript": "Darwaza kholo warna dekh lena",
    "emotion": "angry",
    "risk_factors": ["threat", "aggression"],
    "expected_intent": "forced_entry_attempt",
    "expected_action": "escalate",
    "risk_level": 0.98
  }
]
```

---

## 👶 EMERGENCY CHILD

```json
[
  {
    "id": "lost_child",
    "category": "emergency",
    "time_context": "evening",
    "detected_objects": ["child"],
    "transcript": "Mummy kho gayi",
    "emotion": "distressed",
    "risk_factors": ["child_distress"],
    "expected_intent": "child_emergency",
    "expected_action": "notify_owner",
    "risk_level": 0.75
  }
]
```

---

You can scale this JSON to 100+ scenarios.

---

# ✅ PART 2 — RISK-WEIGHT MATRIX (INDIAN CONTEXT)

Indian urban risk signals differ from Western households.

Here is a structured scoring model:

---

## 🎯 Base Risk Formula

[
R = w_1(Vision) + w_2(SpeechPattern) + w_3(Time) + w_4(Behavior) + w_5(ContextMismatch)
]

---

## 📊 WEIGHT MATRIX

| Factor                  | Condition         | Weight |
| ----------------------- | ----------------- | ------ |
| No person detected      | claiming delivery | +0.35  |
| Asking for OTP          | always            | +0.50  |
| Asking if owner home    | +0.40             |        |
| Requesting entry        | +0.55             |        |
| Aggressive tone         | +0.45             |        |
| Night visit (10pm–5am)  | +0.30             |        |
| Multiple persons        | +0.25             |        |
| Face hidden             | +0.40             |        |
| Emotion: nervous        | +0.15             |        |
| Emotion: angry          | +0.35             |        |
| Identity change claim   | +0.25             |        |
| Known delivery keywords | −0.20             |        |
| Known staff face match  | −0.35             |        |

---

## 🚨 Risk Level Interpretation

| Risk Score | Action                    |
| ---------- | ------------------------- |
| 0.0–0.39   | Auto-reply allowed        |
| 0.40–0.69  | Notify owner              |
| 0.70–0.84  | High alert, no auto-reply |
| 0.85–1.0   | Escalate immediately      |

---

# ✅ PART 3 — DECISION TREE (INTELLIGENCE AGENT)

Below is your `intelligence_decision_tree.md`.

---

```markdown
# Intelligence Agent Decision Tree
Smart Doorbell — Indian Household Context

INPUT:
- detected_objects
- transcript
- emotion
- risk_assessment_level

-------------------------------------

STEP 1: Check Emergency Signals
-------------------------------------

IF transcript contains:
    - "help"
    - "fire"
    - "accident"
    - "bachao"
    - "emergency"
THEN:
    intent = emergency
    action = notify_owner
    STOP

-------------------------------------

STEP 2: Check Aggression / Threat
-------------------------------------

IF emotion == angry OR transcript contains threat keywords:
    intent = forced_entry_attempt
    action = escalate
    STOP

-------------------------------------

STEP 3: Check OTP / Financial Probes
-------------------------------------

IF transcript contains:
    - "OTP"
    - "verification code"
    - "UPI"
    - "account number"
THEN:
    intent = scam_attempt
    action = escalate
    STOP

-------------------------------------

STEP 4: Delivery Logic
-------------------------------------

IF detected_objects includes "package":

    IF transcript contains COD/payment:
        action = notify_owner
    ELSE:
        action = auto_reply (if risk < threshold)

-------------------------------------

STEP 5: Identity Claim Check
-------------------------------------

IF transcript contains:
    - "owner ne bola"
    - "relative hoon"
    - "andar aana hai"
THEN:
    action = notify_owner

-------------------------------------

STEP 6: Time-Based Risk Adjustment
-------------------------------------

IF current_time between 22:00 and 05:00:
    risk_score += 0.30

-------------------------------------

STEP 7: Final Risk Evaluation
-------------------------------------

IF risk_score >= 0.85:
    action = escalate
ELSE IF risk_score >= 0.40:
    action = notify_owner
ELSE:
    action = auto_reply

-------------------------------------

OUTPUT:
- intent
- reply_text
- risk_score
- escalation_required
```

---

# 🧠 What This Gives You

You now have:

* Structured dataset for fine-tuning
* Indian-specific risk weighting
* Deterministic decision fallback
* LLM-assisted reasoning layer
* Security escalation logic

---

If you want next level:

I can generate:

* 📊 A confusion matrix testing framework
* 🧪 Adversarial attack test cases
* 🔐 India-specific scam pattern library
* 🧠 Hybrid rule + LLM ensemble design
* 📈 Risk simulation code for SQLite

Tell me the level:
1️⃣ Production
2️⃣ Research
3️⃣ Paranoid Mumbai apartment level
4️⃣ Full smart-city grade system

You’re building something very serious now.
