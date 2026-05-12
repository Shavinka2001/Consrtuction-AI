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
    "building_type",
    "foundation_type",
    "superstructure_type",
    "roofing_material",
    "plumbing_system",
    "electrical_system",
    "exterior_finish",
    "hvac_system",
    "age",
    "environmental_harshness",
    "soil_acidity",
    "maintenance_interval",
    "material_quality",
]

# ── Label encoding dictionaries for categorical features ───────────────────────
# Keys are the string values sent from the frontend; values are the integer codes
# used during model training.  A missing key falls back to 0 (safe default).

_LABEL_ENCODINGS: dict[str, dict[str, int]] = {
    "building_type": {
        "Residential": 0, "Commercial": 1, "Industrial": 2, "Healthcare": 3,
        "Educational": 4, "Mixed-Use": 5, "Warehouse": 6, "Hotel": 7,
    },
    "foundation_type": {
        "Shallow": 0, "Deep": 1, "Pile": 2, "Raft": 3,
        "Strip": 4, "Pad": 5, "Caisson": 6,
    },
    "superstructure_type": {
        "Concrete_Frame": 0, "Steel_Frame": 1, "Timber_Frame": 2,
        "Masonry": 3, "Composite": 4,
    },
    "roofing_material": {
        "Tiles": 0, "Metal": 1, "Asphalt": 2, "Concrete": 3,
        "Membrane": 4, "Thatch": 5, "Glass": 6,
    },
    "plumbing_system": {
        "Copper": 0, "PVC": 1, "Galvanized_Steel": 2,
        "PEX": 3, "CPVC": 4, "Cast_Iron": 5,
    },
    "electrical_system": {
        "Standard": 0, "High_Capacity": 1, "Solar_Hybrid": 2,
        "Backup_Generator": 3, "Smart_Grid": 4,
    },
    "exterior_finish": {
        "Brick": 0, "Render": 1, "Timber_Cladding": 2, "Metal_Cladding": 3,
        "Glass_Curtain": 4, "Stone": 5, "EIFS": 6,
    },
    "hvac_system": {
        "Central_Air": 0, "Split_System": 1, "Underfloor": 2,
        "Radiant": 3, "Chiller": 4, "None": 5,
    },
}


def _encode(feature: str, value: str) -> int:
    """Safely label-encode a categorical string value.

    Returns the integer code for *value* in *feature*'s dictionary,
    or 0 if the value is not found (prevents NoneType / KeyError errors).
    """
    code = _LABEL_ENCODINGS.get(feature, {}).get(value, None)
    if code is None:
        logger.warning(
            "[lifecycle_service._encode] Unknown value '%s' for feature '%s' — defaulting to 0.",
            value, feature,
        )
        return 0
    return code


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
        building_type: str,
        foundation_type: str,
        superstructure_type: str,
        roofing_material: str,
        plumbing_system: str,
        electrical_system: str,
        exterior_finish: str,
        hvac_system: str,
        age: float,
        environmental_harshness: float,
        soil_acidity: float,
        maintenance_interval: float,
        material_quality: float,
    ) -> LifecyclePrediction:
        """
        Run a lifecycle degradation prediction.

        Categorical string features are label-encoded via ``_LABEL_ENCODINGS``
        before being passed to the model.  Unknown strings default to 0.
        Assembles a pandas DataFrame with the exact 13 column names in training
        order and calls model.predict().

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
            "building_type":          _encode("building_type", building_type),
            "foundation_type":        _encode("foundation_type", foundation_type),
            "superstructure_type":    _encode("superstructure_type", superstructure_type),
            "roofing_material":       _encode("roofing_material", roofing_material),
            "plumbing_system":        _encode("plumbing_system", plumbing_system),
            "electrical_system":      _encode("electrical_system", electrical_system),
            "exterior_finish":        _encode("exterior_finish", exterior_finish),
            "hvac_system":            _encode("hvac_system", hvac_system),
            "age":                    float(age),
            "environmental_harshness": float(environmental_harshness),
            "soil_acidity":           float(soil_acidity),
            "maintenance_interval":   float(maintenance_interval),
            "material_quality":       float(material_quality),
        }

        # Build DataFrame with exact column names in training order
        X = pd.DataFrame([row], columns=_FEATURE_COLUMNS)

        logger.debug("Lifecycle prediction input DataFrame:\n%s", X.to_string())
        logger.info(
            "Running lifecycle prediction | building_type=%s age=%.0f "
            "environmental_harshness=%.1f soil_acidity=%.2f material_quality=%.1f",
            building_type, age, environmental_harshness, soil_acidity, material_quality,
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
            "Lifecycle prediction | building_type=%s age=%.0f → %.1f yrs [%s]",
            building_type, age, lifespan, risk_level,
        )

        return LifecyclePrediction(
            estimated_lifespan_years=round(lifespan, 1),
            risk_level=risk_level,
            confidence=confidence,
        )


# ── Module-level singleton (loaded at startup via main.py lifespan) ────────────

lifecycle_service = LifecycleDegradationService()

