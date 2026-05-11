"""
UDARiskMLService – scikit-learn model loader and predictor.

Architecture
────────────
This service wraps two pickle artefacts stored in ``backend/weights/``:

  uda_risk_model.pkl   – A trained sklearn estimator (e.g. RandomForest,
                          GradientBoosting, SVC …) that accepts a fixed-width
                          numeric feature vector and returns a numeric class label.

  label_encoder.pkl    – A fitted ``sklearn.preprocessing.LabelEncoder`` that maps
                          the numeric prediction back to a human-readable risk level
                          (e.g. 0 → "LOW", 1 → "MEDIUM", 2 → "HIGH", 3 → "CRITICAL").

Both files are loaded **once** at application startup via ``UDARiskMLService.load()``,
which is called from the FastAPI lifespan context in ``app/main.py``.

Startup behaviour
─────────────────
If either file is missing, loading is skipped gracefully and
``UDARiskMLService.available`` remains ``False``.  All endpoints that depend on the
ML model will then fall back to a rule-based response rather than crashing the server.

Feature engineering
───────────────────
The model expects a 4-element numeric feature vector in this exact column order:

  Index  Feature                     Encoding
  ─────  ──────────────────────────  ──────────────────────────────────────────
  0      construction_stage          STAGE_ORDINAL  (0 = PRE_CONSTRUCTION … 12 = COMPLETE)
  1      approval_status             STATUS_ORDINAL (0 = NOT_STARTED … 5 = REJECTED)
  2      zoning_type                 ZONING_ORDINAL (0 = RESIDENTIAL … 3 = MIXED_USE)
  3      estimated_project_value_lkr Continuous (0.0 when not supplied)

Update the three ordinal dicts below if the training pipeline used a different
encoding scheme.  DO NOT change the column order without retraining the model.

Dependency injection
────────────────────
``get_ml_risk_service()`` is registered as a FastAPI dependency so the service
can be replaced in tests via ``app.dependency_overrides``::

    app.dependency_overrides[get_ml_risk_service] = lambda: MockMLService()
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Artefact paths ─────────────────────────────────────────────────────────────

_WEIGHTS_DIR  = Path(__file__).resolve().parents[2] / "weights"
_MODEL_PATH   = _WEIGHTS_DIR / "uda_risk_model.pkl"
_ENCODER_PATH = _WEIGHTS_DIR / "label_encoder.pkl"

# ── Ordinal feature encodings ──────────────────────────────────────────────────
# Must match the encoding used during model training.

STAGE_ORDINAL: dict[str, int] = {
    "PRE_CONSTRUCTION":    0,
    "SITE_PREPARATION":    1,
    "EXCAVATION":          2,
    "FOUNDATION_STARTED":  3,
    "FOUNDATION_COMPLETE": 4,
    "STRUCTURAL_FRAMING":  5,
    "ROUGH_MEP_INSTALL":   6,
    "ROOFING":             7,
    "EXTERNAL_ENVELOPE":   8,
    "FINISHING":           9,
    "FINAL_INSPECTIONS":   10,
    "OCCUPANCY_READY":     11,
    "COMPLETE":            12,
}

STATUS_ORDINAL: dict[str, int] = {
    "NOT_STARTED":        0,
    "DOCUMENT_GATHERING": 1,
    "SUBMITTED":          2,
    "UNDER_REVIEW":       3,
    "APPROVED":           4,
    "REJECTED":           5,
}

ZONING_ORDINAL: dict[str, int] = {
    "RESIDENTIAL": 0,
    "COMMERCIAL":  1,
    "INDUSTRIAL":  2,
    "MIXED_USE":   3,
}


# ── Custom exceptions ──────────────────────────────────────────────────────────


class ModelNotAvailableError(RuntimeError):
    """Raised when a prediction is requested but the ML model is not loaded."""


# ── Service class ──────────────────────────────────────────────────────────────


class UDARiskMLService:
    """
    Singleton ML service for UDA permit risk prediction.

    Lifecycle
    ─────────
    1. Instantiated at module level (``_ml_service`` below).
    2. ``load()`` called once during FastAPI lifespan startup.
    3. ``predict()`` called per-request from the router.
    4. ``available`` checked by the router to decide rule-based fallback.
    """

    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._label_encoder: Optional[object] = None
        self._available: bool = False
        self._load_error: Optional[str] = None

    # ── Startup loading ────────────────────────────────────────────────────────

    def load(self) -> None:
        """
        Load ``uda_risk_model.pkl`` and ``label_encoder.pkl`` into memory.

        Always returns without raising.  Errors are logged and stored in
        ``self._load_error`` so the caller can surface them via ``/health``.
        """
        self._available = False
        self._load_error = None

        # ── 1. Load the trained estimator ─────────────────────────────────────
        try:
            with _MODEL_PATH.open("rb") as fh:
                self._model = pickle.load(fh)  # noqa: S301 — trusted artefact
            logger.info("UDA risk model loaded from %s", _MODEL_PATH)
        except FileNotFoundError:
            self._load_error = (
                f"Model artefact not found: {_MODEL_PATH}. "
                "Place uda_risk_model.pkl in the weights/ directory."
            )
            logger.warning(
                "UDA risk model not found at %s — ML predictions disabled. "
                "Rule-based fallback is active.",
                _MODEL_PATH,
            )
            return
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"Failed to unpickle model: {exc}"
            logger.exception("Unexpected error loading UDA risk model: %s", exc)
            return

        # ── 2. Load the label encoder ─────────────────────────────────────────
        try:
            with _ENCODER_PATH.open("rb") as fh:
                self._label_encoder = pickle.load(fh)  # noqa: S301
            logger.info("Label encoder loaded from %s", _ENCODER_PATH)
        except FileNotFoundError:
            self._load_error = (
                f"Label encoder not found: {_ENCODER_PATH}. "
                "Place label_encoder.pkl in the weights/ directory."
            )
            logger.warning(
                "Label encoder not found at %s — ML predictions disabled.",
                _ENCODER_PATH,
            )
            # Unload model too — partial state is unsafe
            self._model = None
            return
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"Failed to unpickle label encoder: {exc}"
            logger.exception("Unexpected error loading label encoder: %s", exc)
            self._model = None
            return

        self._available = True
        logger.info("UDARiskMLService ready — ML predictions enabled.")

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True when both artefacts loaded successfully and predictions can be made."""
        return self._available

    @property
    def load_error(self) -> Optional[str]:
        """Human-readable description of the last load failure, or None."""
        return self._load_error

    # ── Feature engineering ────────────────────────────────────────────────────

    def build_feature_vector(
        self,
        construction_stage: str,
        approval_status: str,
        zoning_type: str,
        project_value_lkr: float,
    ) -> list[float]:
        """
        Convert raw input values into the numeric feature vector expected by the model.

        Raises ``ValueError`` when an unknown categorical value is supplied —
        the caller (router) should surface this as HTTP 422.
        """
        if construction_stage not in STAGE_ORDINAL:
            raise ValueError(
                f"Unknown construction_stage '{construction_stage}'. "
                f"Valid values: {list(STAGE_ORDINAL.keys())}"
            )
        if approval_status not in STATUS_ORDINAL:
            raise ValueError(
                f"Unknown approval_status '{approval_status}'. "
                f"Valid values: {list(STATUS_ORDINAL.keys())}"
            )
        if zoning_type not in ZONING_ORDINAL:
            raise ValueError(
                f"Unknown zoning_type '{zoning_type}'. "
                f"Valid values: {list(ZONING_ORDINAL.keys())}"
            )

        return [
            float(STAGE_ORDINAL[construction_stage]),
            float(STATUS_ORDINAL[approval_status]),
            float(ZONING_ORDINAL[zoning_type]),
            max(0.0, project_value_lkr),
        ]

    # ── Prediction ─────────────────────────────────────────────────────────────

    def predict(
        self,
        construction_stage: str,
        approval_status: str,
        zoning_type: str,
        project_value_lkr: float,
    ) -> "MLPredictionResult":
        """
        Run inference and return a structured result.

        Raises
        ──────
        ModelNotAvailableError
            When the model artefacts were not loaded (FileNotFoundError at startup).
        ValueError
            When feature encoding fails due to an unrecognised categorical value.
        """
        if not self._available:
            raise ModelNotAvailableError(
                self._load_error
                or "ML model is not available. Check startup logs."
            )

        # Build feature vector
        features = self.build_feature_vector(
            construction_stage=construction_stage,
            approval_status=approval_status,
            zoning_type=zoning_type,
            project_value_lkr=project_value_lkr,
        )
        X = np.array(features, dtype=np.float64).reshape(1, -1)

        # Raw prediction (numeric class index)
        raw_label: int = int(self._model.predict(X)[0])  # type: ignore[union-attr]

        # Decode via label encoder
        try:
            risk_level: str = str(
                self._label_encoder.inverse_transform([raw_label])[0]  # type: ignore[union-attr]
            ).upper()
        except Exception:  # noqa: BLE001
            # Encoder may not have seen this label — fall back to str
            risk_level = str(raw_label).upper()

        # Prediction probability (confidence) if the estimator supports it
        confidence: Optional[float] = None
        if hasattr(self._model, "predict_proba"):
            proba = self._model.predict_proba(X)[0]  # type: ignore[union-attr]
            confidence = round(float(max(proba)), 4)

        logger.debug(
            "ML prediction | stage=%s status=%s zone=%s raw=%d risk=%s conf=%s",
            construction_stage,
            approval_status,
            zoning_type,
            raw_label,
            risk_level,
            confidence,
        )

        return MLPredictionResult(
            risk_level=risk_level,
            raw_label=raw_label,
            confidence=confidence,
        )


# ── Result dataclass (not a Pydantic model — internal only) ───────────────────


class MLPredictionResult:
    """Lightweight container for a single ML prediction."""

    __slots__ = ("risk_level", "raw_label", "confidence")

    def __init__(
        self,
        risk_level: str,
        raw_label: int,
        confidence: Optional[float],
    ) -> None:
        self.risk_level  = risk_level
        self.raw_label   = raw_label
        self.confidence  = confidence


# ── Module-level singleton ─────────────────────────────────────────────────────

_ml_service = UDARiskMLService()


def get_ml_risk_service() -> UDARiskMLService:
    """
    FastAPI dependency that returns the module-level singleton.

    Override in tests::

        app.dependency_overrides[get_ml_risk_service] = lambda: MockMLService()
    """
    return _ml_service
