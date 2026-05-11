"""
Compliance domain models – Pydantic v2.

Covers the full data contract for permit-workflow documents stored in
MongoDB's ``permit_workflows`` collection.

Document hierarchy
──────────────────
ProjectCompliance          ← root document (one per project)
  └── permits: list[PermitApplication]
        ├── documents: list[DocumentRef]
        └── history:   list[WorkflowTransition]

State machine
─────────────
                    ┌──────────────────────────────────────────┐
                    │  (re-submission after rejection)         │
                    ▼                                          │
NOT_STARTED → DOCUMENT_GATHERING → SUBMITTED → UNDER_REVIEW ──┤
                                                              ├→ APPROVED  (terminal)
                                                              └→ REJECTED ─┘

Other services (scheduling, cost estimation) consume the ProjectComplianceResponse
contract via GET /api/v1/compliance/{project_id}/status.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


# ── Enumerations ────────────────────────────────────────────────────────────────


class WorkflowStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    DOCUMENT_GATHERING = "DOCUMENT_GATHERING"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PermitType(str, Enum):
    BUILDING = "BUILDING"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    ELECTRICAL = "ELECTRICAL"
    PLUMBING = "PLUMBING"
    FIRE_SAFETY = "FIRE_SAFETY"
    ZONING = "ZONING"
    DEMOLITION = "DEMOLITION"
    OCCUPANCY = "OCCUPANCY"


# ── State-machine transition table ─────────────────────────────────────────────

#: Maps each status to the set of statuses it may legally transition to.
VALID_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.NOT_STARTED: frozenset({WorkflowStatus.DOCUMENT_GATHERING}),
    WorkflowStatus.DOCUMENT_GATHERING: frozenset({WorkflowStatus.SUBMITTED}),
    WorkflowStatus.SUBMITTED: frozenset({WorkflowStatus.UNDER_REVIEW}),
    WorkflowStatus.UNDER_REVIEW: frozenset(
        {WorkflowStatus.APPROVED, WorkflowStatus.REJECTED}
    ),
    WorkflowStatus.APPROVED: frozenset(),   # terminal – no further transitions
    WorkflowStatus.REJECTED: frozenset(
        {WorkflowStatus.DOCUMENT_GATHERING}  # re-submission path
    ),
}

#: Human-readable description of each status for API consumers.
STATUS_LABELS: dict[WorkflowStatus, str] = {
    WorkflowStatus.NOT_STARTED: "Application not yet started",
    WorkflowStatus.DOCUMENT_GATHERING: "Collecting required documentation",
    WorkflowStatus.SUBMITTED: "Application submitted to authority",
    WorkflowStatus.UNDER_REVIEW: "Under review by compliance officer",
    WorkflowStatus.APPROVED: "Permit approved",
    WorkflowStatus.REJECTED: "Application rejected – revision required",
}


# ── Sub-document models ─────────────────────────────────────────────────────────


class DocumentRef(BaseModel):
    """Reference to a supporting document attached to a permit application."""

    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., description="Accessible URL to the stored document")
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class WorkflowTransition(BaseModel):
    """Immutable audit-trail entry recorded on every state change."""

    transition_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_status: WorkflowStatus
    to_status: WorkflowStatus
    changed_by: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Email or user-ID of the actor who triggered this transition",
    )
    notes: str | None = Field(
        default=None,
        max_length=1_000,
        description="Optional free-text rationale for the transition",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class PermitApplication(BaseModel):
    """
    A single permit application within a project compliance workflow.

    Each project may have multiple permits of different types tracked
    independently through the same state machine.
    """

    permit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    permit_type: PermitType
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=2_000)
    status: WorkflowStatus = Field(default=WorkflowStatus.NOT_STARTED)
    assigned_officer: str | None = Field(
        default=None,
        description="Email or name of the responsible compliance officer",
    )
    deadline: datetime | None = Field(
        default=None,
        description="Target approval deadline (UTC)",
    )
    documents: list[DocumentRef] = Field(default_factory=list)
    history: list[WorkflowTransition] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def is_terminal(self) -> bool:
        """True if the permit is in a terminal state (no further transitions)."""
        return not VALID_TRANSITIONS[self.status]

    @property
    def valid_next_statuses(self) -> list[WorkflowStatus]:
        """Returns the list of statuses this permit may legally move to next."""
        return sorted(VALID_TRANSITIONS[self.status], key=lambda s: s.value)


# ── Root document ───────────────────────────────────────────────────────────────


class ProjectCompliance(BaseModel):
    """
    Root MongoDB document – one record per construction project.

    Stored in the ``permit_workflows`` collection with ``project_id`` as a
    unique index so that lookups are O(1) without scanning.
    """

    project_id: str = Field(..., min_length=1, max_length=128)
    project_name: str = Field(..., min_length=1, max_length=255)
    permits: list[PermitApplication] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("project_id")
    @classmethod
    def _strip_project_id(cls, v: str) -> str:
        return v.strip()


# ── API request / response schemas ─────────────────────────────────────────────


class UpdateStepRequest(BaseModel):
    """
    PATCH /api/v1/compliance/{project_id}/update-step

    Body contract for advancing (or reverting after rejection) a permit's
    workflow state.  The state machine in ComplianceService enforces that
    only legal transitions are applied.
    """

    permit_id: str = Field(..., description="UUID of the target permit application")
    new_status: WorkflowStatus = Field(
        ..., description="The desired next state for this permit"
    )
    changed_by: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            max_length=255,
            description="Email or user-ID of the officer making this change",
        ),
    ]
    notes: str | None = Field(
        default=None,
        max_length=1_000,
        description="Rationale or comments for this state transition",
    )


class PermitSummary(BaseModel):
    """Flattened permit view returned inside the status response."""

    permit_id: str
    permit_type: PermitType
    title: str
    status: WorkflowStatus
    status_label: str
    assigned_officer: str | None
    deadline: datetime | None
    document_count: int
    valid_next_statuses: list[WorkflowStatus]
    last_updated: datetime
    history: list[WorkflowTransition]


class ProjectComplianceResponse(BaseModel):
    """
    GET /api/v1/compliance/{project_id}/status – public contract.

    Consumed by this service's frontend and also by downstream microservices
    (scheduling, cost estimation) to gate their own workflows.

    ``overall_progress_pct`` is a simple numeric signal:
      (approved_permits / total_permits) × 100

    ``all_permits_resolved`` is the canonical boolean gate other services
    should check before proceeding with cost/schedule calculations.
    """

    project_id: str
    project_name: str
    total_permits: int
    approved_count: int
    rejected_count: int
    pending_count: int
    overall_progress_pct: float = Field(
        description="Percentage of permits in APPROVED state (0–100)"
    )
    all_permits_resolved: bool = Field(
        description="True when every permit is APPROVED or REJECTED with no pending work"
    )
    permits: list[PermitSummary]
    created_at: datetime
    updated_at: datetime


class UpdateStepResponse(BaseModel):
    """Response body returned after a successful PATCH update-step call."""

    project_id: str
    permit_id: str
    permit_title: str
    previous_status: WorkflowStatus
    new_status: WorkflowStatus
    status_label: str
    transition_id: str
    changed_by: str
    timestamp: datetime
    message: str
