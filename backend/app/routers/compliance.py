"""
Compliance router – permit-approval workflow endpoints.

Prefix : /api/v1/compliance
Tag    : Compliance

Endpoints
─────────
GET  /api/v1/compliance/{project_id}/status
    Returns the full permit-workflow status for a project.
    Consumed by the frontend dashboard and by downstream microservices
    (scheduling / cost estimation) to gate their own workflows.

PATCH /api/v1/compliance/{project_id}/update-step
    Advances (or reverts after rejection) a single permit's workflow state.
    Enforces the state machine — invalid transitions are rejected with 422.

POST  /api/v1/compliance/{project_id}/init
    Bootstrap a new compliance record for a project.
    Idempotent guard: returns 409 if the record already exists.

All endpoints require a valid JWT Bearer token.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import get_database
from app.dependencies.auth import require_auth
from app.models.compliance import (
    PermitType,
    ProjectComplianceResponse,
    UpdateStepRequest,
    UpdateStepResponse,
)
from app.models.risk import (
    RiskAnalysisRequest,
    RiskAnalysisResponse,
)
from app.models.ml_risk import (
    MLRiskPredictionRequest,
    MLRiskPredictionResponse,
    RiskLevelML,
)
from app.services.compliance_service import (
    ComplianceService,
    InvalidTransitionError,
    PermitNotFoundError,
    ProjectNotFoundError,
)
from app.services.risk_analyzer import (
    ComplianceRiskAnalyzer,
    NLPDocumentAnalyzerStub,
    default_analyzer,
)
from app.services.ml_risk_service import (
    UDARiskMLService,
    ModelNotAvailableError,
    get_ml_risk_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/compliance", tags=["Compliance"])

# ── Dependency factories ────────────────────────────────────────────────────────


def _get_service(
    db: Annotated[AsyncIOMotorDatabase, Depends(get_database)],  # type: ignore[type-arg]
) -> ComplianceService:
    return ComplianceService(db)


def _get_risk_analyzer() -> ComplianceRiskAnalyzer:
    """
    FastAPI dependency for ComplianceRiskAnalyzer.

    Returns the module-level default instance (stub NLP).  Override this
    dependency in tests or when a real NLP service is available::

        app.dependency_overrides[_get_risk_analyzer] = lambda: ComplianceRiskAnalyzer(
            document_analyzer=MyNLPAnalyzer()
        )
    """
    return default_analyzer


# ── POST /api/v1/compliance/analyze-risk ───────────────────────────────────────
# Declared BEFORE /{project_id}/... routes so the static path segment
# 'analyze-risk' is matched first and never treated as a project_id value.


@router.post(
    "/analyze-risk",
    response_model=RiskAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Proactive risk analysis for permit compliance deviations",
    description=(
        "Evaluates whether the current construction stage has advanced beyond "
        "what is legally permitted given the project's permit approval statuses.\n\n"
        "**Deviation detection**: for every permit type required at the supplied "
        "construction stage, the engine checks that the permit is in `APPROVED` state. "
        "Any non-approved required permit constitutes a violation.\n\n"
        "**Two operating modes**:\n"
        "- **Live mode** – supply `project_id`; permit statuses are fetched from the "
        "database automatically.\n"
        "- **Ad-hoc mode** – omit `project_id` and supply an inline `permits` list for "
        "what-if / pre-submission scenario analysis.\n\n"
        "If both fields are provided, the inline `permits` list takes precedence.\n\n"
        "**Microservice contract**: `has_violations: true` is the hard blocker that "
        "scheduling and cost services must respect before proceeding."
    ),
)
async def analyze_risk(
    body: Annotated[RiskAnalysisRequest, Body()],
    _payload: Annotated[dict, Depends(require_auth)],
    analyzer: Annotated[ComplianceRiskAnalyzer, Depends(_get_risk_analyzer)],
    service: Annotated[ComplianceService, Depends(_get_service)],
) -> RiskAnalysisResponse:
    from app.models.risk import PermitStatusInput  # local to avoid circular at module level

    # ── Resolve permit statuses ────────────────────────────────────────────────
    # Inline permits take precedence over live DB lookup.
    if body.permits is not None and len(body.permits) > 0:
        resolved_permits = body.permits
    elif body.project_id is not None:
        # Fetch live permit statuses from the database.
        try:
            project_status = await service.get_project_status(body.project_id)
        except ProjectNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No compliance record found for project '{body.project_id}'. "
                    "Create one via POST /{project_id}/init, or supply inline 'permits'."
                ),
            )
        resolved_permits = [
            PermitStatusInput(
                permit_type=p.permit_type,
                status=p.status,
            )
            for p in project_status.permits
        ]
    else:
        # model_validator on RiskAnalysisRequest already guards this branch,
        # but defend here too for safety.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either 'project_id' or 'permits'.",
        )

    # ── Run analysis ───────────────────────────────────────────────────────────
    result = analyzer.analyze(
        construction_stage=body.construction_stage,
        permits=resolved_permits,
        project_id=body.project_id,
        estimated_project_value_usd=body.estimated_project_value_usd,
    )

    logger.info(
        "Risk analysis complete | project=%s stage=%s violations=%d severity=%s",
        body.project_id or "ad-hoc",
        body.construction_stage.value,
        result.violation_count,
        result.overall_severity.value if result.overall_severity else "NONE",
    )
    return result


# ── POST /api/v1/compliance/predict-risk (ML) ──────────────────────────────────
# ML-backed risk prediction using uda_risk_model.pkl + label_encoder.pkl.
# Falls back to a deterministic rule-based response when the .pkl files are
# absent, so the endpoint is always callable in development.
#
# Declared BEFORE /{project_id}/... routes to avoid routing collision.

# ── Penalty configuration (LKR) ───────────────────────────────────────────────
# Penalty rates and flat-fee floors per risk level.
# Adjust to match the latest Sri Lankan regulatory schedule.

_PENALTY_CONFIG: dict[str, dict] = {
    "LOW": {
        "rate":          0.01,          # 1 % of project value
        "flat_fee_lkr":  50_000,        # floor when value unknown
        "rate_label":    "1% of project value",
        "flat_label":    "LKR 50,000 flat fee",
    },
    "MEDIUM": {
        "rate":          0.05,
        "flat_fee_lkr":  250_000,
        "rate_label":    "5% of project value",
        "flat_label":    "LKR 250,000 flat fee",
    },
    "HIGH": {
        "rate":          0.10,
        "flat_fee_lkr":  1_000_000,
        "rate_label":    "10% of project value",
        "flat_label":    "LKR 1,000,000 flat fee",
    },
    "CRITICAL": {
        "rate":          0.20,
        "flat_fee_lkr":  5_000_000,
        "rate_label":    "20% of project value",
        "flat_label":    "LKR 5,000,000 flat fee",
    },
}

# ── Legal warning messages keyed by (risk_level, construction_stage) ──────────
# Any stage not explicitly listed falls back to the risk_level generic message.

_WARNING_MESSAGES: dict[str, str] = {
    # Generic per-level (key = risk level only)
    "LOW":      "Minor compliance gap detected. Ensure all pending documents are submitted before advancing to the next construction phase.",
    "MEDIUM":   "Moderate compliance risk identified. Permit applications must be progressed urgently. Continued site activity without the required approvals may attract regulatory scrutiny.",
    "HIGH":     "Significant compliance violation detected. Current construction activity has advanced beyond what is legally permitted by the outstanding permit status. Immediate corrective action is required to avoid financial penalties and potential stop-work orders.",
    "CRITICAL": "Critical compliance breach. Site activity must cease immediately. One or more critical permits are not approved and construction has materially advanced beyond the legally permitted stage. Stop-Work Order may be imminent. Engage a compliance solicitor urgently.",
    # Specific overrides — key = "RISK_LEVEL|STAGE"
    "HIGH|FOUNDATION_STARTED":    "Warning: Foundation work has commenced without UDA Development Permission being granted. This is a direct violation of UDA Law No. 41 of 1978, Section 14. Potential fine: up to LKR 1,000,000 plus daily accrual.",
    "CRITICAL|FOUNDATION_STARTED": "Stop-Work Required: Foundation activity is underway while critical permits remain unapproved. UDA and Local Authority stop-work powers are invoked. Halt all site operations immediately.",
    "HIGH|STRUCTURAL_FRAMING":    "Warning: Structural framing has commenced while permit approvals are outstanding. Building Regulations 1986, Section 23 requires approved plans before structural works begin.",
    "HIGH|EXCAVATION":            "Warning: Excavation works have started without the required permit approvals. Cease operations and submit pending permit applications immediately.",
    "CRITICAL|STRUCTURAL_FRAMING": "Stop-Work Required: Structural works are advancing without approved permits. Immediate cessation of all site operations is mandatory under Building Regulations 1986.",
}


def _resolve_warning(risk_level: str, stage: str) -> str:
    """Return the most specific warning message for the given level + stage combo."""
    return _WARNING_MESSAGES.get(
        f"{risk_level}|{stage}",
        _WARNING_MESSAGES.get(risk_level, "Compliance review required."),
    )


def _calc_penalty(risk_level: str, project_value_lkr: float) -> tuple[float, str, str]:
    """
    Calculate penalty in LKR.

    Returns (penalty_lkr, basis, rate_label).
    """
    cfg = _PENALTY_CONFIG.get(risk_level, _PENALTY_CONFIG["MEDIUM"])
    if project_value_lkr > 0:
        penalty = project_value_lkr * cfg["rate"]
        return penalty, "PERCENTAGE_BASED", cfg["rate_label"]
    return float(cfg["flat_fee_lkr"]), "FLAT_FEE", cfg["flat_label"]


def _is_deviation(approval_status: str, construction_stage: str) -> bool:
    """
    Rule-based deviation flag: True when physical work has advanced beyond
    what the approval status legally permits.

    The status must be APPROVED for any work past SITE_PREPARATION to be
    considered compliant.  SUBMITTED / UNDER_REVIEW are non-compliant for
    stage >= EXCAVATION.
    """
    safe_statuses = {"APPROVED"}
    # NOT_STARTED / DOCUMENT_GATHERING = non-compliant for ANY physical work
    physical_stages = {
        "EXCAVATION", "FOUNDATION_STARTED", "FOUNDATION_COMPLETE",
        "STRUCTURAL_FRAMING", "ROUGH_MEP_INSTALL", "ROOFING",
        "EXTERNAL_ENVELOPE", "FINISHING", "FINAL_INSPECTIONS",
        "OCCUPANCY_READY", "COMPLETE",
    }
    if construction_stage in physical_stages and approval_status not in safe_statuses:
        return True
    return False


def _rule_based_risk(approval_status: str, construction_stage: str) -> str:
    """
    Deterministic fallback when the ML model is unavailable.

    Mirrors the severity escalation logic in ComplianceRiskAnalyzer but
    operates on the single primary permit status rather than the full set.
    """
    physical_stages = {
        "EXCAVATION": 2, "FOUNDATION_STARTED": 3, "FOUNDATION_COMPLETE": 4,
        "STRUCTURAL_FRAMING": 5, "ROUGH_MEP_INSTALL": 6, "ROOFING": 7,
        "EXTERNAL_ENVELOPE": 8, "FINISHING": 9, "FINAL_INSPECTIONS": 10,
        "OCCUPANCY_READY": 11, "COMPLETE": 12,
    }
    stage_rank = physical_stages.get(construction_stage, 0)

    if approval_status == "APPROVED":
        return "LOW" if stage_rank < 5 else "LOW"
    if approval_status == "REJECTED":
        return "CRITICAL" if stage_rank >= 3 else "HIGH"
    if approval_status in ("NOT_STARTED", "DOCUMENT_GATHERING"):
        return "CRITICAL" if stage_rank >= 3 else "MEDIUM"
    # SUBMITTED / UNDER_REVIEW
    return "HIGH" if stage_rank >= 3 else "MEDIUM"


@router.post(
    "/predict-risk",
    response_model=MLRiskPredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="ML-powered risk prediction for a construction project state",
    description=(
        "Predicts the legal and financial risk level of a project using the trained "
        "``uda_risk_model.pkl`` scikit-learn estimator.\n\n"
        "**Input**: current construction stage, primary approval status, zoning "
        "classification, and estimated project value.\n\n"
        "**Output**: risk level (LOW / MEDIUM / HIGH / CRITICAL), deviation flag, "
        "legal warning message, and estimated penalty in LKR.\n\n"
        "**Fallback**: when the ``.pkl`` model files are absent, the endpoint returns "
        "a deterministic rule-based prediction instead of failing, and sets "
        "``ml_model_used: false`` in the response so the caller can distinguish "
        "between ML and rule-based outputs.\n\n"
        "Distinct from ``/analyze-risk`` (which checks every permit against the full "
        "stage-prerequisite table). This endpoint provides a single-score prediction "
        "suitable for real-time dashboard display."
    ),
)
async def predict_risk(
    body: Annotated[MLRiskPredictionRequest, Body()],
    _payload: Annotated[dict, Depends(require_auth)],
    ml_service: Annotated[UDARiskMLService, Depends(get_ml_risk_service)],
) -> MLRiskPredictionResponse:
    stage  = body.current_construction_stage.value
    status_ = body.current_approval_status.value
    zoning = body.zoning_type.value
    value  = body.estimated_project_value_lkr

    ml_model_used   = False
    model_confidence: float | None = None
    risk_level: str

    # ── 1. Attempt ML prediction ───────────────────────────────────────────────
    if ml_service.available:
        try:
            result = ml_service.predict(
                construction_stage=stage,
                approval_status=status_,
                zoning_type=zoning,
                project_value_lkr=value,
            )
            risk_level       = result.risk_level
            model_confidence = result.confidence
            ml_model_used    = True
            logger.info(
                "ML prediction | project=%s stage=%s status=%s risk=%s conf=%s",
                body.project_id or "ad-hoc",
                stage,
                status_,
                risk_level,
                model_confidence,
            )
        except ValueError as exc:
            # Unknown categorical value — surface as 422
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        except ModelNotAvailableError:
            # Race condition: service became unavailable between check and predict
            logger.warning("ML service became unavailable mid-request; using fallback.")
            risk_level = _rule_based_risk(status_, stage)
    else:
        # ── 2. Rule-based fallback ─────────────────────────────────────────────
        logger.info(
            "ML model not available — rule-based fallback | project=%s stage=%s status=%s",
            body.project_id or "ad-hoc",
            stage,
            status_,
        )
        risk_level = _rule_based_risk(status_, stage)

    # Normalise risk_level to one of our known values
    if risk_level not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        logger.warning("Unexpected risk_level '%s' from model; defaulting to HIGH.", risk_level)
        risk_level = "HIGH"

    # ── 3. Compute penalty and deviation flag ──────────────────────────────────
    deviation_detected                        = _is_deviation(status_, stage)
    penalty_lkr, basis, rate_label            = _calc_penalty(risk_level, value)
    warning_msg                               = _resolve_warning(risk_level, stage)

    logger.info(
        "predict-risk | project=%s risk=%s deviation=%s penalty_lkr=%.0f ml=%s",
        body.project_id or "ad-hoc",
        risk_level,
        deviation_detected,
        penalty_lkr,
        ml_model_used,
    )

    return MLRiskPredictionResponse(
        risk_level=RiskLevelML(risk_level),
        deviation_detected=deviation_detected,
        legal_warning_message=warning_msg,
        potential_penalty_lkr=round(penalty_lkr, 2),
        construction_stage=stage,
        approval_status=status_,
        penalty_basis=basis,
        penalty_rate_applied=rate_label,
        ml_model_used=ml_model_used,
        model_confidence=model_confidence,
        project_id=body.project_id,
    )


@router.get(
    "/{project_id}/status",
    response_model=ProjectComplianceResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch permit-workflow status for a project",
    description=(
        "Returns the current compliance workflow for every permit application "
        "linked to *project_id*, including audit history, assigned officers, "
        "and computed progress metrics.  \n\n"
        "**Microservice contract** – other services (scheduling, cost estimation) "
        "should poll or subscribe to this endpoint to gate their own workflows "
        "on `all_permits_resolved: true`."
    ),
)
async def get_compliance_status(
    project_id: Annotated[
        str,
        Path(
            description="Unique project identifier",
            min_length=1,
            max_length=128,
        ),
    ],
    _payload: Annotated[dict, Depends(require_auth)],
    service: Annotated[ComplianceService, Depends(_get_service)],
) -> ProjectComplianceResponse:
    try:
        return await service.get_project_status(project_id)
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No compliance record found for project '{project_id}'. "
                   "Use POST /init to create one.",
        )


# ── PATCH /api/v1/compliance/{project_id}/update-step ─────────────────────────


@router.patch(
    "/{project_id}/update-step",
    response_model=UpdateStepResponse,
    status_code=status.HTTP_200_OK,
    summary="Advance or revert a permit's workflow state",
    description=(
        "Applies a state-machine transition to the specified permit within "
        "the project's compliance record. Every change is recorded as an "
        "immutable `WorkflowTransition` in the permit's `history` array.\n\n"
        "**Valid transition paths:**\n"
        "```\n"
        "NOT_STARTED → DOCUMENT_GATHERING\n"
        "DOCUMENT_GATHERING → SUBMITTED\n"
        "SUBMITTED → UNDER_REVIEW\n"
        "UNDER_REVIEW → APPROVED | REJECTED\n"
        "REJECTED → DOCUMENT_GATHERING  (re-submission)\n"
        "```\n"
        "Attempting an illegal transition returns **422 Unprocessable Entity**."
    ),
)
async def update_compliance_step(
    project_id: Annotated[
        str,
        Path(description="Unique project identifier", min_length=1, max_length=128),
    ],
    request: Annotated[UpdateStepRequest, Body()],
    _payload: Annotated[dict, Depends(require_auth)],
    service: Annotated[ComplianceService, Depends(_get_service)],
) -> UpdateStepResponse:
    try:
        return await service.update_permit_step(project_id, request)

    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No compliance record found for project '{project_id}'.",
        )
    except PermitNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permit '{exc}' not found within project '{project_id}'.",
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": str(exc),
                "current_status": exc.current.value,
                "requested_status": exc.requested.value,
                "valid_next_statuses": [s.value for s in exc.valid_next],
            },
        )


# ── POST /api/v1/compliance/{project_id}/init ──────────────────────────────────


class InitComplianceRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255)
    permit_types: list[PermitType] = Field(
        ...,
        min_length=1,
        description="List of permit types to track for this project",
    )


@router.post(
    "/{project_id}/init",
    response_model=ProjectComplianceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bootstrap a new compliance record",
    description=(
        "Creates the compliance workflow document for a project and pre-populates "
        "one `PermitApplication` (in **NOT_STARTED** state) for each permit type "
        "supplied in the request body.  \n\n"
        "Returns **409 Conflict** if a record already exists for this project."
    ),
)
async def init_compliance(
    project_id: Annotated[
        str,
        Path(description="Unique project identifier", min_length=1, max_length=128),
    ],
    body: Annotated[InitComplianceRequest, Body()],
    _payload: Annotated[dict, Depends(require_auth)],
    service: Annotated[ComplianceService, Depends(_get_service)],
) -> ProjectComplianceResponse:
    try:
        return await service.create_project_compliance(
            project_id=project_id,
            project_name=body.project_name,
            permit_types=body.permit_types,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
