"""
app/services/scan.py

Orchestrates the core OpenRecon pipeline for a single scan:

    Target
      ↓
    Module(s) registered for the target type
      ↓
    ModuleResult (Finding[] + Evidence[])
      ↓
    Normalization + Deduplication
      ↓
    Storage

For investigation-scoped scans, the target is also linked to the
investigation after creation (run_scan_for_investigation).

Rules:
- Never import routers or Pydantic schemas here.
- Never call the DB directly — delegate to app.services.storage.
- Never call modules from routers — routers call this service.
- Errors from modules are captured and returned, never swallowed.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.Evidence import Evidence
from app.models.Finding import Finding
from app.models.Target import Target
from app.modules.dns import DNSModule
from app.modules.sherlock import SherlockModule
from app.services import investigation as inv_service
from app.services.storage import get_or_create_target, store_module_result

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------
_MODULE_REGISTRY: dict[str, list] = {
    "username": [SherlockModule()],
    "domain": [DNSModule()],
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
    options: dict | None = None,
) -> ScanResult:
    """
    Run a full scan pipeline for a given target.

    Steps:
    1. Validate target_type is supported.
    2. Get or create the Target (deduplication by type+value).
    3. Execute each registered module, passing options as kwargs.
    4. Persist findings + evidence (normalization + deduplication inside).
    5. Return ScanResult. Never raises.

    Args:
        db: async SQLAlchemy session.
        target_type: canonical type string (e.g. "username", "domain").
        target_value: the value to investigate.
        options: optional dict passed as **kwargs to each module's execute().
            SherlockModule: {"sites": ["GitHub", "Reddit"]}
            DNSModule: no options currently used.
    """
    options = options or {}

    if target_type not in _MODULE_REGISTRY:
        supported = ", ".join(SUPPORTED_TARGET_TYPES)
        target, _ = await get_or_create_target(db, type=target_type, value=target_value)
        return ScanResult(
            target=target,
            errors=[(f"Unsupported target type '{target_type}'. Supported types: {supported}.")],
        )

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

    for module in _MODULE_REGISTRY[target_type]:
        modules_run.append(module.name)
        logger.info("run_scan: executing module=%s for target_id=%s", module.name, target.id)

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
    )


async def run_scan_for_investigation(
    db: AsyncSession,
    *,
    investigation_id: str,
    target_type: str,
    target_value: str,
    options: dict | None = None,
    role: str | None = None,
) -> ScanResult:
    """
    Run a scan and automatically link the target to an investigation.

    This combines run_scan() with add_target_to_investigation():
    1. Run the scan (get-or-create target, execute modules, store results).
    2. Link the target to the investigation if not already linked.
       If the target is already linked, the existing link is silently kept —
       no error is raised, since running a second scan on the same target
       for the same investigation is a valid workflow (new findings accumulate).
    3. Return the ScanResult (same shape as run_scan).

    Raises ValueError if the investigation does not exist or is closed.
    The caller (router) is responsible for converting ValueError to HTTP 400/404.

    Args:
        db: async SQLAlchemy session.
        investigation_id: the investigation to link the target to.
        target_type: canonical type string.
        target_value: the value to investigate.
        options: module-specific options (see run_scan).
        role: optional role label for the link
              (e.g. "initial_target", "pivot", "discovered_domain").
    """
    # Validate investigation exists and is open before running the scan.
    inv = await inv_service.get_investigation(db, investigation_id)
    if inv is None:
        raise ValueError(f"Investigation '{investigation_id}' not found.")
    if inv.status == "closed":
        raise ValueError(
            f"Investigation '{investigation_id}' is closed. Re-open it before running scans."
        )

    # Run the scan.
    scan_result = await run_scan(
        db,
        target_type=target_type,
        target_value=target_value,
        options=options,
    )

    # Link target to investigation — ignore "already linked" silently.
    try:
        await inv_service.add_target_to_investigation(
            db,
            investigation_id=investigation_id,
            target_id=scan_result.target.id,
            role=role,
        )
        logger.info(
            "run_scan_for_investigation: linked target_id=%s to investigation_id=%s role=%r",
            scan_result.target.id,
            investigation_id,
            role,
        )
    except ValueError as e:
        if "already linked" in str(e):
            logger.info(
                "run_scan_for_investigation: target_id=%s already in investigation_id=%s — skipped",
                scan_result.target.id,
                investigation_id,
            )
        else:
            # Unexpected ValueError (closed race condition etc.) — surface it.
            raise

    return scan_result
