"""
app/services/correlation.py

Persistence layer and orchestrator for the correlation engine.

run_correlation(db, target_id) is the primary entry point:
1. Load all Findings for the target.
2. Pass them to the correlator (pure, no DB).
3. Persist new Relations (skip already-existing ones).
4. Return a CorrelationResult.

For investigation-level correlation, run_correlation_for_investigation()
runs correlation across all targets in an investigation and collects
all resulting relations.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlator import run_all_rules
from app.models.Finding import Finding
from app.models.Relation import Relation

logger = logging.getLogger(__name__)


@dataclass
class CorrelationResult:
    """
    Result of a correlation run.

    Attributes:
    - target_id: the target that was correlated (or None for investigation-level).
    - relations_created: new Relation ORM objects inserted this run.
    - relations_skipped: count of relations that already existed (deduped).
    - errors: any errors encountered.
    """

    target_id: str | None
    relations_created: list[Relation] = field(default_factory=list)
    relations_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return len(self.relations_created)


async def _load_findings_as_dicts(
    db: AsyncSession,
    target_id: str,
) -> list[dict]:
    """
    Load all Findings for a target as plain dicts for the correlator.
    The correlator is a pure function and must not receive ORM objects.
    """
    stmt = select(Finding).where(Finding.target_id == target_id)
    result = await db.execute(stmt)
    findings = result.scalars().all()
    return [
        {
            "id": f.id,
            "type": f.type,
            "value": f.value,
            "normalized_value": f.normalized_value,
            "source": f.source,
            "confidence": f.confidence,
            "target_id": f.target_id,
        }
        for f in findings
    ]


async def _relation_exists(
    db: AsyncSession,
    source_finding_id: str,
    target_finding_id: str,
    relation_type: str,
) -> bool:
    """Check if an identical relation already exists."""
    stmt = select(Relation).where(
        Relation.source_finding_id == source_finding_id,
        Relation.target_finding_id == target_finding_id,
        Relation.relation_type == relation_type,
    )
    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def run_correlation(
    db: AsyncSession,
    target_id: str,
) -> CorrelationResult:
    """
    Run the full correlation pipeline for a single target.

    Steps:
    1. Load all findings for this target as plain dicts.
    2. Run all correlation rules (pure).
    3. For each proposed relation:
       a. Skip if it already exists (idempotent).
       b. Persist the new Relation.
    4. Return CorrelationResult.

    Safe to call multiple times — already-existing relations are skipped.
    Never raises — errors captured in CorrelationResult.errors.
    """
    result = CorrelationResult(target_id=target_id)

    try:
        findings = await _load_findings_as_dicts(db, target_id)
    except Exception as e:  # noqa: BLE001
        result.errors.append(f"Failed to load findings for target '{target_id}': {e}")
        return result

    if not findings:
        logger.info(
            "run_correlation: no findings for target_id=%s — nothing to correlate", target_id
        )
        return result

    proposed = run_all_rules(findings)
    logger.info(
        "run_correlation: target_id=%s findings=%d proposed_relations=%d",
        target_id,
        len(findings),
        len(proposed),
    )

    try:
        for rel_data in proposed:
            already_exists = await _relation_exists(
                db,
                rel_data["source_finding_id"],
                rel_data["target_finding_id"],
                rel_data["relation_type"],
            )
            if already_exists:
                result.relations_skipped += 1
                continue

            rel = Relation(
                source_finding_id=rel_data["source_finding_id"],
                target_finding_id=rel_data["target_finding_id"],
                relation_type=rel_data["relation_type"],
                confidence=rel_data["confidence"],
                reason=rel_data["reason"],
                meta=rel_data.get("metadata"),
            )
            db.add(rel)
            result.relations_created.append(rel)

        await db.commit()
        for rel in result.relations_created:
            await db.refresh(rel)

    except Exception as e:  # noqa: BLE001
        await db.rollback()
        result.errors.append(f"Failed to persist relations for target '{target_id}': {e}")
        return result

    logger.info(
        "run_correlation: target_id=%s created=%d skipped=%d",
        target_id,
        result.created_count,
        result.relations_skipped,
    )
    return result


async def run_correlation_for_investigation(
    db: AsyncSession,
    investigation_id: str,
) -> CorrelationResult:
    """
    Run correlation across all targets in an investigation.

    Loads all findings from every target in the investigation (combined),
    runs correlation on the full set so cross-target relations can be detected,
    then persists all new relations.

    Returns a combined CorrelationResult with target_id=None.
    """
    from app.models.InvestigationTarget import InvestigationTarget

    combined = CorrelationResult(target_id=None)

    # Load all target_ids for this investigation.
    stmt = select(InvestigationTarget).where(
        InvestigationTarget.investigation_id == investigation_id
    )
    result = await db.execute(stmt)
    links = result.scalars().all()

    if not links:
        logger.info(
            "run_correlation_for_investigation: no targets in investigation_id=%s",
            investigation_id,
        )
        return combined

    # Gather all findings across all targets.
    all_findings: list[dict] = []
    for link in links:
        try:
            findings = await _load_findings_as_dicts(db, link.target_id)
            all_findings.extend(findings)
        except Exception as e:  # noqa: BLE001
            combined.errors.append(f"Failed to load findings for target '{link.target_id}': {e}")

    if not all_findings:
        return combined

    proposed = run_all_rules(all_findings)
    logger.info(
        "run_correlation_for_investigation: investigation_id=%s "
        "total_findings=%d proposed_relations=%d",
        investigation_id,
        len(all_findings),
        len(proposed),
    )

    try:
        for rel_data in proposed:
            already_exists = await _relation_exists(
                db,
                rel_data["source_finding_id"],
                rel_data["target_finding_id"],
                rel_data["relation_type"],
            )
            if already_exists:
                combined.relations_skipped += 1
                continue

            rel = Relation(
                source_finding_id=rel_data["source_finding_id"],
                target_finding_id=rel_data["target_finding_id"],
                relation_type=rel_data["relation_type"],
                confidence=rel_data["confidence"],
                reason=rel_data["reason"],
                meta=rel_data.get("metadata"),
            )
            db.add(rel)
            combined.relations_created.append(rel)

        await db.commit()
        for rel in combined.relations_created:
            await db.refresh(rel)

    except Exception as e:  # noqa: BLE001
        await db.rollback()
        combined.errors.append(
            f"Failed to persist relations for investigation '{investigation_id}': {e}"
        )

    logger.info(
        "run_correlation_for_investigation: investigation_id=%s created=%d skipped=%d",
        investigation_id,
        combined.created_count,
        combined.relations_skipped,
    )
    return combined


async def get_relations_for_target(
    db: AsyncSession,
    target_id: str,
) -> list[Relation]:
    """
    Return all Relations where either the source or target Finding
    belongs to the given target_id.
    """
    stmt = (
        select(Relation)
        .join(Finding, Relation.source_finding_id == Finding.id)
        .where(Finding.target_id == target_id)
    )
    result = await db.execute(stmt)
    source_rels = list(result.scalars().all())

    stmt2 = (
        select(Relation)
        .join(Finding, Relation.target_finding_id == Finding.id)
        .where(Finding.target_id == target_id)
    )
    result2 = await db.execute(stmt2)
    target_rels = list(result2.scalars().all())

    # Deduplicate by id.
    seen: set[str] = set()
    combined: list[Relation] = []
    for r in source_rels + target_rels:
        if r.id not in seen:
            seen.add(r.id)
            combined.append(r)
    return combined
