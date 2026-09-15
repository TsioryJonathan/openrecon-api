import asyncio
import logging
from typing import ClassVar

from app.core.confidence import Confidence
from app.core.module import BaseModule, ModuleResult
from app.utils.sherlock_parser import parse_sherlock_file

logger = logging.getLogger(__name__)

# Default sherlock-rs execution parameters.
_SHERLOCK_TIMEOUT = 10  # per-site timeout in seconds
_SHERLOCK_CONCURRENCY = 20  # parallel requests


class SherlockModule(BaseModule):
    """
    OpenRecon module wrapping sherlock-rs.

    Accepts: username
    Produces: one Finding of type "social_account" per discovered profile,
              each backed by one Evidence of type "url".

    Confidence rationale:
    - sherlock-rs checks the URL and gets a 200 response → LIKELY.
      We cannot confirm the account belongs to the target without additional
      corroboration, so CONFIRMED is not used here by default.
    - The caller may upgrade confidence later if corroborating evidence is found
      (e.g. the profile bio matches other findings).

    This module does NOT write to the database. Storage is handled by the
    caller (service layer or future orchestrator). The module only produces
    normalized dicts that match the Finding and Evidence ORM shapes.
    """

    name: ClassVar[str] = "sherlock"
    description: ClassVar[str] = "Search for a username across 480+ platforms using sherlock-rs."
    supported_target_types: ClassVar[list[str]] = ["username"]

    async def execute(
        self,
        target_type: str,
        target_value: str,
        **kwargs,
    ) -> ModuleResult:
        """
        Run sherlock-rs against a username.

        Keyword args:
            sites (list[str]): restrict scan to these site names.
                               Defaults to all sites if not provided.

        Returns:
            ModuleResult with one Finding + one Evidence per discovered profile.
        """
        if target_type not in self.supported_target_types:
            return ModuleResult(
                errors=[
                    (
                        f"SherlockModule does not accept target type '{target_type}'. "
                        f"Supported: {self.supported_target_types}"
                    )
                ]
            )

        username = target_value.strip()
        sites: list[str] = kwargs.get("sites", [])

        cmd = [
            "sherlock-rs",
            username,
            "--timeout",
            str(_SHERLOCK_TIMEOUT),
            "--concurrency",
            str(_SHERLOCK_CONCURRENCY),
        ]
        for site in sites:
            cmd += ["--site", site]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
        except FileNotFoundError:
            return ModuleResult(
                errors=["sherlock-rs binary not found. Is it installed and in PATH?"]
            )
        except OSError as e:
            return ModuleResult(errors=[f"sherlock-rs execution failed: {e}"])

        if process.returncode != 0:
            error_msg = stderr.decode().strip() or "sherlock-rs exited with non-zero code"
            logger.error("sherlock-rs failed for username=%s: %s", username, error_msg)
            return ModuleResult(errors=[error_msg])

        raw_output = stdout.decode()
        parsed = parse_sherlock_file(raw_output)

        findings: list[dict] = []
        evidence: list[dict] = []

        for entry in parsed:
            site = entry["site"]
            url = entry["url"]

            # One finding per discovered profile.
            finding = {
                "type": "social_account",
                "value": url,
                "source": self.name,
                "confidence": Confidence.LIKELY,
                "confidence_reason": (
                    f"sherlock-rs received a positive HTTP response at {url}. "
                    f"Account existence confirmed on {site}, "
                    f"attribution to target username '{username}' is LIKELY."
                ),
                "metadata": {"site": site, "username": username},
                # target_id will be injected by the caller before DB insertion.
            }

            # One evidence per finding: the URL that was found.
            ev = {
                "source": self.name,
                "evidence_type": "url",
                "value": url,
                "metadata": {
                    "site": site,
                    "username": username,
                    "raw_line": f"[+] {site}: {url}",
                },
                # finding_id will be injected by the caller after findings are stored.
            }

            findings.append(finding)
            evidence.append(ev)

        return ModuleResult(
            findings=findings,
            evidence=evidence,
            raw={"stdout": raw_output, "site_count": len(parsed)},
            errors=[],
        )
