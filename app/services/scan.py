"""
app/services/scan.py

Orchestrates the core OpenRecon pipeline for a single scan:

    Target
      ↓
    Module (currently SherlockModule for username targets)
      ↓
    ModuleResult (Finding[] + Evidence[])
      ↓
    Storage

This is the first real end-to-end pipeline. It is intentionally simple:
one target type, one module, one storage call. The orchestrator (Phase 7)
will extend this with multi-module chaining and adaptive recon.

Rules:
- Never import routers or Pydantic schemas here.
- Never call the DB directly — delegate to app.services.storage.
- Never call modules from routers — routers call this service.
- Errors from the module are captured and returned, never swallowed silently.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Evidence import Evidence
from app.models.Finding import Finding
from app.models.Target import Target
from app.modules.sherlock import SherlockModule
from app.services.storage import get_or_create_target, store_module_result

logger = logging.getLogger(__name__)

# Module registry — maps target_type to the module that handles it.
# When new modules are added (DNS, RDAP, HTTP...), register them here.
_MODULE_REGISTRY: dict[str, list] = {
    "username": [SherlockModule()],
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
    - errors: list of error strings from module execution.
      A scan can be partially successful (some findings + some errors).
    - modules_run: names of modules that were executed.
    """

    target: Target
    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    modules_run: list[str] = field(default_factory=list)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)


async def run_scan(
    db: AsyncSession,
    *,
    target_type: str,
    target_value: str,
    **kwargs,
) -> ScanResult:
    """
    Run a full scan pipeline for a given target.

    Steps:
    1. Validate target_type is supported.
    2. Get or create the Target in the DB (deduplication by type+value).
    3. For each module registered for this target_type:
       a. Execute the module.
       b. Collect errors.
       c. If findings were produced, persist them via store_module_result.
    4. Return a ScanResult with all stored findings, evidence, and any errors.

    Args:
        db: async SQLAlchemy session.
        target_type: canonical type string (e.g. "username").
        target_value: the value to investigate (e.g. "john123").
        **kwargs: passed through to the module's execute() method.
                  For SherlockModule: sites=list[str].

    Returns:
        ScanResult. Never raises — all errors are captured in ScanResult.errors.
    """
    if target_type not in _MODULE_REGISTRY:
        supported = ", ".join(SUPPORTED_TARGET_TYPES)
        # We still need a Target object to return — create a minimal one.
        target, _ = await get_or_create_target(db, type=target_type, value=target_value)
        return ScanResult(
            target=target,
            errors=[(f"Unsupported target type '{target_type}'. Supported types: {supported}.")],
        )

    # Step 1 — Get or create the Target.
    target, created = await get_or_create_target(db, type=target_type, value=target_value)
    logger.info(
        "run_scan: target id=%s type=%s value=%s created=%s",
        target.id,
        target_type,
        target_value,
        created,
    )

    all_findings: list[Finding] = []
    all_evidence: list[Evidence] = []
    all_errors: list[str] = []
    modules_run: list[str] = []

    # Step 2 — Execute each registered module for this target type.
    for module in _MODULE_REGISTRY[target_type]:
        modules_run.append(module.name)
        logger.info(
            "run_scan: executing module=%s for target_id=%s",
            module.name,
            target.id,
        )

        try:
            result = await module.execute(target_type, target_value, **kwargs)
        except Exception as e:
            # Module.execute() should never raise, but we catch anyway.
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

        # Step 3 — Persist findings + evidence if any were produced.
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
    )
