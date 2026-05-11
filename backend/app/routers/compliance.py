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


# ── POST /api/v1/compliance/roadmap ───────────────────────────────────────────
# Declared BEFORE /{project_id}/... routes so the static segment 'roadmap'
# is never mistaken for a project_id value.
# ─────────────────────────────────────────────────────────────────────────────


class RoadmapBuildingParams(BaseModel):
    floor_area: float = Field(..., gt=0, description="Total floor area in m²")
    stories: int = Field(..., ge=1, le=200, description="Number of stories")
    zoning_type: str = Field(
        ...,
        pattern="^(RESIDENTIAL|COMMERCIAL|INDUSTRIAL|MIXED_USE)$",
        description="Zoning classification",
    )
    construction_type: str = Field(
        ...,
        pattern="^(NEW_CONSTRUCTION|EXTENSION|RENOVATION|DEMOLITION)$",
        description="Construction type",
    )
    project_value_lkr: float | None = Field(
        None, ge=0, description="Estimated project value in LKR (optional)"
    )


class RoadmapPermitItem(BaseModel):
    id: str
    name: str
    authority: str
    icon_key: str
    estimated_fee_lkr: float
    min_days: int
    max_days: int
    mandatory: bool
    risk_level: str
    description: str
    required_documents: list[str]
    legal_reference: str
    phase: int


class RoadmapRiskAlert(BaseModel):
    id: str
    severity: str
    title: str
    message: str
    penalty_lkr: float | None = None
    daily_accrual_lkr: float | None = None
    stop_work: bool = False
    statute: str | None = None
    corrective_action: str | None = None


class RoadmapSummary(BaseModel):
    total_permits: int
    mandatory_count: int
    estimated_total_fee_lkr: float
    max_timeline_days: int
    high_risk_count: int


class RoadmapResponse(BaseModel):
    permits: list[RoadmapPermitItem]
    risk_alerts: list[RoadmapRiskAlert]
    summary: RoadmapSummary


# ── Fee helpers ────────────────────────────────────────────────────────────────


def _uda_fee(area: float, zoning: str) -> float:
    rates = {"RESIDENTIAL": 50, "COMMERCIAL": 100, "INDUSTRIAL": 75, "MIXED_USE": 85}
    mins  = {"RESIDENTIAL": 5_000, "COMMERCIAL": 10_000, "INDUSTRIAL": 15_000, "MIXED_USE": 10_000}
    return max(area * rates.get(zoning, 75), mins.get(zoning, 10_000))


def _local_authority_fee(area: float, zoning: str) -> float:
    rates = {"RESIDENTIAL": 35, "COMMERCIAL": 65, "INDUSTRIAL": 55, "MIXED_USE": 55}
    return max(area * rates.get(zoning, 45), 4_000)


def _fire_safety_fee(area: float, stories: int) -> float:
    base = 80_000 if stories >= 5 else 50_000 if stories >= 3 else 30_000
    return base + area * 15


# ── Permit builder ─────────────────────────────────────────────────────────────


def _build_permit_list(
    area: float,
    stories: int,
    zoning: str,
    construction_type: str,
) -> list[RoadmapPermitItem]:
    permits: list[RoadmapPermitItem] = []
    is_new  = construction_type == "NEW_CONSTRUCTION"
    is_demo = construction_type == "DEMOLITION"
    is_ext  = construction_type == "EXTENSION"

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    if is_new or is_demo or area > 100:
        permits.append(RoadmapPermitItem(
            id="uda",
            name="UDA Development Permission",
            authority="Urban Development Authority (UDA)",
            icon_key="Building2",
            estimated_fee_lkr=_uda_fee(area, zoning),
            min_days=21, max_days=60,
            mandatory=True, risk_level="HIGH", phase=1,
            description=(
                "Statutory approval from the Urban Development Authority for any "
                "development within UDA-regulated zones."
            ),
            required_documents=[
                "Survey plan certified by Licensed Surveyor",
                "Architectural drawings (4 sets)",
                "Deed of title / lease agreement",
                "Structural drawings (for buildings > 3 stories)",
                "Completed Form UDA/DP/01",
            ],
            legal_reference="Urban Development Authority Law No. 41 of 1978, Section 14",
        ))

    permits.append(RoadmapPermitItem(
        id="local-auth",
        name="Local Authority Building Plan Approval",
        authority="Municipal / Urban / Pradeshiya Sabha Council",
        icon_key="ClipboardCheck",
        estimated_fee_lkr=_local_authority_fee(area, zoning),
        min_days=14, max_days=45,
        mandatory=True, risk_level="HIGH", phase=1,
        description=(
            "Building plan approval is mandatory before any construction activity. "
            "The relevant local authority verifies conformity with the building regulations."
        ),
        required_documents=[
            "Approved survey plan",
            "Architectural drawings (stamped by Chartered Architect)",
            "Structural design calculations",
            "Soil test report (for > 2 stories)",
            "Application form with owner signature",
        ],
        legal_reference="Building Regulations 1986 under Local Authorities Ordinance, Section 23",
    ))

    if area > 500 or zoning in ("INDUSTRIAL", "COMMERCIAL"):
        fee_tier = 150_000 if area > 2_000 else 75_000 if area > 500 else 50_000
        permits.append(RoadmapPermitItem(
            id="cea",
            name="CEA Environmental Clearance",
            authority="Central Environmental Authority (CEA)",
            icon_key="Leaf",
            estimated_fee_lkr=fee_tier,
            min_days=30, max_days=90,
            mandatory=zoning == "INDUSTRIAL", risk_level="HIGH", phase=1,
            description=(
                "Projects above 500 m² or in industrial/commercial zones require an "
                "environmental screening or Initial Environmental Examination (IEE)."
            ),
            required_documents=[
                "Project Information Document (PID)",
                "Environmental Impact Assessment report",
                "Site plan showing buffer zones",
                "Drainage disposal plan",
                "EIA application form (CEA/EIA/01)",
            ],
            legal_reference="National Environmental Act No. 47 of 1980, Section 23(cc)",
        ))

    if zoning in ("COMMERCIAL", "INDUSTRIAL") or area > 1_000:
        permits.append(RoadmapPermitItem(
            id="rda",
            name="Road Access / Deviation Permit",
            authority="Road Development Authority (RDA)",
            icon_key="Map",
            estimated_fee_lkr=100_000 if zoning == "INDUSTRIAL" else 45_000,
            min_days=14, max_days=30,
            mandatory=False, risk_level="MEDIUM", phase=1,
            description=(
                "Required when construction activities involve or affect a national road, "
                "access deviation, or hoarding on a road reserve."
            ),
            required_documents=[
                "Site location plan",
                "Traffic impact assessment",
                "Proposed road access layout",
                "RDA application form",
            ],
            legal_reference="Road Development Authority Act No. 73 of 1981, Section 8",
        ))

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    if stories >= 3 or area > 1_000 or zoning in ("COMMERCIAL", "INDUSTRIAL"):
        permits.append(RoadmapPermitItem(
            id="fire",
            name="Fire Safety Certificate",
            authority="Sri Lanka Fire Department / District Fire Brigade",
            icon_key="Flame",
            estimated_fee_lkr=_fire_safety_fee(area, stories),
            min_days=10, max_days=30,
            mandatory=stories >= 3 or zoning == "COMMERCIAL",
            risk_level="HIGH" if stories >= 5 else "MEDIUM",
            phase=2,
            description=(
                "Issued after inspection of fire suppression systems, emergency exits, "
                "fire-rated doors, and fire detection installations."
            ),
            required_documents=[
                "Fire protection system drawings",
                "Fire compartmentation plan",
                "Sprinkler system layout",
                "Emergency evacuation plan",
                "Hydrant installation certificate",
            ],
            legal_reference="Fire Services Act No. 24 of 1974; SLSI SLS 1390 Fire Safety Standard",
        ))

    if is_new or is_ext:
        permits.append(RoadmapPermitItem(
            id="electrical",
            name="Electrical Supply Connection Approval",
            authority="Lanka Electricity Company (LECO) / Ceylon Electricity Board (CEB)",
            icon_key="Zap",
            estimated_fee_lkr=45_000 if stories >= 3 else 20_000,
            min_days=7, max_days=21,
            mandatory=True, risk_level="MEDIUM", phase=2,
            description=(
                "Approval for new electrical supply connection, including load application "
                "and metering installation inspection."
            ),
            required_documents=[
                "Electrical installation drawings",
                "Single-line diagram",
                "Load calculation sheet",
                "Registered electrical contractor certification",
                "Completed CEB/LECO application form",
            ],
            legal_reference="Electricity Act No. 20 of 2009, Section 44; IEE Wiring Regulations BS 7671",
        ))

        permits.append(RoadmapPermitItem(
            id="water",
            name="Water Supply & Drainage Connection",
            authority="National Water Supply & Drainage Board (NWSDB)",
            icon_key="Droplets",
            estimated_fee_lkr=25_000,
            min_days=10, max_days=25,
            mandatory=True, risk_level="MEDIUM", phase=2,
            description=(
                "Connection approval for potable water supply and sewage/drainage "
                "tie-in to the municipal network."
            ),
            required_documents=[
                "Plumbing layout drawings",
                "Sewage disposal plan",
                "Water demand calculation",
                "NWSDB application form",
            ],
            legal_reference="National Water Supply & Drainage Board Law No. 2 of 1974, Section 15",
        ))

    # ── Phase 3 ───────────────────────────────────────────────────────────────

    permits.append(RoadmapPermitItem(
        id="coc",
        name="Certificate of Conformity (CoC)",
        authority="Local Authority / Chartered Engineer",
        icon_key="BadgeCheck",
        estimated_fee_lkr=15_000,
        min_days=7, max_days=21,
        mandatory=True, risk_level="HIGH", phase=3,
        description=(
            "Issued by the local authority after final inspection confirms that all "
            "completed work conforms to the approved plans and building regulations."
        ),
        required_documents=[
            "As-built drawings",
            "Structural completion certificate (Chartered Engineer)",
            "Electrical inspection certificate",
            "Plumbing completion certificate",
            "Fire safety completion report",
        ],
        legal_reference="Building Regulations 1986, Section 36; UDA Circular No. 2022/01",
    ))

    if zoning in ("COMMERCIAL", "INDUSTRIAL") or stories >= 3:
        permits.append(RoadmapPermitItem(
            id="occupancy",
            name="Certificate of Occupancy",
            authority="Local Authority / UDA",
            icon_key="HardHat",
            estimated_fee_lkr=20_000,
            min_days=14, max_days=30,
            mandatory=True, risk_level="HIGH", phase=3,
            description=(
                "Authorises legal occupation of the building. Issued only after all "
                "Phase 1 & 2 clearances and the Certificate of Conformity are in order."
            ),
            required_documents=[
                "Certificate of Conformity",
                "Fire Safety Certificate",
                "LECO/CEB connection certificate",
                "NWSDB connection certificate",
                "Structural completion report",
            ],
            legal_reference=(
                "Urban Development Authority Law No. 41 of 1978, Section 19; "
                "Building Regulations 1986, Section 38"
            ),
        ))

    return permits


# ── Risk-alert builder ─────────────────────────────────────────────────────────


def _build_roadmap_risk_alerts(
    area: float,
    stories: int,
    zoning: str,
    construction_type: str,
    project_value_lkr: float | None,
) -> list[RoadmapRiskAlert]:
    alerts: list[RoadmapRiskAlert] = []
    value = project_value_lkr or 0.0

    if stories >= 5:
        alerts.append(RoadmapRiskAlert(
            id="risk-highrise",
            severity="HIGH",
            title="High-Rise Building — Multi-Authority Coordination Required",
            message=(
                f"Buildings of {stories} stories require simultaneous coordination across "
                "UDA, Local Authority, Fire Department, and LECO. Fire safety inspections "
                "are mandatory at multiple construction stages. Engage a Chartered Architect "
                "and a Fire Safety Consultant before commencing structural works."
            ),
            penalty_lkr=round(value * 0.10) if value > 0 else 1_000_000,
            daily_accrual_lkr=10_000,
            stop_work=False,
            statute="Fire Services Act No. 24 of 1974; UDA Law No. 41 of 1978",
            corrective_action=(
                "Appoint a dedicated Compliance Manager. Prepare a parallel permit "
                "submission schedule to minimise critical-path delays."
            ),
        ))

    if zoning == "INDUSTRIAL":
        alerts.append(RoadmapRiskAlert(
            id="risk-industrial-cea",
            severity="HIGH",
            title="Industrial Zone — CEA Environmental Clearance is Mandatory",
            message=(
                "All industrial developments require a mandatory Initial Environmental "
                "Examination (IEE) from the Central Environmental Authority. The CEA "
                "review process takes 30–90 days and is a hard blocker for foundation work."
            ),
            penalty_lkr=500_000,
            daily_accrual_lkr=5_000,
            stop_work=False,
            statute="National Environmental Act No. 47 of 1980, Section 23(cc)",
            corrective_action=(
                "Commission an IEE from a registered environmental consultant before any "
                "other permit submission. Aim to submit within the first month of the project."
            ),
        ))

    if construction_type == "DEMOLITION":
        alerts.append(RoadmapRiskAlert(
            id="risk-demolition",
            severity="HIGH",
            title="Demolition Works — Hazardous Materials Survey Required",
            message=(
                "Before any demolition activity, a hazardous materials survey (including "
                "asbestos) is required under the Factory Ordinance and CEA regulations. "
                "Unauthorised demolition without UDA approval can result in immediate "
                "stop-work and prosecution."
            ),
            penalty_lkr=750_000,
            daily_accrual_lkr=7_500,
            stop_work=True,
            statute="UDA Law No. 41 of 1978, Section 14; Factory Ordinance No. 45 of 1942",
            corrective_action=(
                "Obtain UDA Development Permission and a hazardous materials survey report "
                "before commencing any demolition. Engage a specialist demolition contractor "
                "licensed by the CIDA."
            ),
        ))

    if area > 2_000 and zoning == "COMMERCIAL":
        alerts.append(RoadmapRiskAlert(
            id="risk-large-commercial",
            severity="MEDIUM",
            title="Large Commercial Development — Extended Review Timelines",
            message=(
                f"Commercial projects exceeding 2,000 m² (your project: {area:,.0f} m²) "
                "typically face extended CEA and RDA review periods. Both must be resolved "
                "before construction commences."
            ),
            penalty_lkr=250_000,
            daily_accrual_lkr=None,
            stop_work=False,
            statute=(
                "National Environmental Act No. 47 of 1980; "
                "Road Development Authority Act No. 73 of 1981"
            ),
            corrective_action=(
                "Begin CEA and RDA applications simultaneously at project kick-off. "
                "Assign a dedicated coordinator for environmental document preparation."
            ),
        ))

    if construction_type == "NEW_CONSTRUCTION" and stories >= 3:
        alerts.append(RoadmapRiskAlert(
            id="risk-multi-story-structural",
            severity="MEDIUM",
            title="Multi-Story Structure — Soil & Structural Design Certification Required",
            message=(
                f"Your {stories}-story building requires a certified Soil Test Report and "
                "Structural Design Calculation submitted alongside the Local Authority "
                "application. Missing these delays approval by 2–4 weeks."
            ),
            penalty_lkr=None,
            daily_accrual_lkr=None,
            stop_work=False,
            statute="Building Regulations 1986, Section 23; ICTAD SCA/2",
            corrective_action=(
                "Commission a soil investigation report and engage a Chartered Structural "
                "Engineer at the design stage. Have all structural calculations stamped "
                "before plan submission."
            ),
        ))

    return alerts


@router.post(
    "/roadmap",
    response_model=RoadmapResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a permit approval roadmap from building parameters",
    description=(
        "Accepts building parameters (floor area, stories, zoning, construction type) "
        "and returns the full three-phase approval roadmap: required permits with fee "
        "estimates and processing timelines, plus proactive risk alerts specific to the "
        "project characteristics. Requires a valid JWT Bearer token."
    ),
)
async def generate_roadmap(
    body: Annotated[RoadmapBuildingParams, Body()],
    _payload: Annotated[dict, Depends(require_auth)],
) -> RoadmapResponse:
    permits = _build_permit_list(
        area=body.floor_area,
        stories=body.stories,
        zoning=body.zoning_type,
        construction_type=body.construction_type,
    )

    risk_alerts = _build_roadmap_risk_alerts(
        area=body.floor_area,
        stories=body.stories,
        zoning=body.zoning_type,
        construction_type=body.construction_type,
        project_value_lkr=body.project_value_lkr,
    )

    total_fee      = sum(p.estimated_fee_lkr for p in permits)
    max_days       = max((p.max_days for p in permits), default=0)
    mandatory_count = sum(1 for p in permits if p.mandatory)
    high_risk_count = sum(1 for p in permits if p.risk_level == "HIGH")

    logger.info(
        "Roadmap generated | zoning=%s type=%s area=%.0f stories=%d permits=%d alerts=%d",
        body.zoning_type,
        body.construction_type,
        body.floor_area,
        body.stories,
        len(permits),
        len(risk_alerts),
    )

    return RoadmapResponse(
        permits=permits,
        risk_alerts=risk_alerts,
        summary=RoadmapSummary(
            total_permits=len(permits),
            mandatory_count=mandatory_count,
            estimated_total_fee_lkr=round(total_fee, 2),
            max_timeline_days=max_days,
            high_risk_count=high_risk_count,
        ),
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
