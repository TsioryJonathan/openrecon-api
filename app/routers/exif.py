import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas import ErrorResponse, ExifResponse
from app.services.exif import run_exif_extract

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/heic", "image/webp"}


@router.post(
    "/extract",
    response_model=ExifResponse,
    summary="Extract EXIF metadata from an image",
    description=(
        "Uploads an image and returns its EXIF metadata: GPS coordinates, "
        "device make/model, capture date, editing software, and copyright."
    ),
    responses={400: {"model": ErrorResponse, "description": "Invalid file type"}},
)
async def extract(file: UploadFile):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}",
        )

    suffix = Path(file.filename or "upload").suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = await run_exif_extract(tmp_path)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"filename": file.filename or "upload", **result}
