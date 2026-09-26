from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class ModuleResult:
    """
    The normalized output of any OpenRecon module execution.

    A module never returns raw tool output. It always returns a ModuleResult
    containing structured Finding dicts and Evidence dicts ready to be stored.

    Attributes:
    - findings: list of Finding-shaped dicts (matching the Finding ORM model).
      Each dict must contain at minimum: type, value, source, confidence,
      confidence_reason. target_id is injected by the caller before storage.
    - evidence: list of Evidence-shaped dicts (matching the Evidence ORM model).
      Each dict must contain at minimum: source, evidence_type, value.
      finding_id is injected by the caller after findings are stored.
    - raw: the unmodified output from the underlying tool, for debugging.
      Stored in Finding.metadata or Evidence.metadata as appropriate.
    - errors: list of error strings that occurred during execution.
      A partial result (some findings, some errors) is valid — the module
      should not suppress partial results just because some checks failed.
    """

    findings: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if at least some findings were produced without a total failure."""
        return len(self.findings) > 0 or len(self.errors) == 0


class BaseModule(ABC):
    """
    Abstract base class for all OpenRecon modules.

    Every module must declare:
    - name: unique slug (e.g. "sherlock", "dns", "rdap")
    - description: one-line human-readable description
    - supported_target_types: list of target type strings this module accepts
      (e.g. ["username"], ["domain", "ip"], ["domain", "subdomain", "url"])

    Every module must implement:
    - execute(target_type, target_value, **kwargs) -> ModuleResult

    The core orchestrator depends only on this interface.
    It must never import from a specific module directly.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    supported_target_types: ClassVar[list[str]]

    def accepts(self, target_type: str) -> bool:
        """Return True if this module can handle the given target type."""
        return target_type in self.supported_target_types

    @abstractmethod
    async def execute(
        self,
        target_type: str,
        target_value: str,
        **kwargs,
    ) -> ModuleResult:
        """
        Run the module against a target.

        Args:
            target_type: canonical type string (e.g. "username", "domain")
            target_value: the actual value to investigate (e.g. "john123")
            **kwargs: module-specific options (e.g. sites list for Sherlock)

        Returns:
            ModuleResult with findings, evidence, raw output, and any errors.
            Never raises — errors are captured in ModuleResult.errors.
        """
        ...
