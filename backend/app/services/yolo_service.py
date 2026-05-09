"""
YOLOv8 inference service.

Loads the model once at module import time (singleton pattern) so that
the heavy initialisation cost is paid only on startup, not per request.

Model path: weights/best.pt  (relative to the backend project root)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import torch
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# ── Model weight path ──────────────────────────────────────────────────────────

# Resolve relative to *this file's* package root so the path works regardless
# of the working directory the server is launched from.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # …/backend/
WEIGHTS_PATH: Path = _BACKEND_ROOT / "weights" / "best.pt"

# ── Pydantic-style result dataclasses ─────────────────────────────────────────


@dataclass
class BoundingBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: BoundingBox


@dataclass
class InferenceResult:
    success: bool
    detections: List[Detection] = field(default_factory=list)
    error: str | None = None


# ── Singleton model loader ─────────────────────────────────────────────────────


class _YOLOService:
    """Holds a single loaded YOLO model instance, initialised lazily."""

    _model: YOLO | None = None

    def _load(self) -> YOLO:
        if self._model is None:
            if not WEIGHTS_PATH.exists():
                raise FileNotFoundError(
                    f"YOLO weights not found at '{WEIGHTS_PATH}'. "
                    "Place your trained best.pt inside the backend/weights/ folder."
                )
            logger.info("Loading YOLO model from %s …", WEIGHTS_PATH)
            self._model = YOLO(str(WEIGHTS_PATH))
            # Move to GPU if available for faster inference
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model.to(device)
            logger.info("YOLO model loaded on device: %s", device)
        return self._model

    def run(self, image_path: str | Path) -> InferenceResult:
        """
        Run YOLOv8 inference on *image_path* and return structured detections.

        Args:
            image_path: Absolute or relative path to the temporary image file.

        Returns:
            InferenceResult with a list of Detection objects.
        """
        try:
            model = self._load()
            results = model(str(image_path), verbose=False)

            detections: list[Detection] = []

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                class_names: dict[int, str] = result.names  # {0: 'person', …}

                for box in boxes:
                    # xyxy tensor → Python floats
                    x_min, y_min, x_max, y_max = (
                        float(v) for v in box.xyxy[0].tolist()
                    )
                    confidence = float(box.conf[0])
                    class_id = int(box.cls[0])
                    class_name = class_names.get(class_id, str(class_id))

                    detections.append(
                        Detection(
                            class_name=class_name,
                            confidence=round(confidence, 4),
                            bbox=BoundingBox(
                                x_min=round(x_min, 2),
                                y_min=round(y_min, 2),
                                x_max=round(x_max, 2),
                                y_max=round(y_max, 2),
                            ),
                        )
                    )

            return InferenceResult(success=True, detections=detections)

        except FileNotFoundError:
            raise  # let the router surface this as a 500
        except Exception as exc:
            logger.exception("YOLO inference failed: %s", exc)
            return InferenceResult(success=False, error=str(exc))


# Module-level singleton — imported by the router
yolo_service = _YOLOService()
