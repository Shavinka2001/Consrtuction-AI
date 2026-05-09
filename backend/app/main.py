"""
ConstructAI – FastAPI application entry point.
"""

from __future__ import annotations

import logging
import os

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Environment & Gemini ───────────────────────────────────────────────────────

from app.routers.analyze import router as analyze_router

# ── Environment & Gemini ───────────────────────────────────────────────────────

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ConstructAI API",
    description="AI-powered construction site analysis backend.",
    version="0.1.0",
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


# ── Health check ───────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok"}


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
