from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas import (
    CorrelationResponse,
    ErrorResponse,
    InvestigationAddTargetRequest,
    InvestigationCreateRequest,
    InvestigationListResponse,
    InvestigationScanRequest,
    InvestigationScanResponse,
    InvestigationSummaryResponse,
)
from app.services import investigation as inv_service
from app.services.correlation import run_correlation_for_investigation
from app.services.report import build_report_data, render_json, render_markdown
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
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
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
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def scan_within_investigation(
    investigation_id: str,
    body: InvestigationScanRequest,
    db: AsyncSession = Depends(get_db),
):
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

    return {
        "scan": {
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
        },
        "investigation": await inv_service.get_investigation_summary(db, investigation_id),
    }


@router.post(
    "/{investigation_id}/correlate",
    response_model=CorrelationResponse,
    summary="Run correlation across all targets in an investigation",
    responses={404: {"model": ErrorResponse}},
)
async def correlate_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
):
    inv = await inv_service.get_investigation(db, investigation_id)
    if inv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )
    result = await run_correlation_for_investigation(db, investigation_id)
    return {
        "investigation_id": investigation_id,
        "relations_created": result.created_count,
        "relations_skipped": result.relations_skipped,
        "errors": result.errors,
        "relations": [
            {
                "id": r.id,
                "source_finding_id": r.source_finding_id,
                "target_finding_id": r.target_finding_id,
                "relation_type": r.relation_type,
                "confidence": r.confidence,
                "reason": r.reason,
                "created_at": str(r.created_at),
            }
            for r in result.relations_created
        ],
    }


@router.get(
    "/{investigation_id}/report",
    summary="Generate an investigation report",
    responses={
        200: {"description": "Report in requested format (JSON or Markdown)"},
        400: {"model": ErrorResponse, "description": "Invalid format parameter"},
        404: {"model": ErrorResponse, "description": "Investigation not found"},
    },
)
async def get_report(
    investigation_id: str,
    format: str = Query(
        default="json",
        description="Output format: 'json' (structured) or 'markdown' (human-readable).",
        pattern="^(json|markdown)$",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a report for an investigation.

    - **json**: Full structured report as a JSON object. Contains all findings,
      evidence, relations, timeline and stats. Suitable for programmatic use
      or downstream processing.
    - **markdown**: Human-readable Markdown document. Suitable for export,
      sharing, or rendering in a docs tool.

    The report only reflects data already in the database. Run
    `POST /correlate` before generating a report if you want relations included.
    No conclusions are invented — every claim traces back to a Finding.
    """
    if format not in ("json", "markdown"):
        raise HTTPException(
            status_code=400,
            detail="format must be 'json' or 'markdown'.",
        )

    report_data = await build_report_data(db, investigation_id)
    if report_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )

    if format == "markdown":
        md = render_markdown(report_data)
        return PlainTextResponse(content=md, media_type="text/markdown")

    return render_json(report_data)


@router.post(
    "/{investigation_id}/close",
    response_model=InvestigationSummaryResponse,
    summary="Close an investigation",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
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
