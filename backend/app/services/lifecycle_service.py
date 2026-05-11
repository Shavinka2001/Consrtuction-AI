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

# ── Risk thresholds ────────────────────────────────────────────────────────────
# Derived from predicted lifespan in years. Tune to match your risk appetite.

_RISK_THRESHOLDS: list[tuple[float, str]] = [
    (30.0, "High"),    # lifespan < 30 yrs  → High
    (50.0, "Medium"),  # 30 ≤ lifespan < 50 → Medium
    (200.0, "Low"),    # lifespan ≥ 50      → Low
]

# ── Feature column order (must match training pipeline EXACTLY) ──────────────────

_FEATURE_COLUMNS: list[str] = [
    "building_type",
    "foundation_type",
    "superstructure_type",
    "roofing_material",
    "exterior_finish",
    "hvac_system",
    "plumbing_system",
    "electrical_system",
    "environmental_harshness",
    "soil_acidity",
    "maintenance_frequency",
    "material_quality",
]

# ── Label encoders (must match LabelEncoder.fit order from training) ───────────────
# ⚠  Update these mappings if you retrain with different categories or order.

_LABEL_ENCODERS: dict[str, dict[str, int]] = {
    "building_type": {
        "Residential":   0,
        "Commercial":    1,
        "Industrial":    2,
        "Institutional": 3,
        "Mixed-Use":     4,
    },
    "foundation_type": {
        "Strip":   0,
        "Pad":     1,
        "Raft":    2,
        "Pile":    3,
        "Caisson": 4,
    },
    "superstructure_type": {
        "Timber Frame":        0,
        "Masonry":             1,
        "Reinforced Concrete": 2,
        "Steel Frame":         3,
        "Composite":           4,
    },
    "roofing_material": {
        "Asphalt Shingle": 0,
        "Metal Sheet":     1,
        "Clay Tile":       2,
        "Concrete Tile":   3,
        "Membrane":        4,
    },
    "exterior_finish": {
        "Painted Plaster": 0,
        "EIFS":            1,
        "Exposed Brick":   2,
        "Stone Veneer":    3,
        "Cladding":        4,
    },
    "hvac_system": {
        "None":                0,
        "Natural Ventilation": 1,
        "Split AC":            2,
        "Central AC":          3,
        "VRF":                 4,
    },
    "plumbing_system": {
        "Galvanized Steel": 0,
        "Cast Iron":        1,
        "UPVC":             2,
        "PEX":              3,
        "Copper":           4,
    },
    "electrical_system": {
        "Standard":         0,
        "Overhead":         1,
        "Underground":      2,
        "Solar-Integrated": 3,
        "None":             4,
    },
}


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

        try:
            if _USE_JOBLIB:
                self._model = _joblib.load(_MODEL_PATH)
                loader = "joblib"
            else:
                with _MODEL_PATH.open("rb") as fh:
                    self._model = pickle.load(fh)  # noqa: S301 — trusted artefact
                loader = "pickle"
            logger.info("Lifecycle model loaded via %s from %s", loader, _MODEL_PATH)
            self._available = True
        except FileNotFoundError:
            self._load_error = (
                f"Model artefact not found: {_MODEL_PATH}. "
                "Train the model and place lifecycle_model.pkl in backend/weights/. "
                "The /predict-lifecycle endpoint will return HTTP 503 until the model is present."
            )
            logger.warning(
                "lifecycle_model.pkl not found at %s — lifecycle predictions disabled.",
                _MODEL_PATH,
            )
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"Failed to load lifecycle model: {exc}"
            logger.exception("Unexpected error loading lifecycle model: %s", exc)

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
        exterior_finish: str,
        hvac_system: str,
        plumbing_system: str,
        electrical_system: str,
        environmental_harshness: float,
        soil_acidity: float,
        maintenance_frequency: float,
        material_quality: float,
    ) -> LifecyclePrediction:
        """
        Run a lifecycle degradation prediction.

        Categorical parameters are label-encoded using ``_LABEL_ENCODERS`` and
        assembled into a pandas DataFrame with the exact column names and order
        matching the model's training pipeline (``_FEATURE_COLUMNS``).

        Raises
        ──────
        LifecycleModelNotAvailableError  – model not loaded.
        ValueError                       – unrecognised categorical value.
        RuntimeError                     – model.predict() raised unexpectedly.
        """
        if not self._available or self._model is None:
            raise LifecycleModelNotAvailableError(
                "Lifecycle degradation model is not loaded. "
                "Place lifecycle_model.pkl in backend/weights/ and restart the server."
            )

        # ── Label-encode categorical features ─────────────────────────────────
        def _encode(feature: str, value: str) -> int:
            mapping = _LABEL_ENCODERS.get(feature, {})
            if value not in mapping:
                raise ValueError(
                    f"Unknown value '{value}' for feature '{feature}'. "
                    f"Accepted: {list(mapping.keys())}"
                )
            return mapping[value]

        row = {
            "building_type":       _encode("building_type", building_type),
            "foundation_type":     _encode("foundation_type", foundation_type),
            "superstructure_type": _encode("superstructure_type", superstructure_type),
            "roofing_material":    _encode("roofing_material", roofing_material),
            "exterior_finish":     _encode("exterior_finish", exterior_finish),
            "hvac_system":         _encode("hvac_system", hvac_system),
            "plumbing_system":     _encode("plumbing_system", plumbing_system),
            "electrical_system":   _encode("electrical_system", electrical_system),
            "environmental_harshness": float(environmental_harshness),
            "soil_acidity":            float(soil_acidity),
            "maintenance_frequency":   float(maintenance_frequency),
            "material_quality":        float(material_quality),
        }

        # Build DataFrame with exact column names in training order
        X = pd.DataFrame([row], columns=_FEATURE_COLUMNS)

        try:
            raw = self._model.predict(X)
        except Exception as exc:  # noqa: BLE001
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
            "Lifecycle prediction | %s/%s → %.1f yrs [%s]",
            building_type, superstructure_type, lifespan, risk_level,
        )

        return LifecyclePrediction(
            estimated_lifespan_years=round(lifespan, 1),
            risk_level=risk_level,
            confidence=confidence,
        )


# ── Module-level singleton (loaded at startup via main.py lifespan) ────────────

lifecycle_service = LifecycleDegradationService()

