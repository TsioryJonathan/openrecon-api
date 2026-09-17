"""
app/core/scope.py

Scope definition and enforcement for OpenRecon scans.

A Scope defines what is allowed to be scanned:
- allowed_target_types: which target types are permitted (e.g. ["domain", "username"])
- allowed_domains: explicit allowlist of domains (and their subdomains if include_subdomains=True)
- allowed_ip_ranges: CIDR ranges for IP targets
- max_depth: how many recursive hops are allowed (reserved for adaptive recon)
- passive_only: if True, only passive modules may run (future enforcement)

Rules:
- An empty allowlist means "no restriction" for that dimension.
  E.g. allowed_domains=[] means all domains are permitted.
- A non-empty allowlist is an explicit permit list — anything not in it is blocked.
- Scope violations are not exceptions — they are ScopeViolation objects
  returned to the caller so the scan pipeline can record them.
- Scope checking is pure (no DB, no I/O).

Usage:
    scope = Scope(allowed_domains=["example.com", "acme.org"])
    result = scope.check("domain", "evil.com")
    if not result.allowed:
        # handle scope violation
"""

import ipaddress
from dataclasses import dataclass, field


@dataclass
class ScopeViolation:
    """
    Result of a scope check that failed.

    Attributes:
    - target_type: the type that was checked.
    - target_value: the value that was checked.
    - reason: human-readable explanation of why it was blocked.
    """

    target_type: str
    target_value: str
    reason: str
    allowed: bool = False


@dataclass
class ScopeOK:
    """Result of a scope check that passed."""

    target_type: str
    target_value: str
    allowed: bool = True
    reason: str = "Target is within scope."


# Type alias for scope check results.
ScopeResult = ScopeViolation | ScopeOK


@dataclass
class Scope:
    """
    Defines what OpenRecon is allowed to scan.

    All allowlists default to empty (= no restriction).
    Set them explicitly to enforce boundaries.

    Attributes:
    - allowed_target_types: permitted target type strings.
      Empty = all types allowed.
    - allowed_domains: permitted domain values (exact match or parent match).
      Empty = all domains allowed.
      A domain "example.com" also permits subdomains if include_subdomains=True.
    - allowed_ip_ranges: permitted CIDR ranges as strings (e.g. "192.168.0.0/16").
      Empty = all IPs allowed.
    - max_depth: maximum recursive scan depth (0 = no recursion). Default: 3.
    - passive_only: if True, active modules are blocked. Default: False.
      (Active module enforcement is reserved for when active modules are added.)
    - include_subdomains: if True, subdomains of allowed_domains are permitted.
      Default: True.
    """

    allowed_target_types: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    allowed_ip_ranges: list[str] = field(default_factory=list)
    max_depth: int = 3
    passive_only: bool = False
    include_subdomains: bool = True

    def check(self, target_type: str, target_value: str) -> ScopeResult:
        """
        Check whether (target_type, target_value) is within this scope.

        Returns ScopeOK if allowed, ScopeViolation with reason if not.
        Checks are applied in order: type → domain → IP range.
        """
        # 1. Target type check
        if self.allowed_target_types and target_type not in self.allowed_target_types:
            return ScopeViolation(
                target_type=target_type,
                target_value=target_value,
                reason=(
                    f"Target type '{target_type}' is not in the allowed types: "
                    f"{self.allowed_target_types}."
                ),
            )

        # 2. Domain check (applies to domain, subdomain, url, http_service)
        if (
            self.allowed_domains
            and target_type in ("domain", "subdomain", "url", "hostname")
            and not self._domain_allowed(target_value)
        ):
            return ScopeViolation(
                target_type=target_type,
                target_value=target_value,
                reason=(
                    f"Domain '{target_value}' is not in the allowed domains: "
                    f"{self.allowed_domains}."
                ),
            )

        # 3. IP range check
        if self.allowed_ip_ranges and target_type == "ip" and not self._ip_allowed(target_value):
            return ScopeViolation(
                target_type=target_type,
                target_value=target_value,
                reason=(
                    f"IP address '{target_value}' is not within any allowed "
                    f"range: {self.allowed_ip_ranges}."
                ),
            )

        return ScopeOK(target_type=target_type, target_value=target_value)

    def _domain_allowed(self, value: str) -> bool:
        """
        Return True if value matches any allowed domain.

        Exact match: "example.com" == "example.com" → True
        Subdomain match (include_subdomains=True):
            "api.example.com".endswith(".example.com") → True
        """
        v = value.lower().strip().rstrip(".")
        for allowed in self.allowed_domains:
            a = allowed.lower().strip().rstrip(".")
            if v == a:
                return True
            if self.include_subdomains and v.endswith(f".{a}"):
                return True
        return False

    def _ip_allowed(self, value: str) -> bool:
        """Return True if value falls within any allowed CIDR range."""
        try:
            ip = ipaddress.ip_address(value.strip())
        except ValueError:
            return False
        for cidr in self.allowed_ip_ranges:
            try:
                network = ipaddress.ip_network(cidr.strip(), strict=False)
                if ip in network:
                    return True
            except ValueError:
                continue
        return False


# ---------------------------------------------------------------------------
# Default scope — no restrictions.
# Used when the caller passes no scope.
# ---------------------------------------------------------------------------
UNRESTRICTED = Scope()
