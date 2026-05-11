"""
ComplianceRiskAnalyzer – Proactive Risk Mitigation engine.

Architecture
────────────
The analyzer is a pure, stateless utility class.  It has no database
dependency — data is passed in at call time.  The router (compliance.py)
is responsible for loading live permit data from MongoDB if needed.

This decoupling means:
  • The analyzer is trivially unit-testable without a DB fixture.
  • Any service in the microservice mesh can instantiate and call it directly.
  • The NLP injection slot is clean and requires no changes to the analyzer's
    core logic when a real document-understanding service is added.

NLP injection protocol
──────────────────────
``DocumentAnalysisProtocol`` defines the interface for future NLP integration.
Implement it to enable:
  - Automated scope extraction from scanned permit PDFs.
  - Blueprint deviation detection (planned vs built).
  - Regulatory text cross-referencing (IBC, OSHA, local zoning).

Pass your implementation to ``ComplianceRiskAnalyzer(document_analyzer=...)``.
Until then, ``NLPDocumentAnalyzerStub`` is used automatically.

Deviation logic
───────────────
For each permit type listed as a prerequisite for the current construction
stage, the analyzer checks whether that permit is APPROVED.  If not, a
``DetectedDeviation`` is raised with:
  - Severity derived from the permit's current status + its criticality tier.
  - Financial penalty calculated from the severity tier (percentage-based when
    project value is known; regulatory flat fee otherwise).
  - One or more ``LegalWarning`` entries referencing real building codes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from app.models.compliance import PermitType, WorkflowStatus
from app.models.risk import (
    ConstructionStage,
    DetectedDeviation,
    FinancialPenalty,
    LegalWarning,
    PermitStatusInput,
    RiskAnalysisResponse,
    ViolationSeverity,
)

logger = logging.getLogger(__name__)


# ── NLP injection protocol ──────────────────────────────────────────────────────


@runtime_checkable
class DocumentAnalysisProtocol(Protocol):
    """
    Interface for pluggable NLP document-understanding services.

    TO IMPLEMENT (future sprint):
      1. Create a class that satisfies this protocol.
      2. Pass it to ``ComplianceRiskAnalyzer(document_analyzer=YourClass())``.
      3. No other changes are required in the analyzer or router.

    Expected capabilities:
      - ``analyze_document``  : Parse a stored permit PDF/image and return
                               structured metadata (approved scope, conditions).
      - ``extract_approved_scope`` : Return the approved work description for a
                                   permit so it can be diffed against current
                                   construction progress.
    """

    def analyze_document(self, document_url: str) -> dict[str, Any]:
        """Return structured metadata extracted from the permit document."""
        ...

    def extract_approved_scope(self, permit_id: str) -> str | None:
        """Return the approved-work description for a permit, or None."""
        ...


class NLPDocumentAnalyzerStub:
    """
    No-op stub — satisfies ``DocumentAnalysisProtocol`` with empty responses.

    Used automatically when no real NLP analyzer is injected.  Produces no
    insights; never raises exceptions.  Replace with a real implementation
    backed by e.g. Google Document AI, Azure Form Recognizer, or a fine-tuned
    LLM with RAG when the NLP sprint is ready.
    """

    def analyze_document(self, document_url: str) -> dict[str, Any]:  # noqa: ARG002
        return {}

    def extract_approved_scope(self, permit_id: str) -> str | None:  # noqa: ARG002
        return None


# ── Static data tables ──────────────────────────────────────────────────────────

#: Numeric rank for each construction stage.  Higher = more advanced.
STAGE_ORDER: dict[ConstructionStage, int] = {
    ConstructionStage.PRE_CONSTRUCTION:   0,
    ConstructionStage.SITE_PREPARATION:   1,
    ConstructionStage.EXCAVATION:         2,
    ConstructionStage.FOUNDATION_STARTED: 3,
    ConstructionStage.FOUNDATION_COMPLETE:4,
    ConstructionStage.STRUCTURAL_FRAMING: 5,
    ConstructionStage.ROUGH_MEP_INSTALL:  6,
    ConstructionStage.ROOFING:            7,
    ConstructionStage.EXTERNAL_ENVELOPE:  8,
    ConstructionStage.FINISHING:          9,
    ConstructionStage.FINAL_INSPECTIONS:  10,
    ConstructionStage.OCCUPANCY_READY:    11,
    ConstructionStage.COMPLETE:           12,
}

#: Permit types required to be APPROVED before each stage may legally begin.
STAGE_PREREQUISITES: dict[ConstructionStage, list[PermitType]] = {
    ConstructionStage.PRE_CONSTRUCTION:   [],
    ConstructionStage.SITE_PREPARATION:   [PermitType.ZONING, PermitType.ENVIRONMENTAL],
    ConstructionStage.EXCAVATION:         [PermitType.ZONING, PermitType.ENVIRONMENTAL, PermitType.BUILDING],
    ConstructionStage.FOUNDATION_STARTED: [PermitType.BUILDING, PermitType.ZONING, PermitType.ENVIRONMENTAL],
    ConstructionStage.FOUNDATION_COMPLETE:[PermitType.BUILDING],
    ConstructionStage.STRUCTURAL_FRAMING: [PermitType.BUILDING, PermitType.FIRE_SAFETY],
    ConstructionStage.ROUGH_MEP_INSTALL:  [PermitType.ELECTRICAL, PermitType.PLUMBING, PermitType.FIRE_SAFETY],
    ConstructionStage.ROOFING:            [PermitType.BUILDING, PermitType.FIRE_SAFETY],
    ConstructionStage.EXTERNAL_ENVELOPE:  [PermitType.BUILDING],
    ConstructionStage.FINISHING:          [PermitType.ELECTRICAL, PermitType.PLUMBING],
    ConstructionStage.FINAL_INSPECTIONS:  [
        PermitType.BUILDING, PermitType.ELECTRICAL,
        PermitType.PLUMBING, PermitType.FIRE_SAFETY, PermitType.ZONING,
    ],
    ConstructionStage.OCCUPANCY_READY:    [
        PermitType.OCCUPANCY, PermitType.BUILDING, PermitType.ELECTRICAL,
        PermitType.PLUMBING, PermitType.FIRE_SAFETY, PermitType.ZONING,
    ],
    ConstructionStage.COMPLETE:           list(PermitType),
}

#: Permit types that automatically escalate severity by one tier.
#  (e.g. BUILDING permit missing at STRUCTURAL_FRAMING = worse than a secondary permit)
CRITICAL_PERMIT_TYPES: frozenset[PermitType] = frozenset({
    PermitType.BUILDING,
    PermitType.FIRE_SAFETY,
    PermitType.ZONING,
})

#: Base severity derived from permit approval status.
STATUS_BASE_SEVERITY: dict[WorkflowStatus, ViolationSeverity | None] = {
    WorkflowStatus.NOT_STARTED:        ViolationSeverity.CRITICAL,
    WorkflowStatus.DOCUMENT_GATHERING: ViolationSeverity.HIGH,
    WorkflowStatus.SUBMITTED:          ViolationSeverity.HIGH,
    WorkflowStatus.UNDER_REVIEW:       ViolationSeverity.MEDIUM,
    WorkflowStatus.REJECTED:           ViolationSeverity.CRITICAL,
    WorkflowStatus.APPROVED:           None,  # no violation
}

#: Severity rank for comparison (worst = highest number).
_SEVERITY_RANK: dict[ViolationSeverity, int] = {
    ViolationSeverity.LOW:      1,
    ViolationSeverity.MEDIUM:   2,
    ViolationSeverity.HIGH:     3,
    ViolationSeverity.CRITICAL: 4,
}

#: Penalty tier per severity.
#  ``percentage`` applied to project value when available; ``flat_fee_usd`` used otherwise.
_PENALTY_TIERS: dict[ViolationSeverity, dict[str, float]] = {
    ViolationSeverity.LOW: {
        "percentage":    0.01,       # 1 % of project value
        "flat_fee_usd":  10_000.0,
        "daily_rate_usd": 200.0,
    },
    ViolationSeverity.MEDIUM: {
        "percentage":    0.05,       # 5 %
        "flat_fee_usd":  50_000.0,
        "daily_rate_usd": 1_000.0,
    },
    ViolationSeverity.HIGH: {
        "percentage":    0.10,       # 10 %
        "flat_fee_usd":  250_000.0,
        "daily_rate_usd": 5_000.0,
    },
    ViolationSeverity.CRITICAL: {
        "percentage":    0.15,       # 15 %
        "flat_fee_usd":  500_000.0,
        "daily_rate_usd": 10_000.0,
    },
}

#: Statutory references keyed by permit type.
_PERMIT_STATUTES: dict[PermitType, list[dict[str, str]]] = {
    PermitType.BUILDING: [
        {
            "code":    "BLDG-001",
            "statute": "IBC §105.1 – Permits Required",
            "message": (
                "Construction commenced without an issued Building Permit constitutes "
                "a violation of IBC §105.1. The authority having jurisdiction may issue "
                "a stop-work order and require removal of completed work."
            ),
            "action":  (
                "Halt all structural work immediately. Submit a complete building permit "
                "application with stamped drawings. Do not resume until a permit is issued."
            ),
        },
        {
            "code":    "BLDG-002",
            "statute": "IBC §114.1 – Stop Work Order",
            "message": (
                "Proceeding with construction during permit review or rejection exposes "
                "the project to a mandatory stop-work order under IBC §114.1."
            ),
            "action":  (
                "Engage a licensed architect or engineer to expedite the permit application. "
                "Document all work completed to date for the permit review package."
            ),
        },
    ],
    PermitType.FIRE_SAFETY: [
        {
            "code":    "FIRE-001",
            "statute": "IFC §105.1.1 – Fire Safety Permits",
            "message": (
                "Structural framing or MEP installation without an approved Fire Safety "
                "Permit violates IFC §105.1.1 and may result in mandatory demolition of "
                "non-compliant fire-protection infrastructure."
            ),
            "action":  (
                "Suspend all fire-protection rough-in work. Submit fire-protection drawings "
                "to the Fire Marshal for review. Retain a licensed fire-protection engineer."
            ),
        },
    ],
    PermitType.ELECTRICAL: [
        {
            "code":    "ELEC-001",
            "statute": "NEC Article 90.2 / Local Electrical Code §110",
            "message": (
                "Electrical rough-in or panel installation without an Electrical Permit "
                "violates NEC Article 90.2 and local electrical codes. Unapproved work "
                "must be fully exposed for inspection and may require removal."
            ),
            "action":  (
                "Stop all electrical rough-in work. Apply for an Electrical Permit with "
                "load calculations and single-line diagrams. Schedule rough-in inspection."
            ),
        },
    ],
    PermitType.PLUMBING: [
        {
            "code":    "PLMB-001",
            "statute": "IPC §106.1 – Plumbing Permits",
            "message": (
                "Plumbing rough-in without an issued Plumbing Permit violates IPC §106.1. "
                "Concealed unapproved plumbing may require destructive inspection."
            ),
            "action":  (
                "Halt all plumbing rough-in. Submit fixture schedules and isometric drawings "
                "for permit review. Schedule a pre-inspection before concealing any piping."
            ),
        },
    ],
    PermitType.ZONING: [
        {
            "code":    "ZONE-001",
            "statute": "Local Zoning Ordinance §10-4 – Zoning Compliance Certificate",
            "message": (
                "Site work commenced without a Zoning Compliance Certificate may result "
                "in use-prohibition orders, fines, and mandated restoration of the site "
                "to its original condition."
            ),
            "action":  (
                "Pause all site work. Obtain a Zoning Compliance Certificate from the "
                "Planning Department before resuming. Confirm setbacks and land-use class."
            ),
        },
    ],
    PermitType.ENVIRONMENTAL: [
        {
            "code":    "ENV-001",
            "statute": "EPA NPDES §402 / Local Environmental Control Act §7",
            "message": (
                "Ground disturbance without an approved Environmental/NPDES permit "
                "violates EPA §402 and may incur federal civil penalties up to $25,000/day."
            ),
            "action":  (
                "Cease all ground-disturbing activities. Install erosion control measures. "
                "File an NPDES Stormwater Pollution Prevention Plan (SWPPP) immediately."
            ),
        },
    ],
    PermitType.OCCUPANCY: [
        {
            "code":    "OCC-001",
            "statute": "IBC §111.1 – Certificate of Occupancy",
            "message": (
                "Occupying or commissioning a building without a Certificate of Occupancy "
                "violates IBC §111.1 and may void all applicable insurance policies."
            ),
            "action":  (
                "Do not allow any occupants or operational use of the building. "
                "Complete all outstanding inspections and obtain the CO before any use."
            ),
        },
    ],
    PermitType.DEMOLITION: [
        {
            "code":    "DEMO-001",
            "statute": "IBC §3303.1 – Demolition Permits",
            "message": (
                "Demolition work commenced without a Demolition Permit violates "
                "IBC §3303.1 and carries both civil fines and criminal liability."
            ),
            "action":  (
                "Immediately halt all demolition work. Apply for a Demolition Permit "
                "including asbestos/hazmat survey results before resuming."
            ),
        },
    ],
}


# ── Main analyzer class ─────────────────────────────────────────────────────────


class ComplianceRiskAnalyzer:
    """
    Stateless risk analysis engine for construction permit compliance.

    Usage::

        analyzer = ComplianceRiskAnalyzer()
        response = analyzer.analyze(
            construction_stage=ConstructionStage.STRUCTURAL_FRAMING,
            permits=[
                PermitStatusInput(permit_type=PermitType.BUILDING, status=WorkflowStatus.UNDER_REVIEW),
                PermitStatusInput(permit_type=PermitType.FIRE_SAFETY, status=WorkflowStatus.NOT_STARTED),
            ],
            project_id="PROJ-001",
            estimated_project_value_usd=5_000_000,
        )

    NLP injection::

        from my_nlp_service import MyNLPAnalyzer
        analyzer = ComplianceRiskAnalyzer(document_analyzer=MyNLPAnalyzer())
    """

    def __init__(
        self,
        document_analyzer: DocumentAnalysisProtocol | None = None,
    ) -> None:
        self._nlp: DocumentAnalysisProtocol = (
            document_analyzer if document_analyzer is not None
            else NLPDocumentAnalyzerStub()
        )

    # ── Public API ──────────────────────────────────────────────────────────────

    def analyze(
        self,
        construction_stage: ConstructionStage,
        permits: list[PermitStatusInput],
        project_id: str | None = None,
        estimated_project_value_usd: float | None = None,
    ) -> RiskAnalysisResponse:
        """
        Analyse permit statuses against the current construction stage.

        Args:
            construction_stage:           Current physical milestone.
            permits:                      List of permit type → status pairs.
            project_id:                   Included in the response for traceability.
            estimated_project_value_usd:  When supplied, penalties use percentage
                                          of project value; otherwise flat fees apply.

        Returns:
            RiskAnalysisResponse with all detected deviations, penalties, and
            legal warnings.  ``has_violations = False`` means the project is
            fully compliant for the current stage.
        """
        permit_map: dict[PermitType, WorkflowStatus] = {
            p.permit_type: p.status for p in permits
        }

        deviations = self._detect_deviations(
            construction_stage=construction_stage,
            permit_map=permit_map,
            estimated_project_value_usd=estimated_project_value_usd,
        )

        # ── NLP insights (no-op until real analyzer is injected) ────────────
        nlp_insights: list[str] = self._gather_nlp_insights(permits)

        return self._build_response(
            project_id=project_id,
            construction_stage=construction_stage,
            deviations=deviations,
            nlp_insights=nlp_insights,
        )

    # ── Deviation detection ─────────────────────────────────────────────────────

    def _detect_deviations(
        self,
        construction_stage: ConstructionStage,
        permit_map: dict[PermitType, WorkflowStatus],
        estimated_project_value_usd: float | None,
    ) -> list[DetectedDeviation]:
        required_permits = STAGE_PREREQUISITES.get(construction_stage, [])
        deviations: list[DetectedDeviation] = []

        for permit_type in required_permits:
            # Treat a missing permit entry as NOT_STARTED — worst case.
            current_status = permit_map.get(permit_type, WorkflowStatus.NOT_STARTED)

            if current_status == WorkflowStatus.APPROVED:
                continue  # Fully compliant — no deviation.

            severity = self._derive_severity(permit_type, current_status)
            penalty = self._calculate_penalty(
                severity=severity,
                estimated_project_value_usd=estimated_project_value_usd,
                permit_type=permit_type,
            )
            legal_warnings = self._build_legal_warnings(
                permit_type=permit_type,
                severity=severity,
            )

            deviations.append(
                DetectedDeviation(
                    permit_type=permit_type,
                    permit_status=current_status,
                    construction_stage=construction_stage,
                    severity=severity,
                    description=self._describe_deviation(
                        permit_type, current_status, construction_stage
                    ),
                    financial_penalty=penalty,
                    legal_warnings=legal_warnings,
                )
            )
            logger.info(
                "Deviation detected: permit=%s status=%s stage=%s severity=%s",
                permit_type.value,
                current_status.value,
                construction_stage.value,
                severity.value,
            )

        # Sort worst-first so the caller sees the most critical issues at top.
        deviations.sort(
            key=lambda d: _SEVERITY_RANK[d.severity],
            reverse=True,
        )
        return deviations

    # ── Severity derivation ─────────────────────────────────────────────────────

    @staticmethod
    def _derive_severity(
        permit_type: PermitType,
        status: WorkflowStatus,
    ) -> ViolationSeverity:
        """
        Derive violation severity from permit status + permit criticality.

        Critical permit types (BUILDING, FIRE_SAFETY, ZONING) escalate the
        base severity by one tier when the base is HIGH.
        """
        base = STATUS_BASE_SEVERITY.get(status)
        if base is None:
            # Defensive: APPROVED should never reach here.
            return ViolationSeverity.LOW

        # Escalate HIGH → CRITICAL for structurally critical permit types.
        if base == ViolationSeverity.HIGH and permit_type in CRITICAL_PERMIT_TYPES:
            return ViolationSeverity.CRITICAL

        return base

    # ── Penalty calculation ─────────────────────────────────────────────────────

    @staticmethod
    def _calculate_penalty(
        severity: ViolationSeverity,
        permit_type: PermitType,
        estimated_project_value_usd: float | None,
    ) -> FinancialPenalty:
        tier = _PENALTY_TIERS[severity]

        if estimated_project_value_usd is not None:
            penalty_usd = round(tier["percentage"] * estimated_project_value_usd, 2)
            basis = "PERCENTAGE_BASED"
            note = (
                f"{tier['percentage'] * 100:.0f}% of estimated project value "
                f"(${estimated_project_value_usd:,.0f}) per regulatory penalty schedule."
            )
        else:
            penalty_usd = tier["flat_fee_usd"]
            basis = "FLAT_FEE"
            note = (
                f"Regulatory flat fee applied (project value not supplied). "
                f"Provide 'estimated_project_value_usd' for a project-specific estimate."
            )

        return FinancialPenalty(
            basis=basis,
            estimated_penalty_usd=penalty_usd,
            daily_accrual_usd=tier["daily_rate_usd"],
            calculation_note=note,
        )

    # ── Legal warning construction ──────────────────────────────────────────────

    @staticmethod
    def _build_legal_warnings(
        permit_type: PermitType,
        severity: ViolationSeverity,
    ) -> list[LegalWarning]:
        statute_entries = _PERMIT_STATUTES.get(permit_type, [])
        stop_work = severity in (ViolationSeverity.HIGH, ViolationSeverity.CRITICAL)

        return [
            LegalWarning(
                warning_code=entry["code"],
                statute_reference=entry["statute"],
                message=entry["message"],
                corrective_action=entry["action"],
                stop_work_required=stop_work,
            )
            for entry in statute_entries
        ]

    # ── Deviation narrative ─────────────────────────────────────────────────────

    @staticmethod
    def _describe_deviation(
        permit_type: PermitType,
        status: WorkflowStatus,
        stage: ConstructionStage,
    ) -> str:
        stage_label = stage.value.replace("_", " ").title()
        permit_label = permit_type.value.replace("_", " ").title()
        status_label = status.value.replace("_", " ").title()
        return (
            f"{permit_label} Permit is '{status_label}' but construction has "
            f"reached '{stage_label}', which legally requires this permit to be "
            f"fully APPROVED before work at this stage may proceed."
        )

    # ── NLP insight gathering (injection hook) ──────────────────────────────────

    def _gather_nlp_insights(
        self,
        permits: list[PermitStatusInput],
    ) -> list[str]:
        """
        Delegate to the injected NLP analyzer to extract document-level insights.

        With the stub this is a no-op.  With a real analyzer, each permit's
        documents are parsed and scope deviations are returned as plain-English
        strings that appear in ``RiskAnalysisResponse.nlp_insights``.
        """
        insights: list[str] = []
        for permit in permits:
            scope = self._nlp.extract_approved_scope(permit.permit_type.value)
            if scope:
                insights.append(
                    f"[{permit.permit_type.value}] Approved scope extracted: {scope}"
                )
        return insights

    # ── Response assembly ───────────────────────────────────────────────────────

    @staticmethod
    def _build_response(
        project_id: str | None,
        construction_stage: ConstructionStage,
        deviations: list[DetectedDeviation],
        nlp_insights: list[str],
    ) -> RiskAnalysisResponse:
        has_violations = len(deviations) > 0

        overall_severity: ViolationSeverity | None = (
            max(deviations, key=lambda d: _SEVERITY_RANK[d.severity]).severity
            if has_violations
            else None
        )

        total_penalty = round(
            sum(d.financial_penalty.estimated_penalty_usd for d in deviations), 2
        )
        total_daily = round(
            sum(d.financial_penalty.daily_accrual_usd for d in deviations), 2
        )

        recommendations = _build_recommendations(deviations, construction_stage)

        return RiskAnalysisResponse(
            project_id=project_id,
            construction_stage=construction_stage,
            has_violations=has_violations,
            overall_severity=overall_severity,
            violation_count=len(deviations),
            total_estimated_penalty_usd=total_penalty,
            total_daily_accrual_usd=total_daily,
            deviations=deviations,
            compliance_recommendations=recommendations,
            nlp_insights=nlp_insights,
            analyzed_at=datetime.now(timezone.utc),
        )


# ── Recommendation generator ────────────────────────────────────────────────────


def _build_recommendations(
    deviations: list[DetectedDeviation],
    stage: ConstructionStage,
) -> list[str]:
    """
    Produce a prioritised, de-duplicated list of corrective recommendations.

    CRITICAL and HIGH deviations lead the list.  When the stage is advanced
    enough that a stop-work order is warranted, that instruction is always first.
    """
    if not deviations:
        return [
            f"All required permits are approved for '{stage.value}'. "
            "Continue construction in accordance with the approved plans."
        ]

    recs: list[str] = []

    critical_or_high = [
        d for d in deviations
        if d.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.HIGH)
    ]
    if critical_or_high:
        recs.append(
            "IMMEDIATE ACTION: Issue a Stop-Work Notice to all on-site contractors "
            "until all CRITICAL and HIGH severity permit violations are resolved."
        )

    # Per-permit recommendations, worst-first (list is already sorted).
    seen_types: set[PermitType] = set()
    for dev in deviations:
        if dev.permit_type in seen_types:
            continue
        seen_types.add(dev.permit_type)
        permit_label = dev.permit_type.value.replace("_", " ").title()
        status_label = dev.permit_status.value.replace("_", " ").title()
        recs.append(
            f"[{dev.severity.value}] Resolve {permit_label} Permit "
            f"(currently '{status_label}'): "
            + (dev.legal_warnings[0].corrective_action if dev.legal_warnings else
               f"Obtain {permit_label} Permit approval before resuming work.")
        )

    recs.append(
        "Engage your Compliance Officer to conduct a full permit-status review "
        "and establish a resolution timeline for all outstanding approvals."
    )
    return recs


# ── Module-level singleton ──────────────────────────────────────────────────────

#: Default analyzer instance (stub NLP).  Import and use directly, or
#: instantiate a new one with a real NLP analyzer via dependency injection.
default_analyzer = ComplianceRiskAnalyzer()
