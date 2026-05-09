"""
POST /api/analyze-site

Accepts an uploaded image, runs YOLOv8 inference, and returns structured
detection results. Requires a valid JWT Bearer token.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.dependencies.auth import require_auth
from app.services.yolo_service import Detection, yolo_service

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Temporary upload directory ─────────────────────────────────────────────────

_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "tmp" / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Allowed MIME types ─────────────────────────────────────────────────────────

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
_MAX_FILE_SIZE_MB = 20
_MAX_FILE_SIZE_BYTES = _MAX_FILE_SIZE_MB * 1024 * 1024

# ── Response schemas ───────────────────────────────────────────────────────────


class BoundingBoxSchema(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class DetectionSchema(BaseModel):
    class_name: str
    confidence: float
    bbox: BoundingBoxSchema


class AnalyzeSiteResponse(BaseModel):
    success: bool
    filename: str
    detections: List[DetectionSchema]
    total_detections: int


# ── Helper ─────────────────────────────────────────────────────────────────────


def _detection_to_schema(det: Detection) -> DetectionSchema:
    return DetectionSchema(
        class_name=det.class_name,
        confidence=det.confidence,
        bbox=BoundingBoxSchema(
            x_min=det.bbox.x_min,
            y_min=det.bbox.y_min,
            x_max=det.bbox.x_max,
            y_max=det.bbox.y_max,
        ),
    )


# ── Endpoint ───────────────────────────────────────────────────────────────────


@router.post(
    "/analyze-site",
    response_model=AnalyzeSiteResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyse a construction-site image with YOLOv8",
    description=(
        "Upload a site image (JPEG / PNG / WebP / BMP). "
        "The endpoint runs YOLOv8 inference and returns every detected object "
        "with its class name, confidence score, and bounding-box coordinates. "
        "**Requires a valid JWT Bearer token.**"
    ),
)
async def analyze_site(
    file: Annotated[UploadFile, File(description="Site image to analyse")],
    # `_payload` carries the decoded JWT claims; underscore signals it is not
    # used in the body but is required for authentication enforcement.
    _payload: Annotated[dict, Depends(require_auth)],
) -> AnalyzeSiteResponse:
    # ── 1. Validate content-type ───────────────────────────────────────────────
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed types: {', '.join(sorted(_ALLOWED_CONTENT_TYPES))}."
            ),
        )

    # ── 2. Read & size-check the upload ───────────────────────────────────────
    image_bytes: bytes = await file.read()

    if len(image_bytes) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {_MAX_FILE_SIZE_MB} MB size limit.",
        )

    # ── 3. Save to a uniquely named temp file ─────────────────────────────────
    # Use a UUID prefix to avoid filename collisions under concurrent requests.
    original_suffix = Path(file.filename or "upload").suffix or ".jpg"
    tmp_filename = f"{uuid.uuid4().hex}{original_suffix}"
    tmp_path = _UPLOAD_DIR / tmp_filename

    try:
        tmp_path.write_bytes(image_bytes)
        logger.info("Saved upload to %s (%d bytes)", tmp_path, len(image_bytes))

        # ── 4. Run YOLOv8 inference ───────────────────────────────────────────
        result = yolo_service.run(tmp_path)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Inference failed: {result.error}",
            )

        # ── 5. Build and return the response ──────────────────────────────────
        detections = [_detection_to_schema(d) for d in result.detections]

        logger.info(
            "Inference complete for '%s': %d detection(s).",
            file.filename,
            len(detections),
        )

        return AnalyzeSiteResponse(
            success=True,
            filename=file.filename or tmp_filename,
            detections=detections,
            total_detections=len(detections),
        )

    except HTTPException:
        raise  # propagate intentional HTTP errors as-is

    except FileNotFoundError as exc:
        # Weights file missing — surface clearly rather than a cryptic 500.
        logger.error("Model weights not found: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    except Exception as exc:
        logger.exception("Unexpected error during site analysis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during image analysis.",
        )

    finally:
        # ── 6. Always clean up the temp file ──────────────────────────────────
        if tmp_path.exists():
            tmp_path.unlink()
            logger.debug("Deleted temporary file %s", tmp_path)
