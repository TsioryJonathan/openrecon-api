"""
app/services/scan.py

Orchestrates the core OpenRecon pipeline for a single scan:

    Target
      ↓
    Scope check          ← NEW: blocks out-of-scope targets
      ↓
    Rate limit check     ← NEW: prevents rapid re-scan of same target
      ↓
    Module(s)
      ↓
    Normalization + Deduplication
      ↓
    Storage

Scope and rate limit violations are captured in ScanResult.errors —
they never raise exceptions.

Rules:
- Never import routers or Pydantic schemas here.
- Never call the DB directly — delegate to app.services.storage.
- Never call modules from routers — routers call this service.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimiter import RateLimiter, get_rate_limiter
from app.core.scope import UNRESTRICTED, Scope
from app.models.Evidence import Evidence
from app.models.Finding import Finding
from app.models.Target import Target
from app.modules.dns import DNSModule
from app.modules.rdap import RDAPModule
from app.modules.sherlock import SherlockModule
from app.services import investigation as inv_service
from app.services.storage import get_or_create_target, store_module_result

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------
_MODULE_REGISTRY: dict[str, list] = {
    "username": [SherlockModule()],
    "domain": [DNSModule(), RDAPModule()],
}

SUPPORTED_TARGET_TYPES = list(_MODULE_REGISTRY.keys())


@dataclass
class ScanResult:
    """
    The result of a single scan pipeline execution.

    Attributes:
    - target: the Target ORM object that was created or reused.
    - findings: all Finding ORM objects stored in this scan.
    - evidence: all Evidence ORM objects stored in this scan.
    - errors: list of error strings (module errors, scope violations,
      rate limit hits).
    - modules_run: names of modules that were executed.
    - scope_violations: list of scope violation reason strings.
    - rate_limited: list of (module_name, reason) pairs that were skipped.
    """

    target: Target
    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    modules_run: list[str] = field(default_factory=list)
    scope_violations: list[str] = field(default_factory=list)
    rate_limited: list[tuple[str, str]] = field(default_factory=list)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    @property
    def was_blocked(self) -> bool:
        """True if the scan was entirely blocked (scope or rate limit, no findings)."""
        return (bool(self.scope_violations) or bool(self.rate_limited)) and not self.findings


async def run_scan(
    db: AsyncSession,
    *,
    target_type: str,
    target_value: str,
    options: dict | None = None,
    scope: Scope | None = None,
    rate_limiter: RateLimiter | None = None,
) -> ScanResult:
    """
    Run a full scan pipeline for a given target.

    Steps:
    1. Validate target_type is supported.
    2. Get or create the Target.
    3. Check scope — if the target is out of scope, return immediately
       with a ScopeViolation error and no findings.
    4. For each registered module:
       a. Check rate limit — if too soon, skip this module and record it.
       b. Execute the module.
       c. On success: record the rate limit timestamp.
       d. Persist findings + evidence.
    5. Return ScanResult.

    Args:
        db: async SQLAlchemy session.
        target_type: canonical type string.
        target_value: the value to investigate.
        options: module-specific options dict.
        scope: Scope to enforce. Defaults to UNRESTRICTED (no limits).
        rate_limiter: RateLimiter instance. Defaults to process singleton.
    """
    options = options or {}
    scope = scope or UNRESTRICTED
    rate_limiter = rate_limiter or get_rate_limiter()

    if target_type not in _MODULE_REGISTRY:
        supported = ", ".join(SUPPORTED_TARGET_TYPES)
        target, _ = await get_or_create_target(db, type=target_type, value=target_value)
        return ScanResult(
            target=target,
            errors=[f"Unsupported target type '{target_type}'. Supported types: {supported}."],
        )

    target, created = await get_or_create_target(db, type=target_type, value=target_value)
    logger.info(
        "run_scan: target id=%s type=%s value=%s created=%s",
        target.id,
        target_type,
        target_value,
        created,
    )

    # Scope check — applies to the whole target before any module runs.
    scope_result = scope.check(target_type, target_value)
    if not scope_result.allowed:
        logger.warning(
            "run_scan: SCOPE VIOLATION target_type=%s value=%s reason=%s",
            target_type,
            target_value,
            scope_result.reason,
        )
        return ScanResult(
            target=target,
            errors=[f"SCOPE VIOLATION: {scope_result.reason}"],
            scope_violations=[scope_result.reason],
        )

    all_findings: list[Finding] = []
    all_evidence: list[Evidence] = []
    all_errors: list[str] = []
    modules_run: list[str] = []
    rate_limited: list[tuple[str, str]] = []

    for module in _MODULE_REGISTRY[target_type]:
        # Rate limit check — per (target_type, target_value, module_name).
        rl_result = rate_limiter.check_and_record(target_type, target_value, module.name)
        if not rl_result.allowed:
            logger.info(
                "run_scan: RATE LIMITED module=%s target=%s:%s retry_after=%.0fs",
                module.name,
                target_type,
                target_value,
                rl_result.retry_after_seconds,
            )
            rate_limited.append((module.name, rl_result.reason))
            all_errors.append(f"RATE LIMITED [{module.name}]: {rl_result.reason}")
            continue

        modules_run.append(module.name)
        logger.info(
            "run_scan: executing module=%s for target_id=%s",
            module.name,
            target.id,
        )

        try:
            result = await module.execute(target_type, target_value, **options)
        except Exception as e:
            error_msg = f"Module '{module.name}' raised unexpectedly: {e}"
            logger.exception(error_msg)
            all_errors.append(error_msg)
            continue

        if result.errors:
            all_errors.extend(result.errors)
            logger.warning(
                "run_scan: module=%s reported %d error(s) for target_id=%s",
                module.name,
                len(result.errors),
                target.id,
            )

        if result.findings:
            try:
                stored_f, stored_e = await store_module_result(
                    db,
                    target_id=target.id,
                    findings_data=result.findings,
                    evidence_data=result.evidence,
                )
                all_findings.extend(stored_f)
                all_evidence.extend(stored_e)
                logger.info(
                    "run_scan: module=%s stored %d findings, %d evidence",
                    module.name,
                    len(stored_f),
                    len(stored_e),
                )
            except Exception as e:
                error_msg = f"Storage failed for module '{module.name}': {e}"
                logger.exception(error_msg)
                all_errors.append(error_msg)

    return ScanResult(
        target=target,
        findings=all_findings,
        evidence=all_evidence,
        errors=all_errors,
        modules_run=modules_run,
        rate_limited=rate_limited,
    )


async def run_scan_for_investigation(
    db: AsyncSession,
    *,
    investigation_id: str,
    target_type: str,
    target_value: str,
    options: dict | None = None,
    role: str | None = None,
    scope: Scope | None = None,
    rate_limiter: RateLimiter | None = None,
    owner_id: str | None = None,
) -> ScanResult:
    """
    Run a scan and automatically link the target to an investigation.

    Validates investigation exists (and is owned by owner_id) and is open,
    then delegates to run_scan(). Links target to investigation after scan
    (idempotent).

    Raises ValueError if investigation not found or closed.
    Scope violations and rate limit hits are returned in ScanResult, not raised.
    """
    inv = await inv_service.get_investigation(db, investigation_id, owner_id=owner_id)
    if inv is None:
        raise ValueError(f"Investigation '{investigation_id}' not found.")
    if inv.status == "closed":
        raise ValueError(
            f"Investigation '{investigation_id}' is closed. Re-open it before running scans."
        )

    scan_result = await run_scan(
        db,
        target_type=target_type,
        target_value=target_value,
        options=options,
        scope=scope,
        rate_limiter=rate_limiter,
    )

    try:
        await inv_service.add_target_to_investigation(
            db,
            investigation_id=investigation_id,
            target_id=scan_result.target.id,
            role=role,
            owner_id=owner_id,
        )
    except ValueError as e:
        if "already linked" in str(e):
            logger.info(
                "run_scan_for_investigation: target_id=%s already in investigation_id=%s — skipped",
                scan_result.target.id,
                investigation_id,
            )
        else:
            raise

    return scan_result
