"""
LifecycleDegradationService  –  Component 4 / Lifecycle Predictor
──────────────────────────────────────────────────────────────────
Wraps the pre-trained XGBoost / scikit-learn lifecycle degradation model at:

    backend/weights/lifecycle_model.pkl

Feature contract  (placeholder – adjust to match your training pipeline)
────────────────────────────────────────────────────────────────────────
  Index  Feature                  Type   Range
  ─────  ───────────────────────  ─────  ──────────────────────────────────────
  0      material_quality         int    1 (very poor) – 10 (excellent)
  1      environmental_harshness  int    1 (mild/inland) – 10 (extreme/coastal)
  2      soil_acidity             float  pH 3.0 – 9.0  (7.0 = neutral)
  3      maintenance_frequency    int    1 (monthly) – 12 (once per year)

Update these four features and the feature-vector order once your final
model is trained; no other part of the codebase needs to change.

Risk thresholds
───────────────
  predicted lifespan < 30 yrs  → 'High'
  30 ≤ predicted lifespan ≤ 50 → 'Medium'
  predicted lifespan > 50 yrs  → 'Low'

Model loading order
───────────────────
joblib.load() is attempted first (preferred for sklearn / XGBoost pipelines).
Falls back to pickle.load() automatically for compatibility.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import NamedTuple, Optional

import numpy as np
import pandas as pd

try:
    import joblib as _joblib
    _USE_JOBLIB = True
except ImportError:
    _USE_JOBLIB = False

logger = logging.getLogger(__name__)

# ── Artefact path ──────────────────────────────────────────────────────────────

_WEIGHTS_DIR = Path(__file__).resolve().parents[2] / "weights"
_MODEL_PATH  = _WEIGHTS_DIR / "lifecycle_model.pkl"

# Emit path diagnostics at import time so they appear in the uvicorn startup log
# even before load() is called.  Operators can verify the resolved path without
# attaching a debugger.
logger.info("[lifecycle_service] Weights directory : %s", _WEIGHTS_DIR)
logger.info("[lifecycle_service] Model path       : %s", _MODEL_PATH)
logger.info("[lifecycle_service] lifecycle_model.pkl exists: %s", _MODEL_PATH.exists())

# ── Risk thresholds ────────────────────────────────────────────────────────────
# Derived from predicted lifespan in years. Tune to match your risk appetite.

_RISK_THRESHOLDS: list[tuple[float, str]] = [
    (30.0, "High"),    # lifespan < 30 yrs  → High
    (50.0, "Medium"),  # 30 ≤ lifespan < 50 → Medium
    (200.0, "Low"),    # lifespan ≥ 50      → Low
]

# ── Feature column order (must match training pipeline EXACTLY) ──────────────────
# Case-sensitive — these are the exact column names the model was trained with.

_FEATURE_COLUMNS: list[str] = [
    "Material_Type",
    "Distance_to_Sea_m",
    "Humidity_Level",
    "Maintenance_Cost_Percentage",
]

# Material_Type is already supplied as an integer (0, 1, 2) by the caller.
# No label-encoding dictionary is needed for this model.


# ── Return type ────────────────────────────────────────────────────────────────


class LifecyclePrediction(NamedTuple):
    estimated_lifespan_years: float
    risk_level: str              # "Low" | "Medium" | "High"
    confidence: Optional[float]  # None when model lacks predict_proba


# ── Custom exception ───────────────────────────────────────────────────────────


class LifecycleModelNotAvailableError(RuntimeError):
    """Raised when a prediction is requested but no model is loaded."""


# ── Service ────────────────────────────────────────────────────────────────────


class LifecycleDegradationService:
    """
    Singleton lifecycle degradation predictor.

    Lifecycle
    ─────────
    1. Instantiated at module level (``lifecycle_service`` singleton).
    2. ``load()`` called once in ``main.py`` lifespan startup.
    3. ``predict()`` called per-request from the router.
    4. ``available`` guards the route — returns HTTP 503 when False.
    """

    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._available: bool = False
        self._load_error: Optional[str] = None

    # ── Startup loading ────────────────────────────────────────────────────────

    def load(self) -> None:
        """
        Load ``lifecycle_model.pkl`` into memory using joblib (preferred)
        or pickle as fallback.

        Never raises — keeps the service in ``available=False`` when the
        artefact is absent so the endpoint degrades to HTTP 503 cleanly.
        """
        self._available = False
        self._load_error = None

        logger.info("[lifecycle_service.load] Attempting to load model from: %s", _MODEL_PATH)
        logger.info("[lifecycle_service.load] File exists on disk: %s", _MODEL_PATH.exists())
        logger.info("[lifecycle_service.load] Using joblib: %s", _USE_JOBLIB)

        try:
            if _USE_JOBLIB:
                self._model = _joblib.load(_MODEL_PATH)
                loader = "joblib"
            else:
                with _MODEL_PATH.open("rb") as fh:
                    self._model = pickle.load(fh)  # noqa: S301 — trusted artefact
                loader = "pickle"
            logger.info(
                "[lifecycle_service.load] Model loaded successfully via %s | type=%s",
                loader, type(self._model).__name__,
            )
            self._available = True
        except FileNotFoundError:
            self._load_error = (
                f"Model artefact not found: {_MODEL_PATH}. "
                "Train the model and place lifecycle_model.pkl in backend/weights/. "
                "The /predict-lifecycle endpoint will return HTTP 503 until the model is present."
            )
            logger.warning(
                "[lifecycle_service.load] lifecycle_model.pkl not found at %s — lifecycle predictions disabled.",
                _MODEL_PATH,
            )
        except Exception as exc:  # noqa: BLE001
            self._load_error = (
                f"Failed to load lifecycle model from {_MODEL_PATH}: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.exception(
                "[lifecycle_service.load] Unexpected error loading lifecycle model — "
                "check for version mismatch between training and serving environments. "
                "Error: %s", exc,
            )

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._available

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    # ── Prediction ─────────────────────────────────────────────────────────────

    def predict(
        self,
        Material_Type: int,
        Distance_to_Sea_m: float,
        Humidity_Level: float,
        Maintenance_Cost_Percentage: float,
    ) -> LifecyclePrediction:
        """
        Run a lifecycle degradation prediction.

        Assembles a pandas DataFrame with the exact 4 column names the model
        was trained with (case-sensitive) and calls model.predict().

        Raises
        ──────
        LifecycleModelNotAvailableError  – model not loaded.
        RuntimeError                     – model.predict() raised unexpectedly.
        """
        if not self._available or self._model is None:
            raise LifecycleModelNotAvailableError(
                "Lifecycle degradation model is not loaded. "
                "Place lifecycle_model.pkl in backend/weights/ and restart the server."
            )

        row = {
            "Material_Type":              int(Material_Type),
            "Distance_to_Sea_m":          float(Distance_to_Sea_m),
            "Humidity_Level":             float(Humidity_Level),
            "Maintenance_Cost_Percentage": float(Maintenance_Cost_Percentage),
        }

        # Build DataFrame with exact column names in training order
        X = pd.DataFrame([row], columns=_FEATURE_COLUMNS)

        logger.debug("Lifecycle prediction input DataFrame:\n%s", X.to_string())
        logger.info(
            "Running lifecycle prediction | Material_Type=%d Distance_to_Sea_m=%.1f "
            "Humidity_Level=%.1f Maintenance_Cost_Percentage=%.2f",
            Material_Type, Distance_to_Sea_m, Humidity_Level, Maintenance_Cost_Percentage,
        )

        try:
            raw = self._model.predict(X)
            logger.debug("Raw model output: %s", raw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Model predict() raised unexpectedly: %s", exc)
            raise RuntimeError(f"Model prediction failed: {exc}") from exc

        lifespan_raw: float = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
        lifespan = float(np.clip(lifespan_raw, 1.0, 200.0))

        confidence: Optional[float] = None
        if hasattr(self._model, "predict_proba"):
            try:
                proba = self._model.predict_proba(X)
                confidence = round(float(np.max(proba)), 4)
            except Exception:  # noqa: BLE001
                pass

        risk_level = "Low"
        for threshold, level in _RISK_THRESHOLDS:
            if lifespan < threshold:
                risk_level = level
                break

        logger.info(
            "Lifecycle prediction | Material_Type=%d → %.1f yrs [%s]",
            Material_Type, lifespan, risk_level,
        )

        return LifecyclePrediction(
            estimated_lifespan_years=round(lifespan, 1),
            risk_level=risk_level,
            confidence=confidence,
        )


# ── Module-level singleton (loaded at startup via main.py lifespan) ────────────

lifecycle_service = LifecycleDegradationService()

