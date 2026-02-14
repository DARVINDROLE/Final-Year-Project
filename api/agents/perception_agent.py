from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import wave
from datetime import datetime, timezone
from pathlib import Path

from ..models import ObjectDetection, PerceptionOutput, RingEvent
from ..utils.hindi_normalize import normalize_hindi_transcript
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PerceptionAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("api/instructions/perception.md")
        self.vision_model = self._load_vision_model()
        self.weapon_model = self._load_weapon_model()
        self.vosk_model = self._load_vosk_model()
        self._groq_client = self._init_groq_client()

    def _load_vision_model(self):
        if os.getenv("DOORBELL_DISABLE_MODELS", "0") == "1":
            return None

        try:
            yolo_cls = importlib.import_module("ultralytics").YOLO

            model_path = Path("yolov8n.pt")
            if not model_path.exists():
                return None

            return yolo_cls(str(model_path))
        except Exception:
            return None

    def _load_weapon_model(self):
        if os.getenv("DOORBELL_DISABLE_MODELS", "0") == "1":
            return None

        try:
            yolo_cls = importlib.import_module("ultralytics").YOLO

            weapon_model_path = (
                Path(__file__).resolve().parents[2]
                / "weapon_detection"
                / "runs"
                / "detect"
                / "Normal_Compressed"
                / "weights"
                / "best.pt"
            )
            if not weapon_model_path.exists():
                return None
            return yolo_cls(str(weapon_model_path))
        except Exception:
            return None

    def _load_vosk_model(self):
        """Load VOSK speech recognition models for offline STT (English + Hindi)."""
        if os.getenv("DOORBELL_DISABLE_MODELS", "0") == "1":
            return None

        try:
            vosk = importlib.import_module("vosk")
            vosk.SetLogLevel(-1)

            # Load models for supported languages: Indian English + Hindi
            model_search = {
                "en": [
                    Path("models/vosk-model-small-en-in-0.4"),
                    Path("models/vosk-model-small-en-in"),
                    Path("models/vosk-model-small-en-us-0.15"),
                    Path("models/vosk-model-small-en-us"),
                ],
                "hi": [
                    Path("models/vosk-model-small-hi-0.22"),
                    Path("models/vosk-model-small-hi"),
                ],
            }

            loaded_models = {}
            for lang, paths in model_search.items():
                for mp in paths:
                    if mp.exists():
                        logger.info("Loading VOSK %s model from %s", lang, mp)
                        loaded_models[lang] = vosk.Model(str(mp))
                        break

            if not loaded_models:
                logger.warning(
                    "No VOSK models found. STT will return stub results. "
                    "Download from https://alphacephei.com/vosk/models and place in models/ directory. "
                    "Supported: vosk-model-small-en-in-0.4 (English), vosk-model-small-hi-0.22 (Hindi)"
                )
                return None

            logger.info("VOSK models loaded: %s", list(loaded_models.keys()))
            return loaded_models

        except ImportError:
            logger.warning("vosk package not installed. STT disabled.")
            return None
        except Exception as e:
            logger.warning("Failed to load VOSK model: %s", e)
            return None

    def _init_groq_client(self):
        """Initialize the Groq client for Whisper STT if API key is available."""
        if os.getenv("DOORBELL_DISABLE_MODELS", "0") == "1":
            return None
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            logger.info("GROQ_API_KEY not set — Groq Whisper STT unavailable, using VOSK only")
            return None
        try:
            groq_mod = importlib.import_module("groq")
            client = groq_mod.Groq(api_key=api_key)
            logger.info("Groq client initialized for Whisper STT (whisper-large-v3-turbo)")
            return client
        except Exception as exc:
            logger.warning("Failed to initialise Groq client for STT: %s", exc)
            return None

    async def process(self, ring_event: RingEvent) -> PerceptionOutput:
        image_path = ring_event.image_path or ""
        audio_path = ring_event.audio_path

        vision_result = await asyncio.wait_for(
            asyncio.to_thread(self._detect_objects_sync, image_path), timeout=8
        )
        weapon_result = await asyncio.wait_for(
            asyncio.to_thread(self._weapon_detect_sync, image_path), timeout=8
        )

        transcript = ""
        stt_confidence = 0.0
        if audio_path:
            transcript, stt_confidence = await asyncio.wait_for(
                asyncio.to_thread(self._stt_sync, audio_path), timeout=8
            )

        # Normalize Devanagari → Romanized so keyword matching works
        # regardless of whether Whisper outputs Hindi script or Latin text
        normalized_transcript = normalize_hindi_transcript(transcript)

        objects_list = vision_result["objects"]
        num_persons = self._count_persons(objects_list)
        face_visible = self._check_face_visible(objects_list)
        emotion = self._infer_emotion(normalized_transcript)

        # Detect Indian-scenario context flags (claim vs. object mismatches, scam patterns)
        context_flags = self._detect_context_flags(
            transcript=normalized_transcript,
            objects=objects_list,
            person_detected=vision_result["person_detected"],
            num_persons=num_persons,
        )

        anti_spoof_score = self._compute_anti_spoof_score(
            person_detected=vision_result["person_detected"],
            vision_confidence=vision_result["vision_confidence"],
            transcript=normalized_transcript,
            face_visible=face_visible,
            context_flags=context_flags,
        )

        # Save annotated snapshot with detection boxes for audit trail
        annotated_path = ""
        if image_path:
            annotated_path = await asyncio.to_thread(
                self._save_annotated_snapshot,
                ring_event.session_id or "unknown",
                image_path,
                objects_list,
                weapon_result["weapon_labels"],
            )

        logger.info(
            "Perception [%s]: persons=%d face_visible=%s emotion=%s flags=%s anti_spoof=%.2f",
            ring_event.session_id, num_persons, face_visible, emotion,
            context_flags, anti_spoof_score,
        )

        return PerceptionOutput(
            session_id=ring_event.session_id or "",
            person_detected=vision_result["person_detected"],
            objects=objects_list,
            vision_confidence=vision_result["vision_confidence"],
            transcript=transcript,
            stt_confidence=stt_confidence,
            emotion=emotion,
            anti_spoof_score=anti_spoof_score,
            weapon_detected=weapon_result["weapon_detected"],
            weapon_confidence=weapon_result["weapon_confidence"],
            weapon_labels=weapon_result["weapon_labels"],
            image_path=annotated_path or image_path,
            timestamp=datetime.now(timezone.utc),
            num_persons=num_persons,
            face_visible=face_visible,
            context_flags=context_flags,
        )

    def _detect_objects_sync(self, image_path: str) -> dict:
        if not image_path:
            return {
                "person_detected": False,
                "objects": [],
                "vision_confidence": 0.0,
            }

        if self.vision_model is None:
            return {
                "person_detected": True,
                "objects": [ObjectDetection(label="person", conf=0.6)],
                "vision_confidence": 0.6,
            }

        try:
            results = self.vision_model.predict(
                source=image_path,
                imgsz=416,
                device="cpu",
                half=False,
                verbose=False,
            )
            parsed_objects: list[ObjectDetection] = []
            top_conf = 0.0
            person_detected = False
            for result in results:
                boxes = getattr(result, "boxes", None)
                if boxes is None or boxes.conf is None:
                    continue
                for index in range(len(boxes.conf)):
                    confidence = float(boxes.conf[index])
                    class_id = int(boxes.cls[index])
                    label = str(result.names[class_id])
                    parsed_objects.append(ObjectDetection(label=label, conf=confidence))
                    top_conf = max(top_conf, confidence)
                    if label == "person":
                        person_detected = True
            return {
                "person_detected": person_detected,
                "objects": parsed_objects,
                "vision_confidence": top_conf,
            }
        except Exception:
            return {
                "person_detected": True,
                "objects": [ObjectDetection(label="person", conf=0.5)],
                "vision_confidence": 0.5,
            }

    def _weapon_detect_sync(self, image_path: str, conf_thres: float = 0.6) -> dict:
        if not image_path or self.weapon_model is None:
            return {
                "weapon_detected": False,
                "weapon_confidence": 0.0,
                "weapon_labels": [],
            }

        try:
            results = self.weapon_model.predict(
                source=image_path,
                imgsz=416,
                device="cpu",
                half=False,
                verbose=False,
            )
            detected = False
            top_confidence = 0.0
            labels: list[str] = []

            for result in results:
                boxes = getattr(result, "boxes", None)
                if boxes is None or boxes.conf is None:
                    continue
                for index in range(len(boxes.conf)):
                    confidence = float(boxes.conf[index])
                    if confidence < conf_thres:
                        continue
                    class_id = int(boxes.cls[index])
                    label = str(result.names[class_id])
                    detected = True
                    top_confidence = max(top_confidence, confidence)
                    labels.append(label)

            return {
                "weapon_detected": detected,
                "weapon_confidence": top_confidence,
                "weapon_labels": labels,
            }
        except Exception:
            return {
                "weapon_detected": False,
                "weapon_confidence": 0.0,
                "weapon_labels": [],
            }

    def _stt_sync(self, audio_path: str) -> tuple[str, float]:
        """Run Speech-to-Text — tries Groq Whisper API first (excellent Hindi/English),
        then falls back to VOSK offline models.

        Groq Whisper (whisper-large-v3-turbo):
          - Excellent multilingual: Hindi, English, and Hinglish code-switching
          - Cloud API with ~1-2s latency via Groq hardware acceleration
          - Requires GROQ_API_KEY

        VOSK (offline fallback):
          - Works without internet, CPU-only
          - Weaker on Hindi/Hinglish mixed speech

        Returns (transcript, confidence) tuple.
        """
        # --- Strategy 1: Groq Whisper API (best for Hindi/English) ---
        if self._groq_client is not None:
            transcript, confidence = self._stt_groq_whisper(audio_path)
            if transcript:
                return transcript, confidence
            logger.warning("Groq Whisper failed — falling back to VOSK")

        # --- Strategy 2: VOSK offline (fallback) ---
        if self.vosk_model is None:
            logger.info("No STT engine available — returning stub result")
            return "Audio received", 0.5

        models = self.vosk_model if isinstance(self.vosk_model, dict) else {"en": self.vosk_model}

        best_transcript = ""
        best_confidence = 0.0
        best_lang = ""

        for lang, model in models.items():
            transcript, confidence = self._run_vosk_recognizer(audio_path, model)
            if confidence > best_confidence and transcript:
                best_transcript = transcript
                best_confidence = confidence
                best_lang = lang

        if best_transcript:
            logger.info("STT best result [VOSK-%s] (conf=%.3f): %s", best_lang, best_confidence, best_transcript[:80])

        return best_transcript, round(best_confidence, 3)

    def _stt_groq_whisper(self, audio_path: str) -> tuple[str, float]:
        """Transcribe audio using Groq's Whisper API (whisper-large-v3-turbo).

        Supports: Hindi, English, Hinglish code-switching, and 90+ languages.
        Returns (transcript, confidence). Confidence is estimated from the
        API response (Whisper doesn't return per-word confidence in all modes).
        """
        try:
            with open(audio_path, "rb") as audio_file:
                response = self._groq_client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=(os.path.basename(audio_path), audio_file),
                    response_format="verbose_json",
                    language=None,  # auto-detect language (handles Hinglish)
                    temperature=0.0,
                )

            # Extract transcript text
            transcript = ""
            if hasattr(response, "text"):
                transcript = response.text.strip()
            elif isinstance(response, dict):
                transcript = response.get("text", "").strip()

            if not transcript:
                return "", 0.0

            # Estimate confidence from segments if available
            confidence = 0.85  # Whisper-large-v3 is generally high confidence
            segments = getattr(response, "segments", None)
            if segments:
                # avg_logprob → approximate confidence
                avg_logprobs = [s.get("avg_logprob", -0.3) if isinstance(s, dict)
                                else getattr(s, "avg_logprob", -0.3)
                                for s in segments]
                if avg_logprobs:
                    import math
                    mean_logprob = sum(avg_logprobs) / len(avg_logprobs)
                    confidence = round(min(math.exp(mean_logprob), 1.0), 3)

            # Detect language if available
            detected_lang = getattr(response, "language", "unknown")
            if isinstance(response, dict):
                detected_lang = response.get("language", "unknown")

            logger.info(
                "STT [Groq Whisper] lang=%s conf=%.3f: %s",
                detected_lang, confidence, transcript[:100],
            )
            return transcript, confidence

        except Exception as exc:
            logger.warning("Groq Whisper STT failed: %s", exc)
            return "", 0.0

    def _run_vosk_recognizer(self, audio_path: str, model) -> tuple[str, float]:
        """Run a single VOSK model against an audio file. Returns (transcript, confidence)."""
        try:
            vosk = importlib.import_module("vosk")

            wf = wave.open(audio_path, "rb")
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                logger.warning("Audio format not ideal (expected mono 16-bit). Attempting anyway.")

            sample_rate = wf.getframerate()
            rec = vosk.KaldiRecognizer(model, sample_rate)
            rec.SetWords(True)  # request word-level confidence when available

            transcript_parts = []
            total_confidence = 0.0
            num_results = 0

            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get("text", "")
                    if text:
                        transcript_parts.append(text)
                        num_results += 1
                        if "result" in result:
                            word_confs = [w.get("conf", 0.0) for w in result["result"]]
                            if word_confs:
                                total_confidence += sum(word_confs) / len(word_confs)
                            else:
                                total_confidence += 0.7  # default confidence when words recognized but no per-word conf
                        else:
                            total_confidence += 0.7  # default confidence for text without word-level detail

            final_result = json.loads(rec.FinalResult())
            final_text = final_result.get("text", "")
            if final_text:
                transcript_parts.append(final_text)
                num_results += 1
                if "result" in final_result:
                    word_confs = [w.get("conf", 0.0) for w in final_result["result"]]
                    if word_confs:
                        total_confidence += sum(word_confs) / len(word_confs)
                    else:
                        total_confidence += 0.7
                else:
                    total_confidence += 0.7

            wf.close()

            transcript = " ".join(transcript_parts).strip()
            avg_confidence = (total_confidence / num_results) if num_results > 0 else 0.0

            if not transcript:
                return "", 0.0

            return transcript, avg_confidence

        except Exception as e:
            logger.error("VOSK recognizer failed for %s: %s", audio_path, e)
            return "", 0.0

    # ------------------------------------------------------------------
    # Emotion inference — expanded for Indian household scenarios
    # ------------------------------------------------------------------

    # Keywords grouped by detected emotion (English + Hindi/Hinglish)
    _EMOTION_KEYWORDS: dict[str, list[str]] = {
        "aggressive": [
            # English aggression / threat
            "angry", "open the door", "break", "smash", "kill",
            "threat", "hit", "punch", "attack", "fight",
            # Hindi / Hinglish aggression
            "dekh lena", "todenge", "maar", "kholiye warna", "warna",
            "dhamki", "peetna", "chaku", "goli", "maarunga",
            "jaan se", "barbad", "khatam", "darwaza tod",
        ],
        "distressed": [
            # English distress
            "help", "emergency", "accident", "fire", "ambulance",
            "police", "hospital", "blood", "hurt", "injured",
            "lost", "missing", "scared", "afraid",
            # Hindi distress
            "bachao", "madad", "aag", "lagi", "kho gayi",
            "mummy kho", "daddy kho", "dard", "chot", "gir gaya",
            "ro raha", "dar", "hospital", "khoon",
        ],
        "concerned": [
            "urgent", "please", "sorry", "important", "zaroori",
            "bahut zaroori", "jaldi", "request", "kripya",
        ],
        "nervous": [
            "actually", "umm", "well", "basically", "you see",
            "matlab", "woh", "darasal",
        ],
    }

    def _infer_emotion(self, transcript: str) -> str:
        text = transcript.lower().strip()
        if not text:
            return "neutral"

        # Check aggressive first (highest priority)
        for emotion in ("aggressive", "distressed", "concerned", "nervous"):
            keywords = self._EMOTION_KEYWORDS.get(emotion, [])
            if any(kw in text for kw in keywords):
                return emotion

        return "neutral"

    # ------------------------------------------------------------------
    # Context flags — Indian household mismatch & anomaly detection
    # ------------------------------------------------------------------

    def _detect_context_flags(
        self,
        transcript: str,
        objects: list[ObjectDetection],
        person_detected: bool,
        num_persons: int,
    ) -> list[str]:
        """Analyse transcript vs detected objects for mismatches and risk signals."""
        flags: list[str] = []
        text = transcript.lower()
        obj_labels = {o.label.lower() for o in objects}

        # 1. Delivery claim but no package/box/bag visible
        delivery_words = {"delivery", "parcel", "package", "courier", "amazon", "flipkart", "dhl"}
        if any(w in text for w in delivery_words):
            package_labels = {"backpack", "suitcase", "handbag", "box", "package", "bag"}
            if not (obj_labels & package_labels) and person_detected:
                flags.append("claim_object_mismatch")

        # 2. OTP / verification code request (Indian scam pattern)
        if any(kw in text for kw in ["otp", "verification code", "verify karna", "code bata"]):
            flags.append("otp_request")

        # 3. Occupancy probe — asking if anyone is home
        occupancy_phrases = [
            "koi ghar pe", "koi hai", "anyone home", "is anyone",
            "ghar pe hai", "kaun hai ghar", "owner hai kya",
        ]
        if any(p in text for p in occupancy_phrases):
            flags.append("occupancy_probe")

        # 4. Entry request
        entry_phrases = [
            "andar aana", "andar aane", "let me in", "open the door",
            "darwaza khol", "gate khol", "lift use", "building mein",
            "enter", "come inside",
        ]
        if any(p in text for p in entry_phrases):
            flags.append("entry_request")

        # 5. Financial request — UPI / bank / money
        financial_phrases = [
            "upi", "qr scan", "bank", "account number", "paisa",
            "rupees", "payment", "transfer", "refund", "cod",
            "change milega", "paise", "cash",
        ]
        if any(p in text for p in financial_phrases):
            flags.append("financial_request")

        # 6. Identity claim (unverifiable through doorbell)
        identity_phrases = [
            "owner ne bola", "relative hoon", "chacha hoon", "mama hoon",
            "friend hoon", "personally jaanta", "i know the owner",
            "unke bete", "unki wife", "ghar wale", "family member",
        ]
        if any(p in text for p in identity_phrases):
            flags.append("identity_claim")

        # 7. Government / authority claim
        authority_phrases = [
            "police", "government", "court", "legal notice", "tax",
            "aadhaar", "kyc", "bijli", "electricity", "gas",
            "water board", "meter reading", "inspection", "verification",
        ]
        if any(p in text for p in authority_phrases):
            flags.append("authority_claim")

        # 8. Staff claim (domestic help)
        staff_phrases = [
            "kaam karungi", "kaam karta", "bai", "maid", "cook",
            "driver", "chaabi", "keys", "kaam wali", "safai",
            "purani bai", "naya", "replacement",
        ]
        if any(p in text for p in staff_phrases):
            flags.append("staff_claim")

        # 9. Religious / donation request
        donation_phrases = [
            "chanda", "donation", "mandir", "temple", "masjid",
            "church", "gurudwara", "havan", "puja", "bhagwan",
            "society collection", "ganpati", "durga",
        ]
        if any(p in text for p in donation_phrases):
            flags.append("donation_request")

        # 10. Multi-person situation
        if num_persons > 1:
            flags.append("multi_person")

        # 11. Face not clearly visible (set externally via face_visible flag)
        # — handled in anti_spoof_score computation

        return flags

    def _count_persons(self, objects: list[ObjectDetection]) -> int:
        """Count number of person detections in object list."""
        return sum(1 for o in objects if o.label.lower() == "person")

    def _check_face_visible(self, objects: list[ObjectDetection]) -> bool:
        """Heuristic: if person detected but vision confidence is very low,
        face may be obscured/hidden."""
        persons = [o for o in objects if o.label.lower() == "person"]
        if not persons:
            return True  # no person = not applicable
        # If best person confidence is below threshold, face likely obscured
        best_conf = max(p.conf for p in persons)
        return best_conf >= 0.35

    # ------------------------------------------------------------------
    # Anti-spoof — enhanced with context flags
    # ------------------------------------------------------------------

    def _compute_anti_spoof_score(
        self,
        person_detected: bool,
        vision_confidence: float,
        transcript: str,
        face_visible: bool = True,
        context_flags: list[str] | None = None,
    ) -> float:
        if not person_detected:
            return 0.9

        score = 0.0

        # Low vision confidence penalty
        if vision_confidence < 0.4:
            score += 0.2

        # Silent visitor (no speech)
        if transcript.strip() == "":
            score += 0.05

        # Face hidden / camera blocking
        if not face_visible:
            score += 0.25

        # Context mismatch penalties
        if context_flags:
            if "claim_object_mismatch" in context_flags:
                score += 0.20
            if "otp_request" in context_flags:
                score += 0.15
            if "occupancy_probe" in context_flags:
                score += 0.15

        return min(score, 1.0)

    def _save_annotated_snapshot(
        self,
        session_id: str,
        image_path: str,
        objects: list[ObjectDetection],
        weapon_labels: list[str],
    ) -> str:
        """Save an annotated copy of the snapshot with detection labels overlaid.

        Uses Pillow (PIL) to draw bounding info as text overlay.
        Returns the path to the annotated image, or empty string on failure.
        """
        try:
            PIL_Image = importlib.import_module("PIL.Image")
            PIL_Draw = importlib.import_module("PIL.ImageDraw")

            img = PIL_Image.open(image_path)
            draw = PIL_Draw.Draw(img)

            # Draw detection labels in top-left corner
            y_offset = 10
            for obj in objects:
                color = "red" if obj.label in weapon_labels else "lime"
                text = f"{obj.label}: {obj.conf:.2f}"
                draw.text((10, y_offset), text, fill=color)
                y_offset += 18

            if weapon_labels:
                draw.text(
                    (10, y_offset + 5),
                    f"WEAPON: {', '.join(weapon_labels)}",
                    fill="red",
                )

            # Save to data/snaps/{session_id}_annot.jpg
            snaps_dir = Path("data/snaps")
            snaps_dir.mkdir(parents=True, exist_ok=True)
            annot_path = snaps_dir / f"{session_id}_annot.jpg"
            img.save(str(annot_path), "JPEG", quality=85)

            logger.info("Saved annotated snapshot: %s", annot_path)
            return str(annot_path).replace("\\", "/")

        except Exception as e:
            logger.warning("Failed to save annotated snapshot: %s", e)
            return ""
