"""
app/services/adaptive.py

Adaptive recon orchestrator.

run_adaptive_scan() takes an initial target, runs a scan, extracts leads
from the findings, filters them, and recursively scans eligible leads up
to a configured depth limit.

Safety guarantees:
- Depth limit: never exceeds max_depth hops from the initial target.
- Session dedup: a (target_type, target_value) pair is never scanned twice
  in the same adaptive run, regardless of how many leads point to it.
- Scope check: every lead is checked against the scope before scanning.
  Out-of-scope leads are recorded but not scanned.
- Rate limit: applied per (target, module) via the existing rate limiter.
- No infinite loops: the session_seen set and depth counter guarantee
  termination even if findings somehow reference each other circularly.

Output:
- AdaptiveResult with all scan results per hop, total findings/evidence,
  leads extracted, leads skipped (out of scope / deduped / unsupported),
  and any errors.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.adaptive import Lead, extract_leads
from app.core.ratelimiter import RateLimiter, get_rate_limiter
from app.core.scope import UNRESTRICTED, Scope
from app.models.Evidence import Evidence
from app.models.Finding import Finding
from app.services.scan import SUPPORTED_TARGET_TYPES, ScanResult, run_scan

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEPTH = 2  # hops beyond the initial scan


@dataclass
class HopResult:
    """Result of one hop in the adaptive scan tree."""

    depth: int
    target_type: str
    target_value: str
    source_lead: Lead | None  # None for depth=0 (initial target)
    scan_result: ScanResult
    leads_extracted: list[Lead] = field(default_factory=list)


@dataclass
class AdaptiveResult:
    """
    Complete result of an adaptive recon run.

    Attributes:
    - hops: ordered list of HopResult, depth=0 first.
    - total_findings: all unique Finding ORM objects across all hops.
    - total_evidence: all unique Evidence ORM objects across all hops.
    - leads_skipped: leads that were not scanned, with reasons.
    - errors: all errors across all hops.
    - targets_scanned: set of (type, value) tuples scanned this run.
    """

    hops: list[HopResult] = field(default_factory=list)
    total_findings: list[Finding] = field(default_factory=list)
    total_evidence: list[Evidence] = field(default_factory=list)
    leads_skipped: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    targets_scanned: set[tuple] = field(default_factory=set)

    @property
    def hop_count(self) -> int:
        return len(self.hops)

    @property
    def finding_count(self) -> int:
        return len(self.total_findings)

    @property
    def evidence_count(self) -> int:
        return len(self.total_evidence)


async def run_adaptive_scan(
    db: AsyncSession,
    *,
    target_type: str,
    target_value: str,
    options: dict | None = None,
    scope: Scope | None = None,
    rate_limiter: RateLimiter | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    investigation_id: str | None = None,
    owner_id: str | None = None,
) -> AdaptiveResult:
    """
    Run an adaptive recon scan starting from a single target.

    Depth 0: scan the initial target.
    Depth 1: scan leads extracted from depth-0 findings.
    Depth 2: scan leads extracted from depth-1 findings.
    ... up to max_depth.

    At each depth, leads are filtered:
    - Already scanned in this run → skip (session dedup).
    - Target type not supported by any module → skip.
    - Out of scope → skip (recorded in leads_skipped).
    - Rate limited → captured in scan errors, scan attempt still made.

    Args:
        db: async SQLAlchemy session.
        target_type: initial target type.
        target_value: initial target value.
        options: options passed to ALL modules at ALL depths.
        scope: scope enforcement (default: UNRESTRICTED).
        rate_limiter: rate limiter instance (default: singleton).
        max_depth: maximum number of hops beyond the initial scan (default 2).
        investigation_id: if set, each scanned target is linked to this
            investigation via add_target_to_investigation (idempotent).
        owner_id: ownership scope passed through to investigation services.
    """
    scope = scope or UNRESTRICTED
    rate_limiter = rate_limiter or get_rate_limiter()
    options = options or {}

    result = AdaptiveResult()

    # session_seen: set of (target_type, target_value) scanned this run.
    session_seen: set[tuple] = set()

    # Queue of (depth, target_type, target_value, source_lead).
    queue: list[tuple[int, str, str, Lead | None]] = [(0, target_type, target_value, None)]

    while queue:
        depth, ttype, tvalue, source_lead = queue.pop(0)

        # Session dedup guard.
        key = (ttype, tvalue)
        if key in session_seen:
            result.leads_skipped.append(
                {
                    "target_type": ttype,
                    "target_value": tvalue,
                    "reason": "Already scanned in this adaptive run.",
                    "depth": depth,
                }
            )
            continue
        session_seen.add(key)
        result.targets_scanned.add(key)

        # Depth guard.
        if depth > max_depth:
            result.leads_skipped.append(
                {
                    "target_type": ttype,
                    "target_value": tvalue,
                    "reason": f"Depth limit reached ({max_depth}).",
                    "depth": depth,
                }
            )
            continue

        # Target type support guard.
        if ttype not in SUPPORTED_TARGET_TYPES:
            result.leads_skipped.append(
                {
                    "target_type": ttype,
                    "target_value": tvalue,
                    "reason": f"Target type '{ttype}' is not supported by any module.",
                    "depth": depth,
                }
            )
            continue

        # Scope guard.
        scope_check = scope.check(ttype, tvalue)
        if not scope_check.allowed:
            result.leads_skipped.append(
                {
                    "target_type": ttype,
                    "target_value": tvalue,
                    "reason": f"Out of scope: {scope_check.reason}",
                    "depth": depth,
                }
            )
            logger.info(
                "run_adaptive_scan: skipping out-of-scope target %s:%s depth=%d",
                ttype,
                tvalue,
                depth,
            )
            continue

        # Run the scan.
        logger.info(
            "run_adaptive_scan: scanning %s:%s depth=%d/%d",
            ttype,
            tvalue,
            depth,
            max_depth,
        )
        scan_result = await run_scan(
            db,
            target_type=ttype,
            target_value=tvalue,
            options=options,
            scope=scope,
            rate_limiter=rate_limiter,
        )

        # Optionally link to investigation.
        if investigation_id:
            from app.services import investigation as inv_service

            try:
                role = "initial_target" if depth == 0 else f"adaptive_depth_{depth}"
                await inv_service.add_target_to_investigation(
                    db,
                    investigation_id=investigation_id,
                    target_id=scan_result.target.id,
                    role=role,
                    owner_id=owner_id,
                )
            except ValueError as e:
                if "already linked" not in str(e):
                    logger.warning(
                        "run_adaptive_scan: failed to link target to investigation: %s", e
                    )

        # Collect findings and evidence.
        result.total_findings.extend(scan_result.findings)
        result.total_evidence.extend(scan_result.evidence)
        result.errors.extend(scan_result.errors)

        # Extract leads from this scan's findings — only if depth < max_depth.
        leads_here: list[Lead] = []
        if depth < max_depth and scan_result.findings:
            findings_dicts = [
                {
                    "id": f.id,
                    "type": f.type,
                    "value": f.value,
                    "normalized_value": f.normalized_value,
                    "source": f.source,
                }
                for f in scan_result.findings
            ]
            leads_here = extract_leads(findings_dicts)
            logger.info(
                "run_adaptive_scan: depth=%d extracted %d leads from %d findings",
                depth,
                len(leads_here),
                len(scan_result.findings),
            )

            # Enqueue new leads for depth+1.
            for lead in leads_here:
                if (lead.target_type, lead.target_value) not in session_seen:
                    queue.append((depth + 1, lead.target_type, lead.target_value, lead))
                else:
                    result.leads_skipped.append(
                        {
                            "target_type": lead.target_type,
                            "target_value": lead.target_value,
                            "reason": "Already scanned in this adaptive run (session dedup).",
                            "depth": depth + 1,
                            "rule": lead.rule,
                        }
                    )

        hop = HopResult(
            depth=depth,
            target_type=ttype,
            target_value=tvalue,
            source_lead=source_lead,
            scan_result=scan_result,
            leads_extracted=leads_here,
        )
        result.hops.append(hop)

    logger.info(
        "run_adaptive_scan: complete. hops=%d findings=%d evidence=%d skipped=%d errors=%d",
        result.hop_count,
        result.finding_count,
        result.evidence_count,
        len(result.leads_skipped),
        len(result.errors),
    )
    return result
