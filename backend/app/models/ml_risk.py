"""
ML Risk prediction Pydantic schemas.

Separate from ``app/models/risk.py`` (which serves the rule-based compliance
engine) so each module has a single, stable contract.

Request  → MLRiskPredictionRequest
Response → MLRiskPredictionResponse

These are the types used by:
    POST /api/v1/compliance/predict-risk
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations (mirrors frontend types) ─────────────────────────────────────


class ConstructionStageML(str, Enum):
    PRE_CONSTRUCTION    = "PRE_CONSTRUCTION"
    SITE_PREPARATION    = "SITE_PREPARATION"
    EXCAVATION          = "EXCAVATION"
    FOUNDATION_STARTED  = "FOUNDATION_STARTED"
    FOUNDATION_COMPLETE = "FOUNDATION_COMPLETE"
    STRUCTURAL_FRAMING  = "STRUCTURAL_FRAMING"
    ROUGH_MEP_INSTALL   = "ROUGH_MEP_INSTALL"
    ROOFING             = "ROOFING"
    EXTERNAL_ENVELOPE   = "EXTERNAL_ENVELOPE"
    FINISHING           = "FINISHING"
    FINAL_INSPECTIONS   = "FINAL_INSPECTIONS"
    OCCUPANCY_READY     = "OCCUPANCY_READY"
    COMPLETE            = "COMPLETE"


class ApprovalStatusML(str, Enum):
    NOT_STARTED        = "NOT_STARTED"
    DOCUMENT_GATHERING = "DOCUMENT_GATHERING"
    SUBMITTED          = "SUBMITTED"
    UNDER_REVIEW       = "UNDER_REVIEW"
    APPROVED           = "APPROVED"
    REJECTED           = "REJECTED"


class ZoningTypeML(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL  = "COMMERCIAL"
    INDUSTRIAL  = "INDUSTRIAL"
    MIXED_USE   = "MIXED_USE"


class RiskLevelML(str, Enum):
    """
    Risk levels returned by the ML model (and the rule-based fallback).

    Must match the labels the label_encoder.pkl was fitted on.
    """
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# ── Request schema ────────────────────────────────────────────────────────────


class MLRiskPredictionRequest(BaseModel):
    """
    POST body for ``/api/v1/compliance/predict-risk``.

    Frontend binding
    ────────────────
    Collect these values from the BuildingParams form and the Live Progress
    stepper in ComplianceRoadmap.tsx, then POST to the endpoint.

    Example::

        {
          "current_construction_stage": "FOUNDATION_STARTED",
          "current_approval_status":    "UNDER_REVIEW",
          "zoning_type":                "COMMERCIAL",
          "estimated_project_value_lkr": 45000000,
          "project_id":                 "proj-abc-123"
        }
    """

    current_construction_stage: ConstructionStageML = Field(
        description="The most advanced physical work stage currently active on site."
    )
    current_approval_status: ApprovalStatusML = Field(
        description=(
            "Workflow status of the primary permit (typically UDA Development "
            "Permission) for this project."
        )
    )
    zoning_type: ZoningTypeML = Field(
        description="Land-use classification of the project site."
    )
    estimated_project_value_lkr: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Estimated total construction cost in Sri Lankan Rupees (LKR). "
            "Used to calculate percentage-based penalty exposure. "
            "Supply 0 or omit for flat-fee penalty calculation."
        ),
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Optional project reference. Stored in the response for traceability.",
    )

    @field_validator("estimated_project_value_lkr", mode="before")
    @classmethod
    def coerce_project_value(cls, v: object) -> float:
        """Accept None / empty string → 0.0 so the field is always numeric."""
        if v is None or v == "":
            return 0.0
        return float(v)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "current_construction_stage": "FOUNDATION_STARTED",
                    "current_approval_status":    "UNDER_REVIEW",
                    "zoning_type":                "COMMERCIAL",
                    "estimated_project_value_lkr": 45_000_000,
                    "project_id":                 "proj-commercial-blk-a",
                },
                {
                    "current_construction_stage": "PRE_CONSTRUCTION",
                    "current_approval_status":    "APPROVED",
                    "zoning_type":                "RESIDENTIAL",
                    "estimated_project_value_lkr": 8_000_000,
                },
            ]
        }
    }


# ── Response schema ───────────────────────────────────────────────────────────


class MLRiskPredictionResponse(BaseModel):
    """
    JSON response returned by ``/api/v1/compliance/predict-risk``.

    Frontend binding (RiskAlertBanner)
    ────────────────────────────────────
    Map this to a ``RiskAlert`` in ComplianceRoadmap.tsx::

        const alert: RiskAlert = {
          id:              response.request_id,
          severity:        response.risk_level as AlertSeverity,
          title:           "ML Risk Assessment",
          message:         response.legal_warning_message,
          penaltyLkr:      response.potential_penalty_lkr,
          stopWork:        response.risk_level === "CRITICAL",
        };
    """

    # ── Core prediction fields ─────────────────────────────────────────────────

    risk_level: RiskLevelML = Field(
        description="Predicted risk classification (LOW / MEDIUM / HIGH / CRITICAL)."
    )
    deviation_detected: bool = Field(
        description=(
            "True when the construction stage has advanced beyond what the current "
            "approval status legally permits. Mirrors the hard-blocker flag used by "
            "the scheduling and cost microservices."
        )
    )
    legal_warning_message: str = Field(
        description="Plain-English compliance warning ready for display in the UI."
    )
    potential_penalty_lkr: float = Field(
        description=(
            "Estimated financial exposure in LKR. Percentage-based when "
            "estimated_project_value_lkr > 0, otherwise a regulatory flat fee."
        )
    )

    # ── Contextual / diagnostic fields ────────────────────────────────────────

    construction_stage: str = Field(
        description="Echo of the input construction stage."
    )
    approval_status: str = Field(
        description="Echo of the input approval status."
    )
    penalty_basis: str = Field(
        description="'PERCENTAGE_BASED' or 'FLAT_FEE' — indicates how the penalty was computed."
    )
    penalty_rate_applied: str = Field(
        description="Human-readable rate used (e.g. '10% of project value' or 'LKR 1,000,000 flat fee')."
    )
    ml_model_used: bool = Field(
        description="True when the prediction came from the sklearn model; False for rule-based fallback."
    )
    model_confidence: Optional[float] = Field(
        default=None,
        description="Predicted class probability (0.0–1.0) when the model supports predict_proba. Null for rule-based fallback.",
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Echo of the project_id supplied in the request, if any.",
    )
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the analysis.",
    )

    model_config = {"json_schema_extra": {}}
