"""
Risk analysis domain models – Pydantic v2.

Covers the full data contract for the Proactive Risk Mitigation module.

Key concepts
────────────
ConstructionStage   – Ordered stages of physical site work.
ViolationSeverity   – LOW / MEDIUM / HIGH / CRITICAL — drives penalty tier.
DetectedDeviation   – One per unapproved-yet-required permit at the current stage.
FinancialPenalty    – Computed penalty (percentage or flat fee) for a deviation.
LegalWarning        – Structured statutory reference + corrective action.
RiskAnalysisRequest – POST body; accepts either a live project_id OR inline
                      permit statuses for ad-hoc what-if analysis.
RiskAnalysisResponse – Full report returned to the caller; stable contract for
                       downstream services (cost, scheduling, insurance modules).

NLP injection point
───────────────────
When a real NLP document-understanding service is wired in, it populates
RiskAnalysisResponse.nlp_insights with extracted scope deviations. Until then
the field is an empty list.  See app/services/risk_analyzer.py for the
DocumentAnalysisProtocol definition.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.compliance import PermitType, WorkflowStatus


# ── Construction stage enumeration ─────────────────────────────────────────────


class ConstructionStage(str, Enum):
    """
    Ordered milestones of physical site work.

    The ordering encoded in STAGE_ORDER (see risk_analyzer.py) determines
    whether a project has 'advanced ahead of approvals'.
    """

    PRE_CONSTRUCTION = "PRE_CONSTRUCTION"
    SITE_PREPARATION = "SITE_PREPARATION"
    EXCAVATION = "EXCAVATION"
    FOUNDATION_STARTED = "FOUNDATION_STARTED"
    FOUNDATION_COMPLETE = "FOUNDATION_COMPLETE"
    STRUCTURAL_FRAMING = "STRUCTURAL_FRAMING"
    ROUGH_MEP_INSTALL = "ROUGH_MEP_INSTALL"
    ROOFING = "ROOFING"
    EXTERNAL_ENVELOPE = "EXTERNAL_ENVELOPE"
    FINISHING = "FINISHING"
    FINAL_INSPECTIONS = "FINAL_INSPECTIONS"
    OCCUPANCY_READY = "OCCUPANCY_READY"
    COMPLETE = "COMPLETE"


# ── Violation severity ──────────────────────────────────────────────────────────


class ViolationSeverity(str, Enum):
    """
    Severity tier for a detected compliance deviation.

    Drives both the financial penalty tier and the urgency of legal warnings.

    Rank (lowest → highest): LOW → MEDIUM → HIGH → CRITICAL
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ── Inline permit input (ad-hoc / what-if analysis) ───────────────────────────


class PermitStatusInput(BaseModel):
    """
    Minimal permit snapshot for ad-hoc risk analysis.

    Used when the caller provides permit data inline rather than referencing
    a live project_id stored in the database.
    """

    permit_type: PermitType
    status: WorkflowStatus


# ── Financial penalty breakdown ─────────────────────────────────────────────────


class FinancialPenalty(BaseModel):
    """
    Estimated financial exposure for a single permit deviation.

    ``penalty_usd`` is either percentage-based (when project value is known)
    or a regulatory flat fee.  ``daily_accrual_usd`` represents the ongoing
    cost for every day the violation is unresolved — used by scheduling and
    cost microservices to calculate total exposure over time.
    """

    basis: str = Field(
        description="'PERCENTAGE_BASED' when project value supplied, else 'FLAT_FEE'"
    )
    estimated_penalty_usd: float = Field(
        description="One-time penalty at point of detection"
    )
    daily_accrual_usd: float = Field(
        description="Ongoing daily penalty until the violation is resolved"
    )
    calculation_note: str = Field(
        description="Human-readable explanation of how the figure was derived"
    )


# ── Legal warning ───────────────────────────────────────────────────────────────


class LegalWarning(BaseModel):
    """
    Structured statutory reference for a compliance violation.

    ``statute_reference`` points to a real regulatory code section for
    traceability.  ``corrective_action`` and ``stop_work_required`` give the
    site engineer clear next steps.
    """

    warning_code: str = Field(
        description="Internal code, e.g. 'BLDG-001', used for de-duplication"
    )
    statute_reference: str = Field(
        description="Applicable building code / regulation section"
    )
    message: str = Field(description="Plain-English description of the legal risk")
    corrective_action: str = Field(
        description="Specific action required to remediate this violation"
    )
    stop_work_required: bool = Field(
        description="True when a stop-work order is legally mandated at this severity"
    )


# ── Single detected deviation ───────────────────────────────────────────────────


class DetectedDeviation(BaseModel):
    """
    One violation: a required permit that is not yet APPROVED at the current
    construction stage.

    Carries both the financial penalty and all applicable legal warnings so
    downstream services can act on each deviation independently.
    """

    permit_type: PermitType
    permit_status: WorkflowStatus
    construction_stage: ConstructionStage
    severity: ViolationSeverity
    description: str = Field(
        description="Narrative description of why this is a violation"
    )
    financial_penalty: FinancialPenalty
    legal_warnings: list[LegalWarning]


# ── Request / response schemas ──────────────────────────────────────────────────


class RiskAnalysisRequest(BaseModel):
    """
    POST /api/v1/compliance/analyze-risk – request body.

    Two operating modes:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ LIVE MODE   │ Provide project_id (no permits field needed).             │
    │             │ The service fetches current permit statuses from the DB.  │
    ├─────────────────────────────────────────────────────────────────────────┤
    │ AD-HOC MODE │ Omit project_id; provide permits list directly.           │
    │             │ Useful for what-if / pre-submission analysis.             │
    └─────────────────────────────────────────────────────────────────────────┘
    If both project_id and permits are supplied, the inline permits take
    precedence — enabling overrides and scenario modelling without touching
    the stored record.
    """

    project_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Live project ID — fetches permit statuses from the database",
    )
    construction_stage: ConstructionStage = Field(
        description="The current physical construction milestone"
    )
    permits: list[PermitStatusInput] | None = Field(
        default=None,
        description=(
            "Inline permit statuses for ad-hoc analysis. "
            "Required when project_id is not provided."
        ),
    )
    estimated_project_value_usd: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Total estimated project value in USD. "
            "When supplied, penalties are percentage-based; otherwise flat fees apply."
        ),
    )

    @model_validator(mode="after")
    def _require_at_least_one_source(self) -> "RiskAnalysisRequest":
        if self.project_id is None and (self.permits is None or len(self.permits) == 0):
            raise ValueError(
                "Provide either 'project_id' (to load from database) or "
                "'permits' (for ad-hoc analysis)."
            )
        return self


class RiskAnalysisResponse(BaseModel):
    """
    POST /api/v1/compliance/analyze-risk – response body.

    Designed as a stable inter-service contract:
    - ``has_violations`` is the quick boolean gate.
    - ``overall_severity`` is the worst single severity across all deviations.
    - ``total_estimated_penalty_usd`` aggregates one-time penalties.
    - ``total_daily_accrual_usd`` enables cost services to project exposure.
    - ``nlp_insights`` is reserved for future NLP document analysis results.

    Other microservices (scheduling, cost estimation, insurance) should treat
    ``has_violations = True`` as a hard blocker until all deviations are resolved.
    """

    project_id: str | None
    construction_stage: ConstructionStage
    has_violations: bool
    overall_severity: ViolationSeverity | None = Field(
        description="Worst severity found; null when has_violations is False"
    )
    violation_count: int
    total_estimated_penalty_usd: float = Field(
        description="Sum of all one-time penalty estimates across deviations"
    )
    total_daily_accrual_usd: float = Field(
        description="Sum of daily accrual rates — multiply by delay days for exposure"
    )
    deviations: list[DetectedDeviation]
    compliance_recommendations: list[str] = Field(
        description="Ordered list of prioritised corrective actions"
    )
    nlp_insights: list[str] = Field(
        default_factory=list,
        description=(
            "Populated when an NLP document analyzer is injected. "
            "Contains scope-deviation insights extracted from permit documents."
        ),
    )
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
