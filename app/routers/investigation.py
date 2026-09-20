from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas import (
    AdaptiveScanResponse,
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
from app.services.adaptive import DEFAULT_MAX_DEPTH, run_adaptive_scan
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
    "/{investigation_id}/adaptive-scan",
    response_model=AdaptiveScanResponse,
    summary="Run an adaptive multi-hop scan within an investigation",
    status_code=201,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def adaptive_scan_within_investigation(
    investigation_id: str,
    body: InvestigationScanRequest,
    max_depth: int = Query(
        default=DEFAULT_MAX_DEPTH,
        ge=0,
        le=4,
        description=(
            "Maximum number of hops beyond the initial scan. "
            "0 = scan only the initial target (same as /scan). "
            "Default: 2. Maximum: 4."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Run an adaptive recon scan starting from a single target.

    The engine scans the initial target, extracts new leads from the findings
    (domains, IPs, usernames found in profile URLs, etc.), and recursively
    scans those leads up to `max_depth` hops.

    Safety guarantees enforced by the engine:
    - **Depth limit**: never exceeds `max_depth` hops.
    - **Session dedup**: each (type, value) pair scanned at most once per run.
    - **Scope**: only targets within the investigation's scope are scanned.
    - **Rate limit**: the process-wide rate limiter applies per (target, module).

    All discovered targets are automatically linked to the investigation.
    Returns a summary of all hops, findings, leads extracted/skipped.
    """
    if body.target_type not in SUPPORTED_TARGET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported target type '{body.target_type}'. "
                f"Supported: {', '.join(SUPPORTED_TARGET_TYPES)}."
            ),
        )

    inv = await inv_service.get_investigation(db, investigation_id)
    if inv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )
    if inv.status == "closed":
        raise HTTPException(
            status_code=400,
            detail=f"Investigation '{investigation_id}' is closed.",
        )

    adaptive_result = await run_adaptive_scan(
        db,
        target_type=body.target_type,
        target_value=body.target_value.strip(),
        options=body.options,
        max_depth=max_depth,
        investigation_id=investigation_id,
    )

    hops_out = []
    for hop in adaptive_result.hops:
        hops_out.append(
            {
                "depth": hop.depth,
                "target_type": hop.target_type,
                "target_value": hop.target_value,
                "finding_count": hop.scan_result.finding_count,
                "evidence_count": hop.scan_result.evidence_count,
                "modules_run": hop.scan_result.modules_run,
                "errors": hop.scan_result.errors,
                "leads_extracted": [
                    {
                        "target_type": lead.target_type,
                        "target_value": lead.target_value,
                        "rule": lead.rule,
                        "source_finding_id": lead.source_finding_id,
                    }
                    for lead in hop.leads_extracted
                ],
                "source_lead": {
                    "target_type": hop.source_lead.target_type,
                    "target_value": hop.source_lead.target_value,
                    "rule": hop.source_lead.rule,
                    "source_finding_id": hop.source_lead.source_finding_id,
                }
                if hop.source_lead
                else None,
            }
        )

    return {
        "investigation_id": investigation_id,
        "max_depth": max_depth,
        "hop_count": adaptive_result.hop_count,
        "targets_scanned": [
            {"type": t, "value": v} for t, v in sorted(adaptive_result.targets_scanned)
        ],
        "total_finding_count": adaptive_result.finding_count,
        "total_evidence_count": adaptive_result.evidence_count,
        "hops": hops_out,
        "leads_skipped": adaptive_result.leads_skipped,
        "errors": adaptive_result.errors,
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
        200: {"description": "Report in requested format"},
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_report(
    investigation_id: str,
    format: str = Query(
        default="json",
        description="Output format: 'json' or 'markdown'.",
        pattern="^(json|markdown)$",
    ),
    db: AsyncSession = Depends(get_db),
):
    if format not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'.")
    report_data = await build_report_data(db, investigation_id)
    if report_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Investigation '{investigation_id}' not found.",
        )
    if format == "markdown":
        return PlainTextResponse(content=render_markdown(report_data), media_type="text/markdown")
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
