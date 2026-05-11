"""
Cost & Scheduling Microservice  –  Component 4
───────────────────────────────────────────────
Prefix : /api/v1/project
Tag    : Cost & Scheduling

Endpoints
─────────
POST /api/v1/project/schedule
    CPM (Critical Path Method) schedule from a user-supplied task graph.
    Uses networkx to run a forward + backward pass and returns per-task
    Early/Late Start/Finish, Total Float, the critical path, and a
    ``gantt`` list shaped for direct Gantt chart rendering.

POST /api/v1/project/boq
    Bill-of-Quantities cost aggregation using pandas.
    Items without a ``unit_rate_lkr`` are flagged as PENDING_SCRAPE and
    excluded from totals.  A BeautifulSoup web-scraping hook
    (_fetch_live_rates) is wired in at the aggregation step — see the
    HOOK comment block for full implementation instructions.

Auth
────
Both endpoints are auth-agnostic at the router level.  Authentication is
applied at include_router() time in main.py via
    app.include_router(cost_router, dependencies=[Depends(require_auth)])
so the same JWT guard used by all other endpoints is enforced without any
direct dependency on the app.dependencies.auth module.

Integration notes
─────────────────
- /schedule output (gantt list) is designed for the frontend GanttChart component.
- /boq output can be composed with the compliance roadmap permit fees to produce
  a full construction cost summary.
- Both endpoints are stateless; they accept all required data in the request body
  so they can be called independently or chained by other microservices.
"""

from __future__ import annotations

import logging
import math
from typing import Annotated, Any

import networkx as nx
import pandas as pd
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/project", tags=["Cost & Scheduling"])


# ══════════════════════════════════════════════════════════════════════════════
# §1  SCHEDULE  –  CPM (Critical Path Method)
# ══════════════════════════════════════════════════════════════════════════════

# ── Request models ─────────────────────────────────────────────────────────────


class TaskIn(BaseModel):
    """A single construction task node in the project network diagram."""

    id: str = Field(
        ...,
        description=(
            "Unique task identifier (e.g. 'T01'). "
            "Referenced by other tasks in their ``dependencies`` list."
        ),
    )
    name: str = Field(..., description="Human-readable task name for Gantt chart labels.")
    duration: int = Field(..., gt=0, description="Task duration in working days.")
    dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of tasks that must *finish* before this task can *start* "
            "(Finish-to-Start relationship). Leave empty for tasks with no predecessors."
        ),
    )

    model_config = {"json_schema_extra": {"example": {"id": "T03", "name": "Formwork", "duration": 5, "dependencies": ["T01", "T02"]}}}


class ScheduleRequest(BaseModel):
    project_name: str = Field(..., min_length=1, description="Project name for reporting.")
    tasks: list[TaskIn] = Field(..., min_length=1, description="Full list of project tasks.")

    @model_validator(mode="after")
    def _validate_dependency_refs(self) -> "ScheduleRequest":
        """All dependency IDs must refer to a task that exists in the same request."""
        known_ids = {t.id for t in self.tasks}
        for task in self.tasks:
            unknown = set(task.dependencies) - known_ids
            if unknown:
                raise ValueError(
                    f"Task '{task.id}' references unknown dependency IDs: {sorted(unknown)}. "
                    "Every dependency must correspond to another task in the 'tasks' list."
                )
        return self

    model_config = {
        "json_schema_extra": {
            "example": {
                "project_name": "Office Block – Phase 1",
                "tasks": [
                    {"id": "T01", "name": "Site Clearing", "duration": 3, "dependencies": []},
                    {"id": "T02", "name": "Excavation", "duration": 5, "dependencies": ["T01"]},
                    {"id": "T03", "name": "Foundation Concrete", "duration": 7, "dependencies": ["T02"]},
                    {"id": "T04", "name": "Backfilling", "duration": 3, "dependencies": ["T03"]},
                    {"id": "T05", "name": "Ground Floor Slab", "duration": 4, "dependencies": ["T03"]},
                    {"id": "T06", "name": "Structural Frame", "duration": 14, "dependencies": ["T04", "T05"]},
                ],
            }
        }
    }


# ── Response models ────────────────────────────────────────────────────────────


class TaskScheduled(BaseModel):
    """Per-task CPM result including all four time parameters and float."""

    id: str
    name: str
    duration: int
    dependencies: list[str]
    # CPM time parameters (all in working days, 0-based)
    early_start: int = Field(..., description="Earliest day the task can begin.")
    early_finish: int = Field(..., description="Earliest day the task can complete (ES + duration).")
    late_start: int = Field(..., description="Latest day the task can begin without delaying the project.")
    late_finish: int = Field(..., description="Latest day the task can complete without delaying the project.")
    total_float: int = Field(..., description="Days of scheduling slack. 0 = on the critical path.")
    is_critical: bool = Field(..., description="True when total_float == 0.")


class GanttBar(BaseModel):
    """
    Ready-to-render Gantt bar record.

    ``start_day`` and ``end_day`` are 0-based working-day indices.
    Multiply by (milliseconds per day) on the frontend to convert to calendar dates.
    """

    id: str
    name: str
    start_day: int
    end_day: int
    duration: int
    is_critical: bool
    dependencies: list[str]


class ScheduleResponse(BaseModel):
    project_name: str
    project_duration_days: int = Field(..., description="Total project duration (critical path length).")
    critical_path_ids: list[str] = Field(..., description="Task IDs on the critical path, in execution order.")
    critical_path_names: list[str] = Field(..., description="Human-readable names matching critical_path_ids.")
    tasks: list[TaskScheduled]
    gantt: list[GanttBar] = Field(..., description="Pre-shaped list for Gantt chart rendering.")


# ── CPM engine ─────────────────────────────────────────────────────────────────


def _run_cpm(request: ScheduleRequest) -> ScheduleResponse:
    """
    Execute a full CPM analysis over the task Directed Acyclic Graph.

    Algorithm
    ─────────
    1. Build a networkx DiGraph.  Each edge dep → task represents a
       Finish-to-Start dependency.
    2. Verify the graph is acyclic (raises HTTP 422 if not).
    3. Forward pass (topological order):
           ES[v] = max(EF[u] for u in predecessors(v)),  default 0
           EF[v] = ES[v] + duration[v]
    4. Backward pass (reverse topological order):
           LF[v] = min(LS[w] for w in successors(v)),  default = project_duration
           LS[v] = LF[v] − duration[v]
    5. Total float = LS[v] − ES[v].  Nodes with float == 0 are critical.
    """
    # ── Build graph ────────────────────────────────────────────────────────────
    G: nx.DiGraph = nx.DiGraph()
    for t in request.tasks:
        G.add_node(t.id, name=t.name, duration=t.duration)
    for t in request.tasks:
        for dep in t.dependencies:
            G.add_edge(dep, t.id)   # dep must finish before t starts

    if not nx.is_directed_acyclic_graph(G):
        # Find the cycle for a helpful error message
        try:
            cycle = nx.find_cycle(G)
            cycle_ids = " → ".join(f"'{u}'" for u, _ in cycle)
        except Exception:
            cycle_ids = "(see task definitions)"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The task dependency graph contains a cycle and cannot be scheduled. "
                f"Detected cycle: {cycle_ids}. "
                "CPM requires a Directed Acyclic Graph (DAG). "
                "Remove the circular dependency to proceed."
            ),
        )

    topo: list[str] = list(nx.topological_sort(G))

    # ── Forward pass: Early Start / Early Finish ───────────────────────────────
    ES: dict[str, int] = {}
    EF: dict[str, int] = {}
    for nid in topo:
        dur = G.nodes[nid]["duration"]
        preds = list(G.predecessors(nid))
        es = max((EF[p] for p in preds), default=0)
        ES[nid] = es
        EF[nid] = es + dur

    project_duration: int = max(EF.values())

    # ── Backward pass: Late Start / Late Finish ────────────────────────────────
    LS: dict[str, int] = {}
    LF: dict[str, int] = {}
    for nid in reversed(topo):
        dur = G.nodes[nid]["duration"]
        succs = list(G.successors(nid))
        lf = min((LS[s] for s in succs), default=project_duration)
        LF[nid] = lf
        LS[nid] = lf - dur

    # ── Float and critical path ────────────────────────────────────────────────
    total_float: dict[str, int] = {nid: LS[nid] - ES[nid] for nid in G.nodes}
    critical_ids: list[str] = [nid for nid in topo if total_float[nid] == 0]

    # ── Assemble response ──────────────────────────────────────────────────────
    task_map = {t.id: t for t in request.tasks}

    tasks_out: list[TaskScheduled] = [
        TaskScheduled(
            id=nid,
            name=G.nodes[nid]["name"],
            duration=G.nodes[nid]["duration"],
            dependencies=task_map[nid].dependencies,
            early_start=ES[nid],
            early_finish=EF[nid],
            late_start=LS[nid],
            late_finish=LF[nid],
            total_float=total_float[nid],
            is_critical=total_float[nid] == 0,
        )
        for nid in topo
    ]

    gantt: list[GanttBar] = [
        GanttBar(
            id=t.id,
            name=t.name,
            start_day=t.early_start,
            end_day=t.early_finish,
            duration=t.duration,
            is_critical=t.is_critical,
            dependencies=t.dependencies,
        )
        for t in tasks_out
    ]

    logger.info(
        "CPM complete | project='%s' tasks=%d duration=%d days critical_tasks=%d",
        request.project_name,
        len(tasks_out),
        project_duration,
        len(critical_ids),
    )

    return ScheduleResponse(
        project_name=request.project_name,
        project_duration_days=project_duration,
        critical_path_ids=critical_ids,
        critical_path_names=[G.nodes[nid]["name"] for nid in critical_ids],
        tasks=tasks_out,
        gantt=gantt,
    )


# ── Route ──────────────────────────────────────────────────────────────────────


@router.post(
    "/schedule",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK,
    summary="CPM critical-path schedule",
    description=(
        "Accepts a list of construction tasks with durations and Finish-to-Start "
        "dependencies.  Executes a CPM forward **and** backward pass using "
        "**networkx** and returns:\n\n"
        "- Per-task **Early Start / Early Finish / Late Start / Late Finish / Total Float**\n"
        "- **Critical path** task list (tasks with zero float)\n"
        "- `gantt` — a pre-shaped list for direct Gantt chart rendering "
        "(start_day, end_day, is_critical)\n\n"
        "Returns **HTTP 422** if the dependency graph contains a cycle or if any "
        "dependency ID does not match an existing task."
    ),
)
async def create_schedule(body: ScheduleRequest) -> ScheduleResponse:
    return _run_cpm(body)


# ══════════════════════════════════════════════════════════════════════════════
# §2  BILL OF QUANTITIES  –  Cost Aggregation  (pandas)
# ══════════════════════════════════════════════════════════════════════════════

# ── Request models ─────────────────────────────────────────────────────────────


class BOQItem(BaseModel):
    """A single line item in the Bill of Quantities."""

    code: str = Field(..., description="Unique item code, e.g. 'CON-001'. Used to match live rates.")
    description: str = Field(..., description="Full item description, e.g. 'Grade 30 Concrete – Columns'.")
    trade: str = Field(
        ...,
        description="Trade / work-package category, e.g. 'Concrete Works', 'Masonry', 'Finishes'.",
    )
    unit: str = Field(..., description="Unit of measurement, e.g. 'm³', 'm²', 'kg', 'nr'.")
    quantity: float = Field(..., gt=0, description="Measured quantity in the stated unit.")
    unit_rate_lkr: float | None = Field(
        None,
        ge=0,
        description=(
            "Unit rate in LKR.  "
            "Set to null to have the rate populated by the live market-rate scraper "
            "(see _fetch_live_rates hook).  Items with null rates are excluded from "
            "cost totals and flagged as PENDING_SCRAPE."
        ),
    )
    market_rate_source: str | None = Field(
        None,
        description=(
            "Optional URL or source name for the rate (e.g. supplier portal). "
            "Populated automatically by the scraper once _fetch_live_rates is implemented."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": "CON-001",
                "description": "Grade 30 Structural Concrete – Suspended Slabs",
                "trade": "Concrete Works",
                "unit": "m³",
                "quantity": 45.5,
                "unit_rate_lkr": 38500.00,
                "market_rate_source": None,
            }
        }
    }


class BOQRequest(BaseModel):
    project_name: str = Field(..., min_length=1)
    items: list[BOQItem] = Field(..., min_length=1)
    contingency_pct: float = Field(
        default=10.0,
        ge=0,
        le=100,
        description=(
            "Contingency allowance as a percentage of the net cost subtotal. "
            "Default is 10%, which is the standard ICTAD allowance for Sri Lankan projects."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "project_name": "Office Block – Phase 1",
                "contingency_pct": 10.0,
                "items": [
                    {"code": "SITE-001", "description": "Site Clearing & Grubbing", "trade": "Preliminaries", "unit": "m²", "quantity": 500, "unit_rate_lkr": 350},
                    {"code": "CON-001",  "description": "Grade 30 Concrete – Footings", "trade": "Concrete Works", "unit": "m³", "quantity": 28, "unit_rate_lkr": 38500},
                    {"code": "CON-002",  "description": "Grade 25 Concrete – Slab", "trade": "Concrete Works", "unit": "m³", "quantity": 55, "unit_rate_lkr": None},
                    {"code": "MAS-001",  "description": "115mm Brick Wall", "trade": "Masonry", "unit": "m²", "quantity": 320, "unit_rate_lkr": 2800},
                    {"code": "FIN-001",  "description": "Internal Plaster 12mm", "trade": "Finishes", "unit": "m²", "quantity": 640, "unit_rate_lkr": 750},
                ],
            }
        }
    }


# ── Response models ────────────────────────────────────────────────────────────


class BOQTradeSubtotal(BaseModel):
    """Aggregated cost for one trade / work-package."""

    trade: str
    item_count: int
    subtotal_lkr: float


class BOQResponseItem(BaseModel):
    """BOQ line item enriched with computed totals and rate-status flag."""

    code: str
    description: str
    trade: str
    unit: str
    quantity: float
    unit_rate_lkr: float | None
    total_lkr: float | None = Field(None, description="quantity × unit_rate_lkr. Null when rate is missing.")
    market_rate_source: str | None
    rate_status: str = Field(..., description="'PROVIDED' or 'PENDING_SCRAPE'.")


class BOQResponse(BaseModel):
    project_name: str
    items: list[BOQResponseItem]
    trade_subtotals: list[BOQTradeSubtotal]
    subtotal_lkr: float = Field(..., description="Net cost of all items with known rates.")
    contingency_pct: float
    contingency_lkr: float
    grand_total_lkr: float
    items_pending_rates: list[str] = Field(..., description="Codes of items flagged PENDING_SCRAPE.")
    market_rate_note: str


# ══════════════════════════════════════════════════════════════════════════════
# PLACEHOLDER: Live market-rate injection via BeautifulSoup
# ──────────────────────────────────────────────────────────────────────────────
#
# HOW TO COMPLETE THIS HOOK (future sprint):
#
#   1. Add to requirements.txt:
#          httpx>=0.27.0
#          beautifulsoup4>=4.12.0
#
#   2. Confirm the LKR rate source URL(s), e.g.:
#          RATE_PORTAL_URL = "https://example-supplier.lk/material-rates"
#
#   3. Replace the stub body of _fetch_live_rates() below with:
#
#          import httpx
#          from bs4 import BeautifulSoup
#
#          async with httpx.AsyncClient(timeout=10.0) as client:
#              resp = await client.get(RATE_PORTAL_URL)
#              resp.raise_for_status()
#              soup = BeautifulSoup(resp.text, "html.parser")
#
#              rates: dict[str, float] = {}
#              for row in soup.select("table.rate-table tr"):
#                  cells = row.find_all("td")
#                  if len(cells) >= 3:
#                      code = cells[0].get_text(strip=True)
#                      if code in material_codes:
#                          rates[code] = float(cells[2].get_text(strip=True).replace(",", ""))
#              return rates
#
#   4. The calling code in _aggregate_boq() is already wired to receive and
#      apply the returned dict — no further changes needed there.
#
# ══════════════════════════════════════════════════════════════════════════════


async def _fetch_live_rates(material_codes: list[str]) -> dict[str, float]:
    """
    Stub: BeautifulSoup live market-rate scraper.

    Returns an empty dict until the scraping logic is implemented.
    Items remain at their provided ``unit_rate_lkr``, or are flagged as
    ``PENDING_SCRAPE`` if their rate is null.

    See the PLACEHOLDER comment block above for full implementation instructions.
    """
    # TODO: implement real scraping — see PLACEHOLDER block above.
    logger.debug(
        "_fetch_live_rates called for %d code(s) — stub returning empty dict.",
        len(material_codes),
    )
    return {}


# ── BOQ aggregation engine ─────────────────────────────────────────────────────


async def _aggregate_boq(request: BOQRequest) -> BOQResponse:
    """
    Aggregate the BOQ using pandas.

    Steps
    ─────
    1. Build a DataFrame from the request items.
    2. Call _fetch_live_rates() for any item with unit_rate_lkr = null.
       (stub today; real scraping injected in a future sprint)
    3. Compute per-item total_lkr = quantity × unit_rate_lkr.
    4. Group by trade and sum subtotals.
    5. Compute net subtotal, contingency, and grand total.
    """
    rows = [item.model_dump() for item in request.items]
    df = pd.DataFrame(rows)

    # ── HOOK: inject live market rates for items without a provided rate ────────
    pending_before: list[str] = df.loc[df["unit_rate_lkr"].isna(), "code"].tolist()
    if pending_before:
        live_rates = await _fetch_live_rates(pending_before)
        for code, rate in live_rates.items():
            df.loc[df["code"] == code, "unit_rate_lkr"] = rate
            df.loc[df["code"] == code, "market_rate_source"] = "scraped"
    # ── END HOOK ────────────────────────────────────────────────────────────────

    # Per-item totals (NaN propagates naturally for still-missing rates)
    df["total_lkr"] = df["quantity"] * df["unit_rate_lkr"]

    # Rate-status flag: checked AFTER the hook so scraped items show PROVIDED
    df["rate_status"] = df["unit_rate_lkr"].apply(
        lambda r: "PENDING_SCRAPE"
        if r is None or (isinstance(r, float) and math.isnan(r))
        else "PROVIDED"
    )

    # Refresh pending list after hook
    items_pending: list[str] = df.loc[df["rate_status"] == "PENDING_SCRAPE", "code"].tolist()

    # Safe totals for aggregation (0 for missing-rate items; they are flagged separately)
    df["total_lkr_safe"] = df["total_lkr"].fillna(0.0)

    # ── Trade-level aggregation ────────────────────────────────────────────────
    trade_agg = (
        df.groupby("trade", sort=False)
        .agg(item_count=("code", "count"), subtotal_lkr=("total_lkr_safe", "sum"))
        .reset_index()
    )
    trade_subtotals: list[BOQTradeSubtotal] = [
        BOQTradeSubtotal(
            trade=str(row["trade"]),
            item_count=int(row["item_count"]),
            subtotal_lkr=round(float(row["subtotal_lkr"]), 2),
        )
        for _, row in trade_agg.iterrows()
    ]

    subtotal_lkr    = round(float(df["total_lkr_safe"].sum()), 2)
    contingency_lkr = round(subtotal_lkr * request.contingency_pct / 100.0, 2)
    grand_total_lkr = round(subtotal_lkr + contingency_lkr, 2)

    # ── Build output items (NaN → None for JSON safety) ────────────────────────
    def _nan_to_none(val: Any) -> Any:
        if isinstance(val, float) and math.isnan(val):
            return None
        return val

    items_out: list[BOQResponseItem] = [
        BOQResponseItem(
            code=str(row["code"]),
            description=str(row["description"]),
            trade=str(row["trade"]),
            unit=str(row["unit"]),
            quantity=float(row["quantity"]),
            unit_rate_lkr=_nan_to_none(row["unit_rate_lkr"]),
            total_lkr=_nan_to_none(row["total_lkr"]),
            market_rate_source=row.get("market_rate_source"),
            rate_status=str(row["rate_status"]),
        )
        for row in df.to_dict(orient="records")
    ]

    market_note = (
        f"{len(items_pending)} item(s) are missing unit rates and excluded from cost totals. "
        "Implement _fetch_live_rates() in cost_scheduling.py to inject live LKR rates via "
        "BeautifulSoup. See the PLACEHOLDER comment block at the top of that function for "
        "step-by-step instructions."
        if items_pending
        else "All item rates are provided; cost totals are complete."
    )

    logger.info(
        "BOQ complete | project='%s' items=%d subtotal=LKR%.2f grand_total=LKR%.2f pending_rates=%d",
        request.project_name,
        len(items_out),
        subtotal_lkr,
        grand_total_lkr,
        len(items_pending),
    )

    return BOQResponse(
        project_name=request.project_name,
        items=items_out,
        trade_subtotals=trade_subtotals,
        subtotal_lkr=subtotal_lkr,
        contingency_pct=request.contingency_pct,
        contingency_lkr=contingency_lkr,
        grand_total_lkr=grand_total_lkr,
        items_pending_rates=items_pending,
        market_rate_note=market_note,
    )


# ── Route ──────────────────────────────────────────────────────────────────────


@router.post(
    "/boq",
    response_model=BOQResponse,
    status_code=status.HTTP_200_OK,
    summary="Bill-of-Quantities cost aggregation",
    description=(
        "Accepts a Bill of Quantities and aggregates costs by trade using **pandas**.\n\n"
        "**Rate handling**:\n"
        "- Items with `unit_rate_lkr` provided → immediately included in totals.\n"
        "- Items with `unit_rate_lkr = null` → passed to the `_fetch_live_rates()` "
        "BeautifulSoup scraper hook. If the stub returns nothing (current behaviour), "
        "they are flagged `PENDING_SCRAPE` and excluded from totals.\n\n"
        "**Output includes**:\n"
        "- Per-item totals and rate-status flags\n"
        "- Trade-level subtotals\n"
        "- Net subtotal, configurable contingency allowance, and grand total\n\n"
        "**Microservice integration**: compose with the `/compliance/roadmap` permit fees "
        "to produce a complete construction cost summary."
    ),
)
async def create_boq(body: BOQRequest) -> BOQResponse:
    return await _aggregate_boq(body)


# ══════════════════════════════════════════════════════════════════════════════
# §3  LIFECYCLE DEGRADATION PREDICTOR  –  ML model inference
# ══════════════════════════════════════════════════════════════════════════════
#
# Model artefact : backend/weights/lifecycle_model.pkl  (XGBoost / sklearn)
# Service        : app/services/lifecycle_service.py
#
# Feature contract (placeholder – adjust to match your actual trained model):
#   material_quality        int   1–10
#   environmental_harshness int   1–10
#   soil_acidity            float pH 3.0–9.0
#   maintenance_frequency   int   1–12 months interval
#
# Risk bands (derived from predicted lifespan):
#   < 30 years → High   |  30–50 years → Medium   |  > 50 years → Low
# ══════════════════════════════════════════════════════════════════════════════

from app.services.lifecycle_service import (   # noqa: E402
    LifecycleModelNotAvailableError,
    LifecycleDegradationService,
    lifecycle_service as _lifecycle_service,
)

# ── QS expert recommendations by risk level ────────────────────────────────────

_QS_ADVISORY: dict[str, str] = {
    "High": (
        "URGENT — Predicted structural lifespan is critically short (under 30 years). "
        "Engage a registered Structural Engineer and Quantity Surveyor immediately for a "
        "full condition survey and Whole Life Cost (WLC) assessment. Significant capital "
        "remediation should be budgeted at 12–18% of the current replacement value. "
        "Prioritise waterproofing, load-bearing element repairs, and anti-corrosion "
        "treatment. Failure to act will escalate costs exponentially within 5 years."
    ),
    "Medium": (
        "CAUTION — Predicted structural lifespan falls within the 30–50 year moderate "
        "degradation band. Commission a professional condition survey within the next "
        "2 years. Increase maintenance frequency and budget 5–8% of construction value "
        "for preventive works over the next 10-year period. Address drainage deficiencies, "
        "joint sealant renewal, and any surface coating failures promptly to avoid "
        "escalation into the high-risk category."
    ),
    "Low": (
        "SATISFACTORY — Predicted structural lifespan exceeds 50 years. Maintain the "
        "standard inspection programme (annual visual survey + 5-year professional "
        "condition review). Budget 1–3% of construction value per annum for routine "
        "upkeep including cleaning, minor repairs, and preventive coating maintenance. "
        "No immediate capital remediation is anticipated. Review this assessment if "
        "the usage pattern, loading, or environmental exposure changes materially."
    ),
}


# ── FastAPI dependency ─────────────────────────────────────────────────────────


def get_lifecycle_service() -> LifecycleDegradationService:
    """Inject the lifecycle service — override in tests via dependency_overrides."""
    return _lifecycle_service


# ── Request schema ─────────────────────────────────────────────────────────────


class LifecyclePredictionRequest(BaseModel):
    """
    Placeholder feature set for the lifecycle degradation prediction model.

    These four numeric features are used for initial testing.  Update the
    field names, types, and valid ranges once your final model is trained —
    the feature vector in ``lifecycle_service.predict()`` must be updated
    to match the training pipeline exactly.
    """

    material_quality: int = Field(
        ...,
        ge=1,
        le=10,
        description=(
            "Overall quality of the primary structural material on a 1–10 scale. "
            "1 = severely degraded / very poor quality; 10 = brand-new / premium grade."
        ),
        examples=[7],
    )
    environmental_harshness: int = Field(
        ...,
        ge=1,
        le=10,
        description=(
            "Severity of the environmental exposure on a 1–10 scale. "
            "1 = mild inland conditions; 10 = extreme coastal / industrial / cyclone zone."
        ),
        examples=[6],
    )
    soil_acidity: float = Field(
        ...,
        ge=3.0,
        le=9.0,
        description=(
            "Site soil pH. Strongly acidic soils (pH < 5.5) accelerate foundation "
            "and sub-structure corrosion. Neutral = 7.0."
        ),
        examples=[6.5],
    )
    maintenance_frequency: int = Field(
        ...,
        ge=1,
        le=12,
        description=(
            "Interval between planned maintenance visits in months. "
            "1 = monthly (highest frequency); 12 = once per year (lowest)."
        ),
        examples=[6],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "material_quality": 7,
                "environmental_harshness": 6,
                "soil_acidity": 6.5,
                "maintenance_frequency": 6,
            }
        }
    }


# ── Response schema ────────────────────────────────────────────────────────────


class LifecyclePredictionResponse(BaseModel):
    estimated_lifespan_years: float = Field(
        ...,
        description="Predicted structural lifespan in years (clipped to [1, 200]).",
    )
    risk_level: str = Field(
        ...,
        description="'High' (< 30 yrs) | 'Medium' (30–50 yrs) | 'Low' (> 50 yrs).",
    )
    expert_recommendation: str = Field(
        ...,
        description=(
            "QS-perspective advisory tailored to the derived risk level, "
            "with indicative budget guidance."
        ),
    )
    model_confidence: float | None = Field(
        None,
        description=(
            "Probability confidence in [0, 1] when the model exposes predict_proba. "
            "Null for pure regression models."
        ),
    )
    input_echo: dict = Field(
        ...,
        description="Echo of the request fields for easy audit in the response payload.",
    )


# ── Route ──────────────────────────────────────────────────────────────────────


@router.post(
    "/predict-lifecycle",
    response_model=LifecyclePredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Lifecycle degradation prediction",
    description=(
        "Predicts the estimated structural lifespan and degradation risk level "
        "for a construction asset using the pre-trained **lifecycle_model.pkl** "
        "XGBoost / scikit-learn estimator.\n\n"
        "**Features (placeholder)**: material quality, environmental harshness, "
        "soil acidity, and maintenance frequency.\n\n"
        "**Risk bands**: High (< 30 yrs) · Medium (30–50 yrs) · Low (> 50 yrs).\n\n"
        "**HTTP 503** is returned if ``lifecycle_model.pkl`` is absent from "
        "``backend/weights/`` — the server continues to serve all other endpoints."
    ),
)
async def predict_lifecycle(
    body: LifecyclePredictionRequest,
    svc: Annotated[LifecycleDegradationService, Depends(get_lifecycle_service)],
) -> LifecyclePredictionResponse:
    # ── Model availability guard ───────────────────────────────────────────────
    if not svc.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Lifecycle degradation model is not available. "
                f"{svc.load_error or 'Place lifecycle_model.pkl in backend/weights/ and restart.'}"
            ),
        )

    # ── Run prediction ─────────────────────────────────────────────────────────
    try:
        prediction = svc.predict(
            material_quality=body.material_quality,
            environmental_harshness=body.environmental_harshness,
            soil_acidity=body.soil_acidity,
            maintenance_frequency=body.maintenance_frequency,
        )
    except LifecycleModelNotAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except RuntimeError as exc:
        # model.predict() raised — surface as 500 with actionable detail
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected prediction error: {exc}",
        )

    advisory = _QS_ADVISORY.get(
        prediction.risk_level,
        "Engage a certified engineer for a full condition survey.",
    )

    return LifecyclePredictionResponse(
        estimated_lifespan_years=prediction.estimated_lifespan_years,
        risk_level=prediction.risk_level,
        expert_recommendation=advisory,
        model_confidence=prediction.confidence,
        input_echo={
            "material_quality": body.material_quality,
            "environmental_harshness": body.environmental_harshness,
            "soil_acidity": body.soil_acidity,
            "maintenance_frequency": body.maintenance_frequency,
        },
    )

