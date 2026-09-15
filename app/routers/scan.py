from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas import ErrorResponse, ScanRequest, ScanResponse
from app.services.scan import SUPPORTED_TARGET_TYPES, run_scan

router = APIRouter()


@router.post(
    "",
    response_model=ScanResponse,
    summary="Run an OpenRecon scan",
    description=(
        "Runs the OpenRecon pipeline for a given target. "
        "Creates or reuses a Target, executes the appropriate module(s), "
        "stores all Findings and Evidence, and returns a structured result.\n\n"
        "Currently supported target types: `username` (uses Sherlock).\n\n"
        "For username scans, pass a `sites` list to restrict the scan to specific "
        "platforms. Omit `sites` to scan all supported platforms."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Unsupported target type"},
    },
)
async def scan(body: ScanRequest, db: AsyncSession = Depends(get_db)):
    if body.target_type not in SUPPORTED_TARGET_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported target type '{body.target_type}'. "
                f"Supported: {', '.join(SUPPORTED_TARGET_TYPES)}."
            ),
        )

    result = await run_scan(
        db,
        target_type=body.target_type,
        target_value=body.target_value.strip(),
        sites=body.sites,
    )

    # Build evidence index by finding_id (avoids lazy loading).
    evidence_by_finding: dict[str, list] = {}
    for e in result.evidence:
        evidence_by_finding.setdefault(e.finding_id, []).append(e)

    # Build findings list with their evidence.
    findings_out = []
    for f in result.findings:
        evidence_out = [
            {
                "id": e.id,
                "source": e.source,
                "evidence_type": e.evidence_type,
                "value": e.value,
                "observed_at": str(e.observed_at),
            }
            for e in evidence_by_finding.get(f.id, [])
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
        "target": {
            "id": result.target.id,
            "type": result.target.type,
            "value": result.target.value,
            "created_at": str(result.target.created_at),
        },
        "finding_count": result.finding_count,
        "evidence_count": result.evidence_count,
        "modules_run": result.modules_run,
        "findings": findings_out,
        "errors": result.errors,
    }
