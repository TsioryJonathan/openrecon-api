"""
app/services/storage.py

Central persistence layer for the OpenRecon core data model.

Responsibilities:
- Create and retrieve Target, Finding, Evidence records.
- Inject target_id into findings and finding_id into evidence
  (the module layer never touches these foreign keys directly).
- Provide a single function that persists a full ModuleResult in one
  transaction: store_module_result().

Rules:
- Never import from routers or schemas here.
- Never call any module directly here.
- All functions receive an AsyncSession from the caller (FastAPI dependency
  injection or the future orchestrator). This keeps transactions explicit.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.Evidence import Evidence
from app.models.Finding import Finding
from app.models.Target import Target

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


async def create_target(
    db: AsyncSession,
    *,
    type: str,
    value: str,
    meta: dict | None = None,
) -> Target:
    """
    Create and persist a new Target.

    Does NOT check for duplicates — the caller decides whether to reuse an
    existing target or create a fresh one. Use get_target_by_value() first
    if deduplication is needed.
    """
    target = Target(type=type, value=value, meta=meta)
    db.add(target)
    await db.commit()
    await db.refresh(target)
    logger.info("Created target id=%s type=%s value=%s", target.id, type, value)
    return target


async def get_target_by_value(
    db: AsyncSession,
    *,
    type: str,
    value: str,
) -> Target | None:
    """Return the first Target matching (type, value), or None."""
    stmt = select(Target).where(Target.type == type, Target.value == value)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_or_create_target(
    db: AsyncSession,
    *,
    type: str,
    value: str,
    meta: dict | None = None,
) -> tuple[Target, bool]:
    """
    Return an existing Target matching (type, value), or create one.

    Returns (target, created) where created is True if a new row was inserted.
    """
    existing = await get_target_by_value(db, type=type, value=value)
    if existing:
        return existing, False
    target = await create_target(db, type=type, value=value, meta=meta)
    return target, True


async def get_target_with_findings(
    db: AsyncSession,
    target_id: str,
) -> Target | None:
    """Return a Target with its findings and their evidence eagerly loaded."""
    stmt = (
        select(Target)
        .where(Target.id == target_id)
        .options(selectinload(Target.findings).selectinload(Finding.evidence))
    )
    result = await db.execute(stmt)
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


async def create_finding(
    db: AsyncSession,
    *,
    target_id: str,
    type: str,
    value: str,
    source: str,
    confidence: str,
    confidence_reason: str,
    meta: dict | None = None,
) -> Finding:
    """Create and persist a single Finding linked to a Target."""
    finding = Finding(
        target_id=target_id,
        type=type,
        value=value,
        source=source,
        confidence=confidence,
        confidence_reason=confidence_reason,
        meta=meta,
    )
    db.add(finding)
    await db.commit()
    await db.refresh(finding)
    return finding


async def get_findings_for_target(
    db: AsyncSession,
    target_id: str,
) -> list[Finding]:
    """Return all Findings for a given target_id, ordered by observed_at."""
    stmt = select(Finding).where(Finding.target_id == target_id).order_by(Finding.observed_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


async def create_evidence(
    db: AsyncSession,
    *,
    finding_id: str,
    source: str,
    evidence_type: str,
    value: str,
    meta: dict | None = None,
) -> Evidence:
    """Create and persist a single Evidence record linked to a Finding."""
    ev = Evidence(
        finding_id=finding_id,
        source=source,
        evidence_type=evidence_type,
        value=value,
        meta=meta,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    return ev


async def get_evidence_for_finding(
    db: AsyncSession,
    finding_id: str,
) -> list[Evidence]:
    """Return all Evidence records for a given finding_id."""
    stmt = select(Evidence).where(Evidence.finding_id == finding_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Bulk persistence — ModuleResult
# ---------------------------------------------------------------------------


async def store_module_result(
    db: AsyncSession,
    *,
    target_id: str,
    findings_data: list[dict],
    evidence_data: list[dict],
) -> tuple[list[Finding], list[Evidence]]:
    """
    Persist a full set of findings and their evidence in a single transaction.

    This is the primary entry point used after a module executes.

    The caller passes:
    - target_id: the already-created Target this result belongs to.
    - findings_data: list of dicts from ModuleResult.findings.
      Each dict must have: type, value, source, confidence, confidence_reason.
      Optional: metadata.
    - evidence_data: list of dicts from ModuleResult.evidence.
      Must be same length as findings_data and in the same order —
      evidence_data[i] is the evidence for findings_data[i].

    Returns (stored_findings, stored_evidence).

    If the lengths differ, evidence is stored only for findings that have a
    matching index. A warning is logged for mismatches.

    All inserts happen in a single transaction. On failure, everything is
    rolled back and the exception is re-raised.
    """
    if len(findings_data) != len(evidence_data):
        logger.warning(
            "store_module_result: findings(%d) and evidence(%d) counts differ for target_id=%s",
            len(findings_data),
            len(evidence_data),
            target_id,
        )

    stored_findings: list[Finding] = []
    stored_evidence: list[Evidence] = []

    try:
        for i, f_data in enumerate(findings_data):
            finding = Finding(
                target_id=target_id,
                type=f_data["type"],
                value=f_data["value"],
                source=f_data["source"],
                confidence=f_data["confidence"],
                confidence_reason=f_data["confidence_reason"],
                meta=f_data.get("metadata"),
            )
            db.add(finding)
            stored_findings.append(finding)

        # Flush to get DB-generated IDs without committing yet.
        await db.flush()

        for i, e_data in enumerate(evidence_data):
            if i >= len(stored_findings):
                break
            ev = Evidence(
                finding_id=stored_findings[i].id,
                source=e_data["source"],
                evidence_type=e_data["evidence_type"],
                value=e_data["value"],
                meta=e_data.get("metadata"),
            )
            db.add(ev)
            stored_evidence.append(ev)

        await db.commit()

        for f in stored_findings:
            await db.refresh(f)
        for e in stored_evidence:
            await db.refresh(e)

        logger.info(
            "store_module_result: stored %d findings, %d evidence for target_id=%s",
            len(stored_findings),
            len(stored_evidence),
            target_id,
        )

    except Exception:
        await db.rollback()
        raise

    return stored_findings, stored_evidence
