"""
ComplianceService – permit-workflow business logic.

All MongoDB I/O is async (Motor).  The service layer is intentionally
decoupled from FastAPI — it takes a Motor database handle and raises plain
Python exceptions; the router translates those into HTTP responses.

Collection: ``permit_workflows``
Indexes (created on first run):
  - permit_workflows.project_id   (unique)
  - permit_workflows.updated_at   (for range queries by other services)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from app.models.compliance import (
    VALID_TRANSITIONS,
    STATUS_LABELS,
    PermitApplication,
    PermitSummary,
    PermitType,
    ProjectCompliance,
    ProjectComplianceResponse,
    UpdateStepRequest,
    UpdateStepResponse,
    WorkflowStatus,
    WorkflowTransition,
)

logger = logging.getLogger(__name__)

_COLLECTION = "permit_workflows"


# ── Custom exceptions ───────────────────────────────────────────────────────────


class ProjectNotFoundError(Exception):
    """Raised when a project_id has no compliance record."""


class PermitNotFoundError(Exception):
    """Raised when a permit_id does not exist within the project."""


class InvalidTransitionError(Exception):
    """Raised when the requested state change violates the state machine."""

    def __init__(
        self,
        current: WorkflowStatus,
        requested: WorkflowStatus,
        valid_next: list[WorkflowStatus],
    ) -> None:
        self.current = current
        self.requested = requested
        self.valid_next = valid_next
        super().__init__(
            f"Cannot transition from {current.value!r} to {requested.value!r}. "
            f"Valid next states: {[s.value for s in valid_next] or ['none (terminal state)']}"
        )


# ── Service ─────────────────────────────────────────────────────────────────────


class ComplianceService:
    """
    Encapsulates all compliance-workflow database operations.

    One instance is created per request via FastAPI dependency injection so
    that the Motor database handle is always fresh and correctly scoped.
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
        self._db = db
        self._col = db[_COLLECTION]

    # ── Index management ────────────────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """
        Idempotently create the required indexes.
        Called once at application startup from the lifespan handler.
        """
        indexes = [
            IndexModel([("project_id", ASCENDING)], unique=True, name="project_id_unique"),
            IndexModel([("updated_at", DESCENDING)], name="updated_at_desc"),
        ]
        await self._col.create_indexes(indexes)
        logger.info("Compliance collection indexes verified.")

    # ── Read ────────────────────────────────────────────────────────────────────

    async def get_project_status(self, project_id: str) -> ProjectComplianceResponse:
        """
        Fetch the full compliance status for a project.

        Returns a ``ProjectComplianceResponse`` which is the stable API
        contract consumed by this service's frontend and by downstream
        microservices (scheduling, cost estimation).

        Raises:
            ProjectNotFoundError: if no document exists for *project_id*.
        """
        doc = await self._col.find_one({"project_id": project_id}, {"_id": 0})
        if doc is None:
            raise ProjectNotFoundError(project_id)

        project = ProjectCompliance(**doc)
        return self._build_response(project)

    # ── Write ───────────────────────────────────────────────────────────────────

    async def update_permit_step(
        self, project_id: str, request: UpdateStepRequest
    ) -> UpdateStepResponse:
        """
        Advance (or revert) a permit's workflow state.

        Enforces the state machine defined in ``VALID_TRANSITIONS``.
        Appends an immutable ``WorkflowTransition`` entry to the permit's
        history for a full audit trail.

        Raises:
            ProjectNotFoundError:  project_id not found.
            PermitNotFoundError:   permit_id not found within the project.
            InvalidTransitionError: requested transition is not permitted.
        """
        doc = await self._col.find_one({"project_id": project_id}, {"_id": 0})
        if doc is None:
            raise ProjectNotFoundError(project_id)

        project = ProjectCompliance(**doc)

        # Locate the target permit
        permit_index, permit = next(
            (
                (i, p)
                for i, p in enumerate(project.permits)
                if p.permit_id == request.permit_id
            ),
            (None, None),
        )
        if permit is None or permit_index is None:
            raise PermitNotFoundError(request.permit_id)

        # Validate the transition
        valid_next = list(VALID_TRANSITIONS[permit.status])
        if request.new_status not in VALID_TRANSITIONS[permit.status]:
            raise InvalidTransitionError(permit.status, request.new_status, valid_next)

        # Build the immutable audit entry
        transition = WorkflowTransition(
            from_status=permit.status,
            to_status=request.new_status,
            changed_by=request.changed_by,
            notes=request.notes,
        )

        previous_status = permit.status
        now = datetime.now(timezone.utc)

        # Atomic update via positional operator on the embedded array
        result = await self._col.update_one(
            {
                "project_id": project_id,
                "permits.permit_id": request.permit_id,
            },
            {
                "$set": {
                    f"permits.{permit_index}.status": request.new_status.value,
                    f"permits.{permit_index}.updated_at": now,
                    "updated_at": now,
                },
                "$push": {
                    f"permits.{permit_index}.history": transition.model_dump(mode="json"),
                },
            },
        )

        if result.modified_count == 0:
            logger.warning(
                "update_permit_step: no document modified (project=%s, permit=%s)",
                project_id,
                request.permit_id,
            )

        # Emit an event for downstream microservices (stub – replace with
        # a real message broker call in production, e.g. Kafka / RabbitMQ).
        self._emit_state_change_event(
            project_id=project_id,
            permit_id=request.permit_id,
            permit_type=permit.permit_type,
            previous_status=previous_status,
            new_status=request.new_status,
            changed_by=request.changed_by,
        )

        logger.info(
            "Permit '%s' in project '%s' transitioned %s → %s by %s",
            request.permit_id,
            project_id,
            previous_status.value,
            request.new_status.value,
            request.changed_by,
        )

        return UpdateStepResponse(
            project_id=project_id,
            permit_id=request.permit_id,
            permit_title=permit.title,
            previous_status=previous_status,
            new_status=request.new_status,
            status_label=STATUS_LABELS[request.new_status],
            transition_id=transition.transition_id,
            changed_by=request.changed_by,
            timestamp=transition.timestamp,
            message=(
                f"Permit '{permit.title}' successfully moved from "
                f"{previous_status.value} to {request.new_status.value}."
            ),
        )

    async def create_project_compliance(
        self,
        project_id: str,
        project_name: str,
        permit_types: list[PermitType],
    ) -> ProjectComplianceResponse:
        """
        Bootstrap a new compliance record for a project.

        Creates one ``PermitApplication`` in NOT_STARTED state for each
        permit type listed in *permit_types*.

        Raises:
            DuplicateKeyError (re-raised as ValueError): if a record already
            exists for *project_id*.
        """
        permits = [
            PermitApplication(
                permit_type=pt,
                title=f"{pt.value.replace('_', ' ').title()} Permit",
            )
            for pt in permit_types
        ]
        project = ProjectCompliance(
            project_id=project_id,
            project_name=project_name,
            permits=permits,
        )
        try:
            await self._col.insert_one(project.model_dump(mode="json"))
        except DuplicateKeyError as exc:
            raise ValueError(
                f"A compliance record for project '{project_id}' already exists."
            ) from exc

        logger.info(
            "Created compliance record for project '%s' with %d permit(s).",
            project_id,
            len(permits),
        )
        return self._build_response(project)

    # ── Internal helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_response(project: ProjectCompliance) -> ProjectComplianceResponse:
        """Derive computed fields and map to the public response contract."""
        total = len(project.permits)
        approved = sum(1 for p in project.permits if p.status == WorkflowStatus.APPROVED)
        rejected = sum(1 for p in project.permits if p.status == WorkflowStatus.REJECTED)
        pending = total - approved - rejected
        progress_pct = round((approved / total * 100), 1) if total else 0.0
        all_resolved = pending == 0 and total > 0

        permit_summaries = [
            PermitSummary(
                permit_id=p.permit_id,
                permit_type=p.permit_type,
                title=p.title,
                status=p.status,
                status_label=STATUS_LABELS[p.status],
                assigned_officer=p.assigned_officer,
                deadline=p.deadline,
                document_count=len(p.documents),
                valid_next_statuses=p.valid_next_statuses,
                last_updated=p.updated_at,
                history=p.history,
            )
            for p in project.permits
        ]

        return ProjectComplianceResponse(
            project_id=project.project_id,
            project_name=project.project_name,
            total_permits=total,
            approved_count=approved,
            rejected_count=rejected,
            pending_count=pending,
            overall_progress_pct=progress_pct,
            all_permits_resolved=all_resolved,
            permits=permit_summaries,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    @staticmethod
    def _emit_state_change_event(
        *,
        project_id: str,
        permit_id: str,
        permit_type: PermitType,
        previous_status: WorkflowStatus,
        new_status: WorkflowStatus,
        changed_by: str,
    ) -> None:
        """
        Publish a domain event for inter-service communication.

        PRODUCTION TODO: replace this logging stub with a real message broker
        (e.g. ``aiokafka`` producer or ``aio-pika`` for RabbitMQ).  Other
        microservices (scheduling, cost estimation) subscribe to
        ``compliance.permit.status_changed`` events to gate their workflows.

        Event schema (JSON):
        {
            "event":          "compliance.permit.status_changed",
            "project_id":     str,
            "permit_id":      str,
            "permit_type":    str,
            "previous_status": str,
            "new_status":     str,
            "changed_by":     str
        }
        """
        logger.info(
            "[EVENT] compliance.permit.status_changed | project=%s permit=%s "
            "type=%s %s→%s by=%s",
            project_id,
            permit_id,
            permit_type.value,
            previous_status.value,
            new_status.value,
            changed_by,
        )
