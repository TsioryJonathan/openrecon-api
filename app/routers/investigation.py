from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas import (
    ErrorResponse,
    InvestigationAddTargetRequest,
    InvestigationCreateRequest,
    InvestigationListResponse,
    InvestigationScanRequest,
    InvestigationScanResponse,
    InvestigationSummaryResponse,
)
from app.services import investigation as inv_service
from app.services.scan import SUPPORTED_TARGET_TYPES, run_scan_for_investigation
from app.services.storage import get_or_create_target

router = APIRouter()


@router.post(
    "",
    response_model=InvestigationSummaryResponse,
    summary="Create a new investigation",
    status_code=201,
)
async def create_investigation(
    body: InvestigationCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    inv = await inv_service.create_investigation(db, name=body.name, description=body.description)
    return await inv_service.get_investigation_summary(db, inv.id)


@router.get(
    "",
    response_model=InvestigationListResponse,
    summary="List investigations",
)
async def list_investigations(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    if status and status not in ("open", "closed"):
        raise HTTPException(status_code=400, detail="status must be 'open' or 'closed'.")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200.")

    investigations = await inv_service.list_investigations(
        db, status=status, limit=limit, offset=offset
    )
    return {
        "total": len(investigations),
        "investigations": [
            {
                "id": inv.id,
                "name": inv.name,
                "description": inv.description,
                "status": inv.status,
                "created_at": str(inv.created_at),
                "updated_at": str(inv.updated_at),
            }
            for inv in investigations
        ],
    }


@router.get(
    "/{investigation_id}",
    response_model=InvestigationSummaryResponse,
    summary="Get investigation summary",
    responses={404: {"model": ErrorResponse}},
)
async def get_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
):
    summary = await inv_service.get_investigation_summary(db, investigation_id)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )
    return summary


@router.post(
    "/{investigation_id}/targets",
    response_model=InvestigationSummaryResponse,
    summary="Add a target to an investigation",
    status_code=201,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def add_target(
    investigation_id: str,
    body: InvestigationAddTargetRequest,
    db: AsyncSession = Depends(get_db),
):
    target, _ = await get_or_create_target(
        db, type=body.target_type, value=body.target_value.strip()
    )
    try:
        await inv_service.add_target_to_investigation(
            db,
            investigation_id=investigation_id,
            target_id=target.id,
            role=body.role,
        )
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=code, detail=str(e))

    return await inv_service.get_investigation_summary(db, investigation_id)


@router.post(
    "/{investigation_id}/scan",
    response_model=InvestigationScanResponse,
    summary="Run a scan within an investigation",
    status_code=201,
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported type or closed investigation"},
        404: {"model": ErrorResponse, "description": "Investigation not found"},
    },
)
async def scan_within_investigation(
    investigation_id: str,
    body: InvestigationScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run a scan against a target and automatically link it to the investigation.

    - If the target already exists it is reused (deduplicated by type+value).
    - If the target is already in the investigation, the link is kept as-is.
    - New findings accumulate; duplicates are deduplicated with evidence merged.
    - Returns both the scan result and the updated investigation summary.
    """
    if body.target_type not in SUPPORTED_TARGET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported target type '{body.target_type}'. "
                f"Supported: {', '.join(SUPPORTED_TARGET_TYPES)}."
            ),
        )

    try:
        scan_result = await run_scan_for_investigation(
            db,
            investigation_id=investigation_id,
            target_type=body.target_type,
            target_value=body.target_value.strip(),
            options=body.options,
            role=body.role,
        )
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=code, detail=str(e))

    # Build scan portion of the response.
    findings_out = []
    for f in scan_result.findings:
        evidence_out = [
            {
                "id": e.id,
                "source": e.source,
                "evidence_type": e.evidence_type,
                "value": e.value,
                "observed_at": str(e.observed_at),
            }
            for e in (f.evidence if f.evidence else [])
        ]
        findings_out.append(
            {
                "id": f.id,
                "type": f.type,
                "value": f.value,
                "source": f.source,
                "confidence": f.confidence,
                "confidence_reason": f.confidence_reason,
                "observed_at": str(f.observed_at),
                "evidence": evidence_out,
            }
        )

    scan_out = {
        "target": {
            "id": scan_result.target.id,
            "type": scan_result.target.type,
            "value": scan_result.target.value,
            "created_at": str(scan_result.target.created_at),
        },
        "finding_count": scan_result.finding_count,
        "evidence_count": scan_result.evidence_count,
        "modules_run": scan_result.modules_run,
        "findings": findings_out,
        "errors": scan_result.errors,
    }

    # Updated investigation summary.
    summary = await inv_service.get_investigation_summary(db, investigation_id)

    return {"scan": scan_out, "investigation": summary}


@router.post(
    "/{investigation_id}/close",
    response_model=InvestigationSummaryResponse,
    summary="Close an investigation",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def close_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        await inv_service.close_investigation(db, investigation_id)
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=code, detail=str(e))

    return await inv_service.get_investigation_summary(db, investigation_id)
