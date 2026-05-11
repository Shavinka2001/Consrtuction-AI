"""
ConstructAI – self-contained FastAPI entry point.

Run from the backend/ directory:
    uvicorn main:app --reload --host 127.0.0.1 --port 8000

All routes, auth, and YOLO inference live in this single file so that the
server can be started without the 'app.' package prefix.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List

import jwt
import torch
from dotenv import load_dotenv
from google import genai
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from ultralytics import YOLO

from app.routers.cost_scheduling import router as cost_router
from app.services.lifecycle_service import lifecycle_service as _lifecycle_service

# Load .env from the same directory as this file so it works regardless of CWD.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _get_gemini_client() -> "genai.Client":
    """Lazily create the Gemini client so a missing key never crashes startup."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server.",
        )
    return genai.Client(api_key=api_key)

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── JWT configuration ──────────────────────────────────────────────────────────

JWT_SECRET_KEY: str = os.getenv(
    "JWT_SECRET_KEY", "constructai-dev-secret-CHANGE-in-production"
)
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS: int = 2

# ── Paths ──────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent          # …/backend/
WEIGHTS_PATH = _ROOT / "weights" / "best.pt"
UPLOAD_DIR   = _ROOT / "tmp" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── SQLite database ────────────────────────────────────────────────────────────

DB_PATH = _ROOT / "users.db"

# ── Password hashing ───────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ── DB helpers ─────────────────────────────────────────────────────────────────


def _get_db() -> sqlite3.Connection:
    """Open a connection to users.db with Row factory for dict-like access."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# Default users seeded once into the DB (plain-text passwords are hashed below).
_DEFAULT_USERS: list[dict] = [
    {"username": "admin",      "password": "123", "role": "Project Manager",    "email": "admin@constructai.local"},
    {"username": "site_eng",   "password": "123", "role": "Site Engineer",      "email": "site_eng@constructai.local"},
    {"username": "architect",  "password": "123", "role": "Architect",          "email": "architect@constructai.local"},
    {"username": "qa_officer", "password": "123", "role": "Compliance Officer", "email": "qa_officer@constructai.local"},
    {"username": "qs_planner", "password": "123", "role": "Quantity Surveyor",  "email": "qs_planner@constructai.local"},
]


def _init_db() -> None:
    """Create the users table and seed default accounts (idempotent)."""
    with _get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role     TEXT NOT NULL,
                email    TEXT
            )
            """
        )
        for u in _DEFAULT_USERS:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (username, password, role, email)
                VALUES (?, ?, ?, ?)
                """,
                (u["username"], _hash_password(u["password"]), u["role"], u["email"]),
            )
        conn.commit()
    logger.info("SQLite users.db initialised at %s", DB_PATH)

# ── FastAPI app ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    _init_db()
    # Load lifecycle degradation model (safe — logs warning and stays disabled if .pkl absent)
    _lifecycle_service.load()
    yield


app = FastAPI(
    title="ConstructAI API",
    description="AI-powered construction site analysis backend.",
    version="0.1.0",
    lifespan=_lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Starlette raises a ValueError if allow_origins=["*"] and
# allow_credentials=True are combined (CORS spec forbids it).
# We instead list the Next.js dev origins explicitly; add more via the
# CORS_ORIGINS env var (comma-separated) for staging / production.

_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security scheme (shown in Swagger UI) ─────────────────────────────────────

_bearer = HTTPBearer(auto_error=True)


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class BBoxSchema(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class DetectionSchema(BaseModel):
    class_id:   int
    class_name: str
    confidence: float
    bbox:       BBoxSchema


class AnalysisResponse(BaseModel):
    success:          bool
    filename:         str
    total_detections: int
    detections:       List[DetectionSchema]


class RegisterRequest(BaseModel):
    username: str
    email:    str
    password: str
    role:     str


class RegisterResponse(BaseModel):
    message:  str
    username: str
    role:     str


class ClashDetails(BaseModel):
    className: str
    x: float
    y: float
    severity: str


# ── YOLO model singleton ───────────────────────────────────────────────────────
# The model is loaded lazily on the first inference request and then reused
# for every subsequent call, avoiding the expensive per-request load.

_yolo_model: YOLO | None = None


def _get_yolo() -> YOLO:
    global _yolo_model
    if _yolo_model is None:
        if not WEIGHTS_PATH.exists():
            raise FileNotFoundError(
                f"YOLO weights not found at '{WEIGHTS_PATH}'. "
                "Place your trained best.pt inside backend/weights/."
            )
        logger.info("Loading YOLO model from %s …", WEIGHTS_PATH)
        _yolo_model = YOLO(str(WEIGHTS_PATH))
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _yolo_model.to(device)
        logger.info("YOLO model ready on device: %s", device)
    return _yolo_model


# ── Auth helpers ───────────────────────────────────────────────────────────────


def _create_token(sub: str, role: str) -> str:
    """Encode a signed JWT that expires after JWT_EXPIRY_HOURS hours."""
    payload = {
        "sub":  sub,
        "role": role,
        "exp":  datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat":  datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """
    FastAPI dependency – validates the Bearer token on every protected route.
    Returns the decoded JWT payload dict (contains 'sub', 'role', etc.).
    """
    token = credentials.credentials
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Component 4: Cost & Scheduling Microservice ────────────────────────────────
# Registered here so require_auth (defined above) is already in scope.
# Auth is applied at the router level — the router module itself is stateless
# and has no direct dependency on any auth implementation.

app.include_router(cost_router, dependencies=[Depends(require_auth)])

# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Liveness probe — includes ML model availability status."""
    return {
        "status": "ok",
        "lifecycle_model": {
            "available": _lifecycle_service.available,
            "error":     _lifecycle_service.load_error,
        },
    }


@app.post(
    "/api/login",
    response_model=LoginResponse,
    tags=["Auth"],
    summary="Authenticate and receive a JWT access token",
)
async def login(body: LoginRequest) -> LoginResponse:
    """
    Accepts **email** + **password**, verifies against the SQLite users table,
    and returns a signed JWT valid for 2 hours alongside the user role.
    """
    with _get_db() as conn:
        row = conn.execute(
            "SELECT username, password, role FROM users WHERE email = ?",
            (body.email,),
        ).fetchone()

    # Use constant-time comparison via passlib; reject generically to avoid
    # leaking whether the email exists (OWASP A07 – Identification failures).
    if row is None or not _verify_password(body.password, row["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = _create_token(sub=row["username"], role=row["role"])
    logger.info("Login: user='%s' role='%s'", row["username"], row["role"])

    return LoginResponse(
        access_token=token,
        role=row["role"],
        username=row["username"],
    )


@app.post(
    "/api/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
    summary="Register a new user account",
)
async def register(body: RegisterRequest) -> RegisterResponse:
    """
    Creates a new user account in the SQLite users table.
    The role is provided by the caller (e.g. 'Project Manager', 'Site Engineer').
    Returns 400 if the username is already taken.
    """
    hashed_pw = _hash_password(body.password)
    try:
        with _get_db() as conn:
            conn.execute(
                """
                INSERT INTO users (username, password, role, email)
                VALUES (?, ?, ?, ?)
                """,
                (body.username, hashed_pw, body.role, body.email),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists.",
        )

    logger.info("Registered new user: '%s' role='%s'", body.username, body.role)

    return RegisterResponse(
        message=f"User '{body.username}' registered successfully.",
        username=body.username,
        role=body.role,
    )


@app.post(
    "/api/analyze-site",
    response_model=AnalysisResponse,
    tags=["Analysis"],
    summary="Run YOLOv8 inference on an uploaded construction-site image",
)
async def analyze_site(
    file: Annotated[UploadFile, File(description="Site image (JPEG / PNG / WebP)")],
    _payload: Annotated[dict, Depends(require_auth)],
) -> AnalysisResponse:
    """
    Accepts an image upload, runs YOLOv8 inference, and returns all detected
    objects with class names, confidence scores, and bounding-box coordinates.

    **Requires a valid JWT Bearer token** obtained from `/api/login`.
    """
    # ── 1. Save to a unique temp file ─────────────────────────────────────────
    suffix = Path(file.filename or "upload").suffix or ".jpg"
    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"

    try:
        contents: bytes = await file.read()
        tmp_path.write_bytes(contents)
        logger.info("Saved upload: %s (%d bytes)", tmp_path.name, len(contents))

        # ── 2. Load model (cached after first call) ───────────────────────────
        model = _get_yolo()

        # ── 3. Run inference ──────────────────────────────────────────────────
        results = model(str(tmp_path), verbose=False)

        # ── 4. Extract detections ─────────────────────────────────────────────
        detections: list[DetectionSchema] = []

        for result in results:
            if result.boxes is None:
                continue

            names: dict[int, str] = result.names   # {0: 'hardhat', 1: 'vest', …}

            for box in result.boxes:
                x_min, y_min, x_max, y_max = (
                    float(v) for v in box.xyxy[0].tolist()
                )
                confidence = float(box.conf[0])
                class_id   = int(box.cls[0])

                detections.append(
                    DetectionSchema(
                        class_id=class_id,
                        class_name=names.get(class_id, str(class_id)),
                        confidence=round(confidence, 4),
                        bbox=BBoxSchema(
                            x_min=round(x_min, 2),
                            y_min=round(y_min, 2),
                            x_max=round(x_max, 2),
                            y_max=round(y_max, 2),
                        ),
                    )
                )

        logger.info(
            "Inference complete for '%s': %d detection(s).",
            file.filename,
            len(detections),
        )

        return AnalysisResponse(
            success=True,
            filename=file.filename or tmp_path.name,
            total_detections=len(detections),
            detections=detections,
        )

    except FileNotFoundError as exc:
        logger.error("Model weights missing: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image analysis failed. Please try again.",
        )
    finally:
        # ── 5. Always delete the temp file ────────────────────────────────────
        if tmp_path.exists():
            tmp_path.unlink()
            logger.debug("Deleted temp file: %s", tmp_path.name)


# ── AI Recommendation ──────────────────────────────────────────────────────────


# ── Compliance Roadmap ─────────────────────────────────────────────────────────


class RoadmapRequest(BaseModel):
    floor_area:         int   = Field(..., gt=0,  description="Total floor area in m²")
    stories:            int   = Field(..., ge=1, le=200, description="Number of stories")
    zoning_type:        str   = Field(..., description="RESIDENTIAL | COMMERCIAL | INDUSTRIAL | MIXED_USE")
    construction_type:  str   = Field(..., description="NEW_CONSTRUCTION | EXTENSION | RENOVATION | DEMOLITION")
    project_value_lkr:  int   = Field(..., ge=0, description="Estimated project value in LKR")


class _PermitItem(BaseModel):
    id:                  str
    name:                str
    authority:           str
    icon_key:            str
    estimated_fee_lkr:   float
    min_days:            int
    max_days:            int
    mandatory:           bool
    risk_level:          str
    description:         str
    required_documents:  list[str]
    legal_reference:     str
    phase:               int


class _RiskWarning(BaseModel):
    id:                 str
    severity:           str
    title:              str
    message:            str
    penalty_lkr:        float | None = None
    daily_accrual_lkr:  float | None = None
    stop_work:          bool = False
    statute:            str | None = None
    corrective_action:  str | None = None


class _RoadmapSummary(BaseModel):
    total_permits:           int
    mandatory_count:         int
    estimated_total_fee_lkr: float
    max_timeline_days:       int
    high_risk_count:         int


class RoadmapResponse(BaseModel):
    permits:       list[_PermitItem]
    risk_alerts:   list[_RiskWarning]
    summary:       _RoadmapSummary


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


def _build_permits(area: float, stories: int, zoning: str, ctype: str) -> list[_PermitItem]:
    permits: list[_PermitItem] = []
    is_new  = ctype == "NEW_CONSTRUCTION"
    is_demo = ctype == "DEMOLITION"
    is_ext  = ctype == "EXTENSION"

    # Phase 1 ─────────────────────────────────────────────────────────────────
    # UDA Development Permission — always for new/demo, or large extensions
    if is_new or is_demo or area > 1_500 or stories > 2:
        permits.append(_PermitItem(
            id="uda", name="UDA Development Permission",
            authority="Urban Development Authority (UDA)",
            icon_key="Building2",
            estimated_fee_lkr=_uda_fee(area, zoning),
            min_days=21, max_days=60,
            mandatory=True, risk_level="HIGH", phase=1,
            description=(
                "Statutory approval from the UDA for any development within "
                "UDA-regulated zones. Required before any site preparation."
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

    # Local Authority Building Plan Approval — always required
    permits.append(_PermitItem(
        id="local-auth", name="Local Authority Building Plan Approval",
        authority="Municipal / Urban / Pradeshiya Sabha Council",
        icon_key="ClipboardCheck",
        estimated_fee_lkr=_local_authority_fee(area, zoning),
        min_days=14, max_days=45,
        mandatory=True, risk_level="HIGH", phase=1,
        description=(
            "Mandatory before any construction activity. The local authority "
            "verifies conformity with the Building Regulations 1986."
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

    # CEA Environmental Clearance — large or industrial/commercial
    if area > 500 or zoning in ("INDUSTRIAL", "COMMERCIAL"):
        fee_tier = 150_000 if area > 2_000 else 75_000 if area > 500 else 50_000
        permits.append(_PermitItem(
            id="cea", name="CEA Environmental Clearance",
            authority="Central Environmental Authority (CEA)",
            icon_key="Leaf",
            estimated_fee_lkr=fee_tier,
            min_days=30, max_days=90,
            mandatory=zoning == "INDUSTRIAL", risk_level="HIGH", phase=1,
            description=(
                "Projects above 500 m² or in industrial/commercial zones require "
                "an environmental screening or Initial Environmental Examination (IEE)."
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

    # RDA Road Access Permit — commercial, industrial, or large site
    if zoning in ("COMMERCIAL", "INDUSTRIAL") or area > 1_000:
        permits.append(_PermitItem(
            id="rda", name="Road Access / Deviation Permit",
            authority="Road Development Authority (RDA)",
            icon_key="Map",
            estimated_fee_lkr=100_000 if zoning == "INDUSTRIAL" else 45_000,
            min_days=14, max_days=30,
            mandatory=False, risk_level="MEDIUM", phase=1,
            description=(
                "Required when construction affects a national road, access "
                "deviation, or hoarding on a road reserve."
            ),
            required_documents=[
                "Site location plan",
                "Traffic impact assessment",
                "Proposed road access layout",
                "RDA application form",
            ],
            legal_reference="Road Development Authority Act No. 73 of 1981, Section 8",
        ))

    # Phase 2 ─────────────────────────────────────────────────────────────────
    if stories >= 3 or area > 1_000 or zoning in ("COMMERCIAL", "INDUSTRIAL"):
        permits.append(_PermitItem(
            id="fire", name="Fire Safety Certificate",
            authority="Sri Lanka Fire Department / District Fire Brigade",
            icon_key="Flame",
            estimated_fee_lkr=_fire_safety_fee(area, stories),
            min_days=10, max_days=30,
            mandatory=stories >= 3 or zoning == "COMMERCIAL",
            risk_level="HIGH" if stories >= 5 else "MEDIUM",
            phase=2,
            description=(
                "Issued after inspection of fire suppression systems, emergency "
                "exits, fire-rated doors, and fire detection installations."
            ),
            required_documents=[
                "Fire protection system drawings",
                "Fire compartmentation plan",
                "Sprinkler system layout",
                "Emergency evacuation plan",
                "Hydrant installation certificate",
            ],
            legal_reference="Fire Services Act No. 24 of 1974; SLSI SLS 1390",
        ))

    if is_new or is_ext:
        permits.append(_PermitItem(
            id="electrical", name="Electrical Supply Connection Approval",
            authority="LECO / Ceylon Electricity Board (CEB)",
            icon_key="Zap",
            estimated_fee_lkr=45_000 if stories >= 3 else 20_000,
            min_days=7, max_days=21,
            mandatory=True, risk_level="MEDIUM", phase=2,
            description="Approval for new electrical supply connection and metering installation.",
            required_documents=[
                "Electrical installation drawings",
                "Single-line diagram",
                "Load calculation sheet",
                "Registered electrical contractor certification",
                "Completed CEB/LECO application form",
            ],
            legal_reference="Electricity Act No. 20 of 2009, Section 44; BS 7671",
        ))
        permits.append(_PermitItem(
            id="water", name="Water Supply & Drainage Connection",
            authority="National Water Supply & Drainage Board (NWSDB)",
            icon_key="Droplets",
            estimated_fee_lkr=25_000,
            min_days=10, max_days=25,
            mandatory=True, risk_level="MEDIUM", phase=2,
            description="Connection approval for potable water supply and sewage/drainage tie-in.",
            required_documents=[
                "Plumbing layout drawings",
                "Sewage disposal plan",
                "Water demand calculation",
                "NWSDB application form",
            ],
            legal_reference="National Water Supply & Drainage Board Law No. 2 of 1974, Section 15",
        ))

    # Phase 3 ─────────────────────────────────────────────────────────────────
    permits.append(_PermitItem(
        id="coc", name="Certificate of Conformity (CoC)",
        authority="Local Authority / Chartered Engineer",
        icon_key="BadgeCheck",
        estimated_fee_lkr=15_000,
        min_days=7, max_days=21,
        mandatory=True, risk_level="HIGH", phase=3,
        description=(
            "Issued after final inspection confirms that all completed work "
            "conforms to the approved plans and building regulations."
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
        permits.append(_PermitItem(
            id="occupancy", name="Certificate of Occupancy",
            authority="Local Authority / UDA",
            icon_key="HardHat",
            estimated_fee_lkr=20_000,
            min_days=14, max_days=30,
            mandatory=True, risk_level="HIGH", phase=3,
            description=(
                "Authorises legal occupation of the building. Issued only after all "
                "Phase 1 & 2 clearances and the CoC are in order."
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


# ── Risk-warning builder ───────────────────────────────────────────────────────


def _build_risk_warnings(
    area: float, stories: int, zoning: str, ctype: str, value: float
) -> list[_RiskWarning]:
    warnings: list[_RiskWarning] = []

    if stories >= 5:
        warnings.append(_RiskWarning(
            id="risk-highrise", severity="HIGH",
            title="High-Rise Building — Multi-Authority Coordination Required",
            message=(
                f"Buildings of {stories} stories require simultaneous coordination across "
                "UDA, Local Authority, Fire Department, and LECO. Fire safety inspections "
                "are mandatory at multiple construction stages."
            ),
            penalty_lkr=round(value * 0.10) if value > 0 else 1_000_000,
            daily_accrual_lkr=10_000, stop_work=False,
            statute="Fire Services Act No. 24 of 1974; UDA Law No. 41 of 1978",
            corrective_action=(
                "Appoint a dedicated Compliance Manager. Prepare a parallel permit "
                "submission schedule to minimise critical-path delays."
            ),
        ))

    if zoning == "INDUSTRIAL":
        warnings.append(_RiskWarning(
            id="risk-industrial-cea", severity="HIGH",
            title="Industrial Zone — CEA Environmental Clearance is Mandatory",
            message=(
                "All industrial developments require a mandatory Initial Environmental "
                "Examination (IEE) from the CEA. The review process takes 30–90 days "
                "and is a hard blocker for foundation work."
            ),
            penalty_lkr=500_000, daily_accrual_lkr=5_000, stop_work=False,
            statute="National Environmental Act No. 47 of 1980, Section 23(cc)",
            corrective_action=(
                "Commission an IEE from a registered environmental consultant before "
                "any other permit submission."
            ),
        ))

    if ctype == "DEMOLITION":
        warnings.append(_RiskWarning(
            id="risk-demolition", severity="HIGH",
            title="Demolition Works — Hazardous Materials Survey Required",
            message=(
                "A hazardous materials survey (including asbestos) is required before "
                "any demolition activity. Unauthorised demolition without UDA approval "
                "can result in immediate stop-work and prosecution."
            ),
            penalty_lkr=750_000, daily_accrual_lkr=7_500, stop_work=True,
            statute="UDA Law No. 41 of 1978, Section 14; Factory Ordinance No. 45 of 1942",
            corrective_action=(
                "Obtain UDA Development Permission and a hazardous materials survey "
                "report before commencing any demolition."
            ),
        ))

    if area > 1_500 or stories > 2:
        warnings.append(_RiskWarning(
            id="risk-uda-required", severity="HIGH",
            title="UDA Development Permission Required",
            message=(
                f"Your project ({area:,.0f} m², {stories} stor{'y' if stories == 1 else 'ies'}) "
                "exceeds the UDA threshold. Development Permission must be obtained "
                "before any site preparation or construction commences."
            ),
            penalty_lkr=round(value * 0.10) if value > 0 else 500_000,
            daily_accrual_lkr=5_000, stop_work=False,
            statute="Urban Development Authority Law No. 41 of 1978, Section 14",
            corrective_action=(
                "Submit UDA Development Permission application immediately. "
                "Do not commence site clearing or excavation until approval is granted."
            ),
        ))

    if area > 2_000 and zoning == "COMMERCIAL":
        warnings.append(_RiskWarning(
            id="risk-large-commercial", severity="MEDIUM",
            title="Large Commercial Development — Extended Review Timelines",
            message=(
                f"Commercial projects exceeding 2,000 m² (your project: {area:,.0f} m²) "
                "typically face extended CEA and RDA review periods. Both must be resolved "
                "before construction commences."
            ),
            penalty_lkr=250_000, stop_work=False,
            statute="National Environmental Act No. 47 of 1980; RDA Act No. 73 of 1981",
            corrective_action=(
                "Begin CEA and RDA applications simultaneously at project kick-off."
            ),
        ))

    if ctype == "NEW_CONSTRUCTION" and stories >= 3:
        warnings.append(_RiskWarning(
            id="risk-multi-story-structural", severity="MEDIUM",
            title="Multi-Story Structure — Soil & Structural Design Certification Required",
            message=(
                f"Your {stories}-story building requires a certified Soil Test Report and "
                "Structural Design Calculation submitted alongside the Local Authority "
                "application. Missing these delays approval by 2–4 weeks."
            ),
            stop_work=False,
            statute="Building Regulations 1986, Section 23; ICTAD SCA/2",
            corrective_action=(
                "Commission a soil investigation report and engage a Chartered Structural "
                "Engineer at the design stage."
            ),
        ))

    return warnings


@app.post(
    "/api/v1/compliance/roadmap",
    response_model=RoadmapResponse,
    tags=["Compliance"],
    summary="Generate a three-phase permit approval roadmap from building parameters",
)
async def compliance_roadmap(
    body: RoadmapRequest,
    _payload: Annotated[dict, Depends(require_auth)],
) -> RoadmapResponse:
    """
    Accepts building parameters and returns:
    - **permits** — full three-phase approval list with estimated fees and timelines
    - **risk_alerts** — proactive warnings specific to the project characteristics
    - **summary** — aggregated metrics (total fee, critical-path days, etc.)

    Requires a valid JWT Bearer token from ``/api/login``.
    """
    permits  = _build_permits(body.floor_area, body.stories, body.zoning_type, body.construction_type)
    warnings = _build_risk_warnings(
        body.floor_area, body.stories, body.zoning_type,
        body.construction_type, float(body.project_value_lkr),
    )

    total_fee       = sum(p.estimated_fee_lkr for p in permits)
    max_days        = max((p.max_days for p in permits), default=0)
    mandatory_count = sum(1 for p in permits if p.mandatory)
    high_risk_count = sum(1 for p in permits if p.risk_level == "HIGH")

    logger.info(
        "Roadmap | zoning=%s type=%s area=%d stories=%d permits=%d warnings=%d",
        body.zoning_type, body.construction_type,
        body.floor_area, body.stories, len(permits), len(warnings),
    )

    return RoadmapResponse(
        permits=permits,
        risk_alerts=warnings,
        summary=_RoadmapSummary(
            total_permits=len(permits),
            mandatory_count=mandatory_count,
            estimated_total_fee_lkr=round(total_fee, 2),
            max_timeline_days=max_days,
            high_risk_count=high_risk_count,
        ),
    )


# ── AI Recommendation ──────────────────────────────────────────────────────────


@app.post(
    "/api/generate-recommendation",
    tags=["AI"],
    summary="Generate a Gemini AI engineering recommendation for a detected clash",
)
async def generate_recommendation(request: ClashDetails) -> dict:
    """Calls Gemini 2.5 Flash to produce a technical resolution for a clash."""
    prompt = (
        f"You are an expert Structural/MEP Engineer. "
        f"A construction clash was detected involving a '{request.className}' "
        f"at coordinates X:{request.x}, Y:{request.y} with {request.severity} severity. "
        f"Provide a 2-sentence highly technical, actionable recommendation on how to "
        f"resolve this for the site engineer."
    )
    try:
        gemini = _get_gemini_client()
        response = gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return {"recommendation": response.text}
    except Exception as e:
        print(f"Gemini generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
