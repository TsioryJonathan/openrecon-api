"""
app/services/investigation.py

Service layer for Investigation management.

An Investigation groups Targets under a named context and lets the operator
track related targets, findings, and evidence together instead of treating
every scan as independent.

Rules:
- Never import routers or Pydantic schemas here.
- All functions receive an AsyncSession from the caller.
- Closed investigations reject new targets (service-level enforcement).
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.Evidence import Evidence
from app.models.Finding import Finding
from app.models.Investigation import Investigation
from app.models.InvestigationTarget import InvestigationTarget

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_investigation(
    db: AsyncSession,
    *,
    name: str,
    description: str | None = None,
) -> Investigation:
    """
    Create a new Investigation.

    The investigation is created with status='open' and no targets.
    Targets are added separately via add_target_to_investigation().
    """
    inv = Investigation(name=name.strip(), description=description)
    db.add(inv)
    await db.commit()
    await db.refresh(inv)
    logger.info("Created investigation id=%s name=%r", inv.id, inv.name)
    return inv


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def get_investigation(
    db: AsyncSession,
    investigation_id: str,
) -> Investigation | None:
    """Return an Investigation by ID with its InvestigationTarget rows loaded."""
    stmt = (
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .options(selectinload(Investigation.targets).selectinload(InvestigationTarget.target))
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_investigations(
    db: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Investigation]:
    """
    List investigations, optionally filtered by status.

    Returns investigations ordered by created_at descending (most recent first).
    """
    stmt = select(Investigation).order_by(Investigation.created_at.desc())
    if status:
        stmt = stmt.where(Investigation.status == status)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


async def add_target_to_investigation(
    db: AsyncSession,
    *,
    investigation_id: str,
    target_id: str,
    role: str | None = None,
) -> InvestigationTarget:
    """
    Link an existing Target to an Investigation.

    Raises ValueError if:
    - The investigation does not exist.
    - The investigation is closed.
    - The target is already linked to this investigation.

    The target must already exist in the DB (created via storage.get_or_create_target).
    """
    # Load investigation
    inv = await get_investigation(db, investigation_id)
    if inv is None:
        raise ValueError(f"Investigation '{investigation_id}' not found.")
    if inv.status == "closed":
        raise ValueError(
            f"Investigation '{investigation_id}' is closed. Re-open it before adding targets."
        )

    # Check for duplicate link
    stmt = select(InvestigationTarget).where(
        InvestigationTarget.investigation_id == investigation_id,
        InvestigationTarget.target_id == target_id,
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise ValueError(
            f"Target '{target_id}' is already linked to investigation '{investigation_id}'."
        )

    link = InvestigationTarget(
        investigation_id=investigation_id,
        target_id=target_id,
        role=role,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    logger.info(
        "Linked target_id=%s to investigation_id=%s role=%r",
        target_id,
        investigation_id,
        role,
    )
    return link


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def close_investigation(
    db: AsyncSession,
    investigation_id: str,
) -> Investigation:
    """
    Mark an investigation as closed.

    Closed investigations are read-only: no new targets can be added
    and no scans should be run against them.

    Raises ValueError if the investigation does not exist or is already closed.
    """
    inv = await get_investigation(db, investigation_id)
    if inv is None:
        raise ValueError(f"Investigation '{investigation_id}' not found.")
    if inv.status == "closed":
        raise ValueError(f"Investigation '{investigation_id}' is already closed.")
    inv.status = "closed"
    await db.commit()
    await db.refresh(inv)
    return inv


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


async def get_investigation_summary(
    db: AsyncSession,
    investigation_id: str,
) -> dict | None:
    """
    Return a summary dict for an investigation:
    {
        "id": ...,
        "name": ...,
        "status": ...,
        "created_at": ...,
        "updated_at": ...,
        "target_count": N,
        "finding_count": N,
        "evidence_count": N,
        "targets": [
            {
                "id": ..., "type": ..., "value": ..., "role": ...,
                "finding_count": N
            },
            ...
        ]
    }

    Returns None if the investigation does not exist.
    Counts are computed with aggregate queries to avoid loading all rows.
    """
    inv = await get_investigation(db, investigation_id)
    if inv is None:
        return None

    target_ids = [it.target_id for it in inv.targets]

    # Finding count across all targets
    finding_count = 0
    evidence_count = 0
    target_summaries = []

    for it in inv.targets:
        tid = it.target_id

        f_count_stmt = select(func.count()).where(Finding.target_id == tid)
        f_count = (await db.execute(f_count_stmt)).scalar() or 0

        # Evidence count for this target's findings
        e_count_stmt = (
            select(func.count(Evidence.id))
            .join(Finding, Evidence.finding_id == Finding.id)
            .where(Finding.target_id == tid)
        )
        e_count = (await db.execute(e_count_stmt)).scalar() or 0

        finding_count += f_count
        evidence_count += e_count

        target_summaries.append(
            {
                "id": it.target.id,
                "type": it.target.type,
                "value": it.target.value,
                "role": it.role,
                "added_at": str(it.added_at),
                "finding_count": f_count,
            }
        )

    return {
        "id": inv.id,
        "name": inv.name,
        "description": inv.description,
        "status": inv.status,
        "created_at": str(inv.created_at),
        "updated_at": str(inv.updated_at),
        "target_count": len(target_ids),
        "finding_count": finding_count,
        "evidence_count": evidence_count,
        "targets": target_summaries,
    }
