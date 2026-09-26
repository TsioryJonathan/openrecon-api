"""
app/services/report.py

Generates investigation reports from stored data.

Rules:
- Never invent conclusions not supported by findings/evidence/relations.
- Every claim in the report must trace back to a Finding or Evidence row.
- The report is built from data already in the DB — it never triggers
  new scans or correlation runs.
- Supports two output formats: JSON (structured dict) and Markdown (human-readable).

Report structure:
    Investigation metadata
    Targets
    Findings (grouped by target, sorted by type then confidence)
    Evidence (grouped by finding)
    Relations (sorted by type)
    Timeline (all observed_at timestamps, chronological)
    Sources (unique modules/tools referenced)
    Summary statistics
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.Finding import Finding
from app.models.Investigation import Investigation
from app.models.InvestigationTarget import InvestigationTarget
from app.models.Relation import Relation

logger = logging.getLogger(__name__)

# Confidence display order (highest first)
_CONFIDENCE_ORDER = {"CONFIRMED": 0, "LIKELY": 1, "POSSIBLE": 2}


async def build_report_data(
    db: AsyncSession,
    investigation_id: str,
) -> dict | None:
    """
    Load all data for an investigation and assemble a structured report dict.

    Returns None if the investigation does not exist.

    The returned dict is format-agnostic — render_json() and render_markdown()
    both consume it.

    Structure:
    {
        "investigation": { id, name, description, status, created_at, updated_at },
        "generated_at": ISO timestamp,
        "targets": [
            {
                "id", "type", "value", "role", "added_at",
                "findings": [
                    {
                        "id", "type", "value", "source", "confidence",
                        "confidence_reason", "observed_at",
                        "evidence": [{ id, source, evidence_type, value, observed_at }]
                    }
                ]
            }
        ],
        "relations": [
            { id, source_finding_id, target_finding_id, relation_type,
              confidence, reason, created_at }
        ],
        "timeline": [
            { timestamp, event_type, description }
        ],
        "stats": {
            "target_count", "finding_count", "evidence_count",
            "relation_count", "source_count",
            "by_finding_type": { type: count },
            "by_confidence": { confidence: count },
            "by_relation_type": { type: count },
        },
        "sources": [ "sherlock", "dns", ... ]
    }
    """
    # Load investigation
    stmt = (
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .options(selectinload(Investigation.targets).selectinload(InvestigationTarget.target))
    )
    result = await db.execute(stmt)
    inv = result.scalars().first()
    if inv is None:
        return None

    # Collect all target_ids
    target_links = {it.target_id: it for it in inv.targets}
    target_ids = list(target_links.keys())

    # Load all findings with evidence for all targets
    findings_by_target: dict[str, list[dict]] = {tid: [] for tid in target_ids}
    all_finding_ids: list[str] = []
    all_sources: set[str] = set()
    by_finding_type: dict[str, int] = {}
    by_confidence: dict[str, int] = {}

    if target_ids:
        f_stmt = (
            select(Finding)
            .where(Finding.target_id.in_(target_ids))
            .options(selectinload(Finding.evidence))
            .order_by(Finding.observed_at)
        )
        f_result = await db.execute(f_stmt)
        findings = f_result.scalars().all()

        for f in findings:
            all_finding_ids.append(f.id)
            all_sources.add(f.source)
            by_finding_type[f.type] = by_finding_type.get(f.type, 0) + 1
            by_confidence[f.confidence] = by_confidence.get(f.confidence, 0) + 1

            evidence_list = sorted(
                [
                    {
                        "id": e.id,
                        "source": e.source,
                        "evidence_type": e.evidence_type,
                        "value": e.value,
                        "observed_at": e.observed_at.isoformat() if e.observed_at else None,
                    }
                    for e in f.evidence
                ],
                key=lambda e: e["observed_at"] or "",
            )
            for e in f.evidence:
                all_sources.add(e.source)

            findings_by_target[f.target_id].append(
                {
                    "id": f.id,
                    "type": f.type,
                    "value": f.value,
                    "source": f.source,
                    "confidence": f.confidence,
                    "confidence_reason": f.confidence_reason,
                    "observed_at": f.observed_at.isoformat() if f.observed_at else None,
                    "evidence": evidence_list,
                }
            )

    # Sort findings within each target: by confidence, then type, then value
    for findings_list in findings_by_target.values():
        findings_list.sort(
            key=lambda f: (
                _CONFIDENCE_ORDER.get(f["confidence"], 9),
                f["type"],
                f["value"],
            )
        )

    # Load relations where either end is in our finding set
    relations_data: list[dict] = []
    by_relation_type: dict[str, int] = {}

    if all_finding_ids:
        r_stmt = (
            select(Relation)
            .where(
                Relation.source_finding_id.in_(all_finding_ids)
                | Relation.target_finding_id.in_(all_finding_ids)
            )
            .order_by(Relation.relation_type, Relation.created_at)
        )
        r_result = await db.execute(r_stmt)
        relations = r_result.scalars().all()

        seen_rel_ids: set[str] = set()
        for r in relations:
            if r.id in seen_rel_ids:
                continue
            seen_rel_ids.add(r.id)
            by_relation_type[r.relation_type] = by_relation_type.get(r.relation_type, 0) + 1
            relations_data.append(
                {
                    "id": r.id,
                    "source_finding_id": r.source_finding_id,
                    "target_finding_id": r.target_finding_id,
                    "relation_type": r.relation_type,
                    "confidence": r.confidence,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )

    # Build timeline: merge investigation created_at, target added_at, finding observed_at
    timeline: list[dict] = []

    timeline.append(
        {
            "timestamp": inv.created_at.isoformat() if inv.created_at else None,
            "event_type": "investigation_opened",
            "description": f"Investigation '{inv.name}' opened.",
        }
    )

    for it in inv.targets:
        timeline.append(
            {
                "timestamp": it.added_at.isoformat() if it.added_at else None,
                "event_type": "target_added",
                "description": f"Target {it.target.type}:{it.target.value} added"
                + (f" as {it.role}" if it.role else "")
                + ".",
            }
        )

    for flist in findings_by_target.values():
        for fd in flist:
            if fd["observed_at"]:
                timeline.append(
                    {
                        "timestamp": fd["observed_at"],
                        "event_type": "finding_observed",
                        "description": f"[{fd['type'].upper()}] {fd['value']} "
                        f"(source: {fd['source']}, confidence: {fd['confidence']})",
                    }
                )

    timeline.sort(key=lambda e: e["timestamp"] or "")

    # Assemble targets section
    targets_out = []
    for it in sorted(inv.targets, key=lambda x: x.added_at or datetime.min.replace(tzinfo=UTC)):
        targets_out.append(
            {
                "id": it.target.id,
                "type": it.target.type,
                "value": it.target.value,
                "role": it.role,
                "added_at": it.added_at.isoformat() if it.added_at else None,
                "findings": findings_by_target.get(it.target_id, []),
            }
        )

    # Evidence count
    evidence_count = sum(len(f["evidence"]) for flist in findings_by_target.values() for f in flist)

    return {
        "investigation": {
            "id": inv.id,
            "name": inv.name,
            "description": inv.description,
            "status": inv.status,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "targets": targets_out,
        "relations": relations_data,
        "timeline": timeline,
        "sources": sorted(all_sources),
        "stats": {
            "target_count": len(target_ids),
            "finding_count": sum(by_finding_type.values()),
            "evidence_count": evidence_count,
            "relation_count": len(relations_data),
            "source_count": len(all_sources),
            "by_finding_type": by_finding_type,
            "by_confidence": by_confidence,
            "by_relation_type": by_relation_type,
        },
    }


def render_json(report_data: dict) -> dict:
    """Return the report data as-is (already a structured dict)."""
    return report_data


def render_markdown(report_data: dict) -> str:
    """
    Render the report data as a Markdown document.

    Structure:
    # Investigation: <name>
    ## Summary
    ## Targets & Findings
    ### Target: <type>:<value>
    #### Findings
    ## Relations
    ## Timeline
    ## Sources
    """
    inv = report_data["investigation"]
    stats = report_data["stats"]
    lines: list[str] = []

    # Header
    lines += [
        f"# Investigation: {inv['name']}",
        "",
        f"**Status:** {inv['status']}  ",
        f"**Created:** {inv['created_at']}  ",
        f"**Generated:** {report_data['generated_at']}  ",
    ]
    if inv.get("description"):
        lines += ["", f"> {inv['description']}", ""]

    # Summary
    lines += [
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Targets | {stats['target_count']} |",
        f"| Findings | {stats['finding_count']} |",
        f"| Evidence | {stats['evidence_count']} |",
        f"| Relations | {stats['relation_count']} |",
        f"| Sources | {stats['source_count']} |",
        "",
    ]

    if stats["by_confidence"]:
        lines += ["**Findings by confidence:**", ""]
        for conf, count in sorted(
            stats["by_confidence"].items(), key=lambda x: _CONFIDENCE_ORDER.get(x[0], 9)
        ):
            lines.append(f"- {conf}: {count}")
        lines.append("")

    if stats["by_finding_type"]:
        lines += ["**Findings by type:**", ""]
        for ftype, count in sorted(stats["by_finding_type"].items()):
            lines.append(f"- {ftype}: {count}")
        lines.append("")

    # Targets & Findings
    lines += ["## Targets & Findings", ""]

    for target in report_data["targets"]:
        role_label = f" *(role: {target['role']})*" if target["role"] else ""
        lines += [
            f"### {target['type'].upper()}: `{target['value']}`{role_label}",
            "",
        ]

        findings = target["findings"]
        if not findings:
            lines += ["*No findings recorded for this target.*", ""]
            continue

        for f in findings:
            conf_badge = f"[{f['confidence']}]"
            lines += [
                f"#### {conf_badge} `{f['value']}`",
                "",
                f"- **Type:** {f['type']}",
                f"- **Source:** {f['source']}",
                f"- **Observed:** {f['observed_at']}",
                f"- **Reason:** {f['confidence_reason']}",
            ]
            if f["evidence"]:
                lines += ["- **Evidence:**"]
                for e in f["evidence"]:
                    lines.append(
                        f"  - [{e['evidence_type']}] `{e['value']}` *(source: {e['source']})*"
                    )
            lines.append("")

    # Relations
    lines += ["## Relations", ""]
    if not report_data["relations"]:
        lines += ["*No relations found. Run correlation first.*", ""]
    else:
        if stats.get("by_relation_type"):
            lines += ["**Relations by type:**", ""]
            for rtype, count in sorted(stats["by_relation_type"].items()):
                lines.append(f"- {rtype}: {count}")
            lines.append("")

        lines += [
            "| Type | Confidence | Reason |",
            "|------|-----------|--------|",
        ]
        for r in report_data["relations"]:
            reason_short = r["reason"][:80] + "…" if len(r["reason"]) > 80 else r["reason"]
            lines.append(f"| {r['relation_type']} | {r['confidence']} | {reason_short} |")
        lines.append("")

    # Timeline
    lines += ["## Timeline", ""]
    for event in report_data["timeline"]:
        ts = (event["timestamp"] or "")[:19].replace("T", " ")
        lines.append(f"- `{ts}` **{event['event_type']}** — {event['description']}")
    lines.append("")

    # Sources
    lines += ["## Sources", ""]
    for src in report_data["sources"]:
        lines.append(f"- {src}")
    lines.append("")

    return "\n".join(lines)
