"""Adapter for the IterateAI/OpenThreatDetection weapon-detection model.

The upstream model is a TensorFlow SavedModel (YOLOv4 architecture) that
classifies threats into Gun / Knife / Riffle (sic — upstream's spelling).

The rest of the codebase only ever sees a duck-typed object with two methods —
`detect_from_path` and `detect_from_array` — both returning the same dict shape
the legacy YOLO code returned:

    {"weapon_detected": bool, "weapon_confidence": float, "weapon_labels": list[str]}

Reference upstream pipeline (faithfully reproduced here):
    /tmp/OpenThreatDetection/wepapp/wepcore/inference_images_weapon.py
    - Resize BGR frame to (608, 608)
    - Normalise /255.0
    - Run signatures['serving_default']
    - Output: (1, N, 4+num_classes) — boxes + per-class scores
    - tf.image.combined_non_max_suppression with iou=0.5, score=<our conf>
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve weight paths once, in priority order:
#   1. OPENTHREAT_WEIGHTS_PATH env var (operator override — directory path)
#   2. weapon_detection/openthreat/savedmodel/ (default in-repo location)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OPENTHREAT_PATH = _PROJECT_ROOT / "weapon_detection" / "openthreat" / "savedmodel"
_DEFAULT_CLASS_NAMES = ["Gun", "Knife", "Riffle"]
_INPUT_SIZE = 608
_IOU_THRESHOLD = 0.5
_MAX_DETECTIONS = 50


def _resolve_weights_path() -> Path | None:
    override = os.getenv("OPENTHREAT_WEIGHTS_PATH")
    if override:
        p = Path(override)
        if p.exists() and (p / "saved_model.pb").exists():
            return p
        logger.warning(
            "OPENTHREAT_WEIGHTS_PATH=%s is not a SavedModel directory — "
            "falling back to default path",
            override,
        )
    if _DEFAULT_OPENTHREAT_PATH.exists() and (_DEFAULT_OPENTHREAT_PATH / "saved_model.pb").exists():
        return _DEFAULT_OPENTHREAT_PATH
    return None


def _load_class_names(weights_path: Path) -> list[str]:
    # Look in the savedmodel dir, then one level up (where we keep weapons.names).
    for candidate in (weights_path / "weapons.names", weights_path.parent / "weapons.names"):
        if candidate.exists():
            try:
                names = [line.strip() for line in candidate.read_text().splitlines() if line.strip()]
                if names:
                    return names
            except Exception as exc:
                logger.debug("Failed to read class names from %s: %s", candidate, exc)
    return list(_DEFAULT_CLASS_NAMES)


class OpenThreatDetector:
    """Thin TF adapter around the OpenThreatDetection SavedModel.

    Failure modes are non-raising — every method returns the safe-default dict
    on missing model, decode error, or inference exception.
    """

    SAFE_DEFAULT: dict = {
        "weapon_detected": False,
        "weapon_confidence": 0.0,
        "weapon_labels": [],
    }

    def __init__(self, weights_path: Path | None = None) -> None:
        self.weights_path = weights_path or _resolve_weights_path()
        self._infer_fn: Any | None = None
        self._class_names: list[str] = list(_DEFAULT_CLASS_NAMES)
        if self.weights_path is not None:
            self._load()

    @property
    def is_loaded(self) -> bool:
        return self._infer_fn is not None

    def _load(self) -> None:
        # Quiet TF logging unless the operator wants the full firehose.
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        try:
            import tensorflow as tf  # type: ignore
            from tensorflow.python.saved_model import tag_constants  # type: ignore
        except Exception as exc:
            logger.warning("OpenThreatDetector: tensorflow import failed: %s", exc)
            return
        try:
            model = tf.saved_model.load(str(self.weights_path), tags=[tag_constants.SERVING])
            sigs = list(model.signatures.keys())
            if "serving_default" not in sigs:
                logger.warning(
                    "OpenThreatDetector: SavedModel has no 'serving_default' "
                    "signature (found: %s)",
                    sigs,
                )
                return
            self._infer_fn = model.signatures["serving_default"]
            self._class_names = _load_class_names(self.weights_path)
            # WARNING level so it's visible under uvicorn's default log config.
            logger.warning(
                "OpenThreatDetector: loaded TF SavedModel from %s (classes=%s)",
                self.weights_path,
                self._class_names,
            )
        except Exception as exc:
            logger.warning("OpenThreatDetector: failed to load %s: %s", self.weights_path, exc)
            self._infer_fn = None

    def _predict(self, image_bgr, conf: float) -> dict:
        if self._infer_fn is None:
            return dict(self.SAFE_DEFAULT)
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
            import tensorflow as tf  # type: ignore
        except Exception as exc:
            logger.debug("OpenThreatDetector: runtime import failed: %s", exc)
            return dict(self.SAFE_DEFAULT)

        try:
            resized = cv2.resize(image_bgr, (_INPUT_SIZE, _INPUT_SIZE))
            data = (resized / 255.0).astype(np.float32)[np.newaxis, ...]
            batch = tf.constant(data)
            pred = self._infer_fn(batch)

            # Output is a single-key dict; key name varies by export. The
            # upstream code iterates and grabs the first value the same way.
            value = next(iter(pred.values()))
            boxes = value[:, :, 0:4]
            scores = value[:, :, 4:]

            nms_boxes, nms_scores, nms_classes, valid = tf.image.combined_non_max_suppression(
                boxes=tf.reshape(boxes, (tf.shape(boxes)[0], -1, 1, 4)),
                scores=tf.reshape(
                    scores, (tf.shape(scores)[0], -1, tf.shape(scores)[-1])
                ),
                max_output_size_per_class=_MAX_DETECTIONS,
                max_total_size=_MAX_DETECTIONS,
                iou_threshold=_IOU_THRESHOLD,
                score_threshold=conf,
            )

            valid_n = int(valid.numpy()[0])
            if valid_n == 0:
                return dict(self.SAFE_DEFAULT)
            scores_arr = nms_scores.numpy()[0][:valid_n]
            classes_arr = nms_classes.numpy()[0][:valid_n].astype(int)

            labels: list[str] = []
            for c in classes_arr:
                if 0 <= c < len(self._class_names):
                    labels.append(self._class_names[c])
                else:
                    labels.append(f"class_{c}")

            return {
                "weapon_detected": True,
                "weapon_confidence": float(np.max(scores_arr)),
                "weapon_labels": labels,
            }
        except Exception as exc:
            logger.debug("OpenThreatDetector inference failed: %s", exc)
            return dict(self.SAFE_DEFAULT)

    def detect_from_path(self, image_path: str, conf: float = 0.55) -> dict:
        if not image_path or self._infer_fn is None:
            return dict(self.SAFE_DEFAULT)
        try:
            import cv2  # type: ignore
        except Exception:
            return dict(self.SAFE_DEFAULT)
        img = cv2.imread(image_path)
        if img is None:
            return dict(self.SAFE_DEFAULT)
        return self._predict(img, conf)

    def detect_from_array(self, frame, conf: float = 0.55) -> dict:
        if frame is None or self._infer_fn is None:
            return dict(self.SAFE_DEFAULT)
        return self._predict(frame, conf)
