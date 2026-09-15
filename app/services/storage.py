"""
app/services/storage.py

Central persistence layer for the OpenRecon core data model.

Responsibilities:
- Create and retrieve Target, Finding, Evidence records.
- Normalize finding values before storage (app.core.normalizer).
- Deduplicate findings before insertion (app.core.deduplicator).
- Attach evidence to existing findings when duplicates are detected.
- Provide store_module_result() as the single entry point after a module run.

Rules:
- Never import from routers or schemas here.
- Never call any module directly here.
- All functions receive an AsyncSession from the caller.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deduplicator import deduplicate_findings, prepare_findings_for_storage
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

    Does NOT check for duplicates — use get_or_create_target() when
    deduplication is needed.
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
    normalized_value: str,
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
        normalized_value=normalized_value,
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
    Normalize, deduplicate, and persist findings + evidence in one transaction.

    Pipeline:
    1. Normalize: compute normalized_value for each finding dict.
    2. Deduplicate: split into new findings vs already-existing ones.
    3. Insert new findings (flush to get IDs).
    4. Insert evidence for new findings.
    5. Insert evidence for existing (duplicate) findings — evidence accumulates.
    6. Commit.

    Args:
        db: async SQLAlchemy session.
        target_id: the already-created Target this result belongs to.
        findings_data: list of dicts from ModuleResult.findings.
            Required keys: type, value, source, confidence, confidence_reason.
            Optional: metadata.
        evidence_data: list of dicts from ModuleResult.evidence.
            Must be same length as findings_data, same index order.
            Required keys: source, evidence_type, value.
            Optional: metadata.

    Returns:
        (all_findings, all_evidence) — includes both newly inserted records
        and the existing Finding objects that received new evidence.

    On failure: rolls back and re-raises.
    """
    if len(findings_data) != len(evidence_data):
        logger.warning(
            "store_module_result: findings(%d) and evidence(%d) counts differ for target_id=%s",
            len(findings_data),
            len(evidence_data),
            target_id,
        )

    # Step 1 — Normalize.
    prepare_findings_for_storage(findings_data)

    # Step 2 — Deduplicate.
    new_findings_data, new_evidence_data, existing_ids = await deduplicate_findings(
        db,
        target_id=target_id,
        findings_data=findings_data,
        evidence_data=evidence_data,
    )

    stored_findings: list[Finding] = []
    stored_evidence: list[Evidence] = []

    try:
        # Step 3 — Insert new findings.
        new_finding_objs: list[Finding] = []
        for f_data in new_findings_data:
            finding = Finding(
                target_id=target_id,
                type=f_data["type"],
                value=f_data["value"],
                normalized_value=f_data["normalized_value"],
                source=f_data["source"],
                confidence=f_data["confidence"],
                confidence_reason=f_data["confidence_reason"],
                meta=f_data.get("metadata"),
            )
            db.add(finding)
            new_finding_objs.append(finding)

        # Flush to get IDs before inserting evidence.
        await db.flush()

        # Step 4 — Insert evidence for new findings.
        for i, e_data in enumerate(new_evidence_data):
            if i >= len(new_finding_objs):
                break
            ev = Evidence(
                finding_id=new_finding_objs[i].id,
                source=e_data["source"],
                evidence_type=e_data["evidence_type"],
                value=e_data["value"],
                meta=e_data.get("metadata"),
            )
            db.add(ev)
            stored_evidence.append(ev)

        # Step 5 — Insert evidence for existing (deduplicated) findings.
        for original_idx, existing_finding_id in existing_ids.items():
            if original_idx >= len(evidence_data):
                continue
            e_data = evidence_data[original_idx]
            ev = Evidence(
                finding_id=existing_finding_id,
                source=e_data["source"],
                evidence_type=e_data["evidence_type"],
                value=e_data["value"],
                meta=e_data.get("metadata"),
            )
            db.add(ev)
            stored_evidence.append(ev)

        await db.commit()

        # Refresh all new objects.
        for f in new_finding_objs:
            await db.refresh(f)
        for e in stored_evidence:
            await db.refresh(e)

        stored_findings.extend(new_finding_objs)

        # Also fetch the existing findings that received new evidence,
        # so the caller has the full picture.
        for existing_finding_id in existing_ids.values():
            stmt = select(Finding).where(Finding.id == existing_finding_id)
            res = await db.execute(stmt)
            existing_f = res.scalars().first()
            if existing_f and existing_f not in stored_findings:
                stored_findings.append(existing_f)

        logger.info(
            "store_module_result: %d new findings, %d deduplicated, "
            "%d evidence stored for target_id=%s",
            len(new_finding_objs),
            len(existing_ids),
            len(stored_evidence),
            target_id,
        )

    except Exception:
        await db.rollback()
        raise

    return stored_findings, stored_evidence
