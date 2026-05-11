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
        material_quality: int,
        environmental_harshness: int,
        soil_acidity: float,
        maintenance_frequency: int,
    ) -> LifecyclePrediction:
        """
        Run a lifecycle degradation prediction.

        Parameters
        ──────────
        material_quality        – int  1 (very poor) to 10 (excellent)
        environmental_harshness – int  1 (mild) to 10 (extreme/coastal)
        soil_acidity            – float  pH value, typically 3.0 – 9.0
        maintenance_frequency   – int  months between maintenance visits
                                       (1 = monthly, 12 = annually)

        Returns
        ───────
        LifecyclePrediction namedtuple with estimated lifespan, risk level,
        and optional confidence score.

        Raises
        ──────
        LifecycleModelNotAvailableError – model not loaded.
        RuntimeError                    – model.predict() failed unexpectedly.
        """
        if not self._available or self._model is None:
            raise LifecycleModelNotAvailableError(
                "Lifecycle degradation model is not loaded. "
                "Place lifecycle_model.pkl in backend/weights/ and restart the server."
            )

        # Build 2-D feature array [[mq, eh, sa, mf]]
        X = np.array(
            [[
                float(material_quality),
                float(environmental_harshness),
                float(soil_acidity),
                float(maintenance_frequency),
            ]],
            dtype=np.float64,
        )

        try:
            raw = self._model.predict(X)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Model prediction failed: {exc}") from exc

        lifespan_raw: float = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
        # Clip to a physically plausible range (1 – 200 years)
        lifespan = float(np.clip(lifespan_raw, 1.0, 200.0))

        # Confidence score (classifiers only)
        confidence: Optional[float] = None
        if hasattr(self._model, "predict_proba"):
            try:
                proba = self._model.predict_proba(X)
                confidence = round(float(np.max(proba)), 4)
            except Exception:  # noqa: BLE001
                pass  # confidence stays None for pure regression models

        # Derive risk level from predicted lifespan
        risk_level = "Low"
        for threshold, level in _RISK_THRESHOLDS:
            if lifespan < threshold:
                risk_level = level
                break

        logger.info(
            "Lifecycle prediction | mq=%s eh=%s sa=%s mf=%s → %.1f yrs [%s]",
            material_quality, environmental_harshness, soil_acidity, maintenance_frequency,
            lifespan, risk_level,
        )

        return LifecyclePrediction(
            estimated_lifespan_years=round(lifespan, 1),
            risk_level=risk_level,
            confidence=confidence,
        )


# ── Module-level singleton (loaded at startup via main.py lifespan) ────────────

lifecycle_service = LifecycleDegradationService()

