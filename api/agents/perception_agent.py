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
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class PerceptionAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("api/instructions/perception.md")
        self.vision_model = self._load_vision_model()
        self.weapon_model = self._load_weapon_model()
        self.vosk_model = self._load_vosk_model()

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

        emotion = self._infer_emotion(transcript)
        anti_spoof_score = self._compute_anti_spoof_score(
            person_detected=vision_result["person_detected"],
            vision_confidence=vision_result["vision_confidence"],
            transcript=transcript,
        )

        # Save annotated snapshot with detection boxes for audit trail
        annotated_path = ""
        if image_path:
            annotated_path = await asyncio.to_thread(
                self._save_annotated_snapshot,
                ring_event.session_id or "unknown",
                image_path,
                vision_result["objects"],
                weapon_result["weapon_labels"],
            )

        return PerceptionOutput(
            session_id=ring_event.session_id or "",
            person_detected=vision_result["person_detected"],
            objects=vision_result["objects"],
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
        """Run Speech-to-Text using VOSK (offline, CPU-only).

        Tries all loaded language models (English, Hindi) and picks the result
        with the highest confidence. Returns (transcript, confidence) tuple.
        Audio should be WAV format, preferably 16kHz mono.
        """
        if self.vosk_model is None:
            logger.info("VOSK models not loaded — returning stub STT result")
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
            logger.info("STT best result [%s] (conf=%.3f): %s", best_lang, best_confidence, best_transcript[:80])

        return best_transcript, round(best_confidence, 3)

    def _run_vosk_recognizer(self, audio_path: str, model) -> tuple[str, float]:
        """Run a single VOSK model against an audio file. Returns (transcript, confidence)."""
        try:
            vosk = importlib.import_module("vosk")

            wf = wave.open(audio_path, "rb")
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                logger.warning("Audio format not ideal (expected mono 16-bit). Attempting anyway.")

            sample_rate = wf.getframerate()
            rec = vosk.KaldiRecognizer(model, sample_rate)

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
                        if "result" in result:
                            word_confs = [w.get("conf", 0.0) for w in result["result"]]
                            if word_confs:
                                total_confidence += sum(word_confs) / len(word_confs)
                                num_results += 1

            final_result = json.loads(rec.FinalResult())
            final_text = final_result.get("text", "")
            if final_text:
                transcript_parts.append(final_text)
                if "result" in final_result:
                    word_confs = [w.get("conf", 0.0) for w in final_result["result"]]
                    if word_confs:
                        total_confidence += sum(word_confs) / len(word_confs)
                        num_results += 1

            wf.close()

            transcript = " ".join(transcript_parts).strip()
            avg_confidence = (total_confidence / num_results) if num_results > 0 else 0.0

            if not transcript:
                return "", 0.0

            return transcript, avg_confidence

        except Exception as e:
            logger.error("VOSK recognizer failed for %s: %s", audio_path, e)
            return "", 0.0

    def _infer_emotion(self, transcript: str) -> str:
        text = transcript.lower().strip()
        if any(word in text for word in ["help", "urgent", "please"]):
            return "concerned"
        if any(word in text for word in ["delivery", "package", "amazon"]):
            return "neutral"
        if any(word in text for word in ["angry", "open", "now"]):
            return "aggressive"
        return "neutral"

    def _compute_anti_spoof_score(
        self,
        person_detected: bool,
        vision_confidence: float,
        transcript: str,
    ) -> float:
        if not person_detected:
            return 0.9

        score = 0.0
        if vision_confidence < 0.4:
            score += 0.2
        if transcript.strip() == "":
            score += 0.05

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
