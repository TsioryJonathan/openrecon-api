"""
app/core/deduplicator.py

Prevents duplicate Findings in the database.

Deduplication key: (target_id, type, normalized_value).

If a Finding with the same key already exists:
- The existing Finding is kept (not replaced).
- New Evidence is added to the existing Finding (sources accumulate).
- The existing Finding's confidence may be upgraded if the new data
  justifies a higher level (POSSIBLE → LIKELY → CONFIRMED).

If no existing Finding matches:
- The new Finding is inserted normally.

This produces the correct end state:
    Finding: api.example.com
    Evidence:
    - source: dns,        type: dns_record
    - source: crt.sh,     type: certificate_entry
    - source: http,       type: http_response

instead of three duplicate Findings for the same subdomain.

The deduplicator never removes data. It only decides where new evidence
should be attached.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.confidence import Confidence
from app.core.normalizer import normalize_finding_value
from app.models.Finding import Finding

logger = logging.getLogger(__name__)

# Confidence upgrade ladder — higher index = higher confidence.
_CONFIDENCE_RANK: dict[str, int] = {
    Confidence.POSSIBLE: 0,
    Confidence.LIKELY: 1,
    Confidence.CONFIRMED: 2,
}


async def find_existing(
    db: AsyncSession,
    *,
    target_id: str,
    finding_type: str,
    normalized_value: str,
) -> Finding | None:
    """
    Return an existing Finding matching (target_id, type, normalized_value),
    or None if no duplicate exists.
    """
    stmt = select(Finding).where(
        Finding.target_id == target_id,
        Finding.type == finding_type,
        Finding.normalized_value == normalized_value,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def maybe_upgrade_confidence(
    db: AsyncSession,
    finding: Finding,
    new_confidence: str,
    new_reason: str,
) -> bool:
    """
    Upgrade the confidence of an existing Finding if the new level is higher.

    Returns True if the confidence was upgraded, False if unchanged.
    """
    current_rank = _CONFIDENCE_RANK.get(finding.confidence, 0)
    new_rank = _CONFIDENCE_RANK.get(new_confidence, 0)

    if new_rank > current_rank:
        old = finding.confidence
        finding.confidence = new_confidence
        finding.confidence_reason = (
            f"{finding.confidence_reason} | Upgraded from {old}: {new_reason}"
        )
        await db.flush()
        logger.info(
            "Confidence upgraded: finding_id=%s %s → %s",
            finding.id,
            old,
            new_confidence,
        )
        return True

    return False


def prepare_findings_for_storage(
    findings_data: list[dict],
) -> list[dict]:
    """
    Enrich each finding dict with its normalized_value before storage.

    This is a pure function (no DB access) so it can be tested without
    a session. Called by store_module_result before the dedup DB lookup.

    Mutates each dict in place by adding "normalized_value".
    Returns the same list for chaining convenience.
    """
    for f in findings_data:
        f["normalized_value"] = normalize_finding_value(f["type"], f["value"])
    return findings_data


async def deduplicate_findings(
    db: AsyncSession,
    *,
    target_id: str,
    findings_data: list[dict],
    evidence_data: list[dict],
) -> tuple[list[dict], list[dict], dict[int, str]]:
    """
    Split incoming findings into new ones and duplicates.

    For each finding in findings_data:
    - If no existing Finding matches → keep in new_findings / new_evidence.
    - If a duplicate exists → skip insertion, but record the existing
      finding_id so its evidence can still be attached.

    Returns:
    - new_findings: findings that need to be inserted.
    - new_evidence: evidence for new_findings (same-index correspondence).
    - existing_finding_ids: dict mapping original index → existing finding_id
      for duplicates. The caller attaches evidence to these existing findings.

    Precondition: findings_data must have been processed by
    prepare_findings_for_storage() so each dict has a "normalized_value" key.
    """
    new_findings: list[dict] = []
    new_evidence: list[dict] = []
    existing_finding_ids: dict[int, str] = {}

    for i, f_data in enumerate(findings_data):
        normalized = f_data.get("normalized_value") or normalize_finding_value(
            f_data["type"], f_data["value"]
        )

        existing = await find_existing(
            db,
            target_id=target_id,
            finding_type=f_data["type"],
            normalized_value=normalized,
        )

        if existing:
            logger.info(
                "Dedup: finding type=%s value=%r already exists as id=%s — skipping insert, "
                "attaching evidence to existing.",
                f_data["type"],
                f_data["value"],
                existing.id,
            )
            existing_finding_ids[i] = existing.id

            # Opportunistically upgrade confidence.
            await maybe_upgrade_confidence(
                db,
                existing,
                f_data.get("confidence", Confidence.POSSIBLE),
                f_data.get("confidence_reason", ""),
            )
        else:
            new_findings.append(f_data)
            if i < len(evidence_data):
                new_evidence.append(evidence_data[i])

    return new_findings, new_evidence, existing_finding_ids
