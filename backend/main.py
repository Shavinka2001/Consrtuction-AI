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
import uuid
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
from pydantic import BaseModel
from ultralytics import YOLO

load_dotenv()

# ── Gemini client (global singleton) ──────────────────────────────────────────
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

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

# ── Dummy user database ────────────────────────────────────────────────────────
# WARNING: plain-text passwords are acceptable ONLY for local development.
# Replace with a real database + password hashing (bcrypt) before going live.

USERS_DB: dict[str, dict] = {
    "admin": {
        "username":  "admin",
        "password":  "123",
        "role":      "Project Manager",
        "full_name": "Admin User",
    },
    "site_eng": {
        "username":  "site_eng",
        "password":  "123",
        "role":      "Site Engineer",
        "full_name": "Site Engineer",
    },
    "architect": {
        "username":  "architect",
        "password":  "123",
        "role":      "Architect",
        "full_name": "Architect",
    },
    "qa_officer": {
        "username":  "qa_officer",
        "password":  "123",
        "role":      "Compliance Officer",
        "full_name": "QA Officer",
    },
    "qs_planner": {
        "username":  "qs_planner",
        "password":  "123",
        "role":      "Quantity Surveyor",
        "full_name": "QS Planner",
    },
}

# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ConstructAI API",
    description="AI-powered construction site analysis backend.",
    version="0.1.0",
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
    username: str
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


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.post(
    "/api/login",
    response_model=LoginResponse,
    tags=["Auth"],
    summary="Authenticate and receive a JWT access token",
)
async def login(body: LoginRequest) -> LoginResponse:
    """
    Accepts **username** + **password**, verifies against the in-memory user
    store, and returns a signed JWT valid for 2 hours alongside the user role.
    """
    user = USERS_DB.get(body.username)

    # Constant-time-ish check: validate both fields before rejecting
    # so as not to leak whether the username exists.
    if not user or user["password"] != body.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = _create_token(sub=user["username"], role=user["role"])
    logger.info("Login: user='%s' role='%s'", user["username"], user["role"])

    return LoginResponse(
        access_token=token,
        role=user["role"],
        username=user["username"],
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
    Creates a new user account in the in-memory store.
    The role is provided by the caller (e.g. 'Project Manager', 'Site Engineer').
    Returns 400 if the username is already taken.
    """
    if body.username in USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists.",
        )

    USERS_DB[body.username] = {
        "username":  body.username,
        "email":     body.email,
        "password":  body.password,
        "role":      body.role,
        "full_name": body.username,
    }
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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return {"recommendation": response.text}
    except Exception as e:
        print(f"Gemini generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
