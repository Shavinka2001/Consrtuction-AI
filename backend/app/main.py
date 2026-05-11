"""
ConstructAI – FastAPI application entry point.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.database import close_mongo_connection, connect_to_mongo
from app.routers.analyze import router as analyze_router
from app.routers.compliance import router as compliance_router
from app.services.compliance_service import ComplianceService
from app.services.ml_risk_service import _ml_service as ml_risk_service

# ── Environment ────────────────────────────────────────────────────────────────

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """Manage resources that must live for the full application lifetime."""
    # ── Startup ──────────────────────────────────────────────────────────────
    await connect_to_mongo()

    # Load ML risk model artefacts (uda_risk_model.pkl + label_encoder.pkl).
    # Safe to call when files are absent — logs a warning and disables ML mode.
    ml_risk_service.load()

    # Ensure compliance indexes exist (idempotent – safe to run every boot).
    from app.core.database import _client  # noqa: PLC0415
    import os
    db_name = os.environ.get("COMPLIANCE_DB_NAME", "constructai")
    if _client is not None:
        svc = ComplianceService(_client[db_name])
        await svc.ensure_indexes()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await close_mongo_connection()


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ConstructAI API",
    description="AI-powered construction site analysis backend.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Restrict to the Next.js dev server in development; tighten for production.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(analyze_router, prefix="/api", tags=["Analysis"])
app.include_router(compliance_router)   # prefix already set in the router


# ── Health check ───────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {
        "status": "ok",
        "ml_risk_model": {
            "available": ml_risk_service.available,
            "error": ml_risk_service.load_error,
        },
    }


# ── Recommendation endpoint ────────────────────────────────────────────────────


class ClashDetails(BaseModel):
    className: str
    x: float
    y: float
    severity: str


@app.post("/api/generate-recommendation", tags=["AI"])
async def generate_recommendation(request: ClashDetails) -> dict:
    """Use Gemini to produce a technical resolution recommendation for a detected clash."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY is not set in environment.")
        raise HTTPException(status_code=500, detail="Gemini API key not configured.")
    try:
        client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(api_version="v1"),
        )
        prompt = (
            f"You are an expert Structural/MEP Engineer. "
            f"A construction clash was detected involving a '{request.className}' "
            f"at coordinates X:{request.x}, Y:{request.y} with {request.severity} severity. "
            f"Provide a 2-sentence highly technical, actionable recommendation on how to "
            f"resolve this for the site engineer."
        )
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        logger.info("Gemini recommendation generated for class='%s'", request.className)
        return {"recommendation": response.text}
    except Exception as exc:
        logger.error("Gemini generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Failed to generate recommendation: {exc}") from exc
