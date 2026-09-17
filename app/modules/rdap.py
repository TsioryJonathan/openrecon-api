"""
app/modules/rdap.py

OpenRecon RDAP module.

Accepts: domain
Produces:
  - Finding type "registrar"      — who registered the domain
  - Finding type "nameserver"     — authoritative nameservers
  - Finding type "domain_status"  — EPP status codes (e.g. clientTransferProhibited)
  - Finding type "expiry_date"    — when the domain registration expires

Data source: rdap.org bootstrap resolver (fully passive, read-only).
RDAP is the modern replacement for WHOIS (RFC 7483).

Confidence rationale:
  - registrar, nameserver, expiry_date: CONFIRMED — RDAP returns authoritative
    registration data from the registry.
  - domain_status: CONFIRMED — EPP status codes are authoritative.

If RDAP returns no data (domain not found, registry unsupported, timeout),
the module returns an empty result with the error captured — never raises.
"""

import logging
from typing import ClassVar

import httpx

from app.core.confidence import Confidence
from app.core.module import BaseModule, ModuleResult

logger = logging.getLogger(__name__)

_RDAP_TIMEOUT = 12  # seconds — rdap.org can be slow for some TLDs
_RDAP_BASE = "https://rdap.org/domain/"


class RDAPModule(BaseModule):
    """
    Passive RDAP registration lookup module.

    For a given domain:
    1. Queries rdap.org bootstrap resolver.
    2. Extracts registrar, nameservers, EPP status codes, expiry date.
    3. Produces one Finding + one Evidence per extracted datum.

    Does not make direct registry connections — uses rdap.org as a
    bootstrap proxy so no TLD-specific endpoint configuration is needed.
    Does not write to the database.
    """

    name = "rdap"
    description = "Passive RDAP registration lookup: registrar, nameservers, status, expiry."
    supported_target_types: ClassVar[list[str]] = ["domain"]

    async def execute(
        self,
        target_type: str,
        target_value: str,
        **kwargs,
    ) -> ModuleResult:
        if target_type not in self.supported_target_types:
            return ModuleResult(
                errors=[
                    (
                        f"RDAPModule does not accept target type '{target_type}'. "
                        f"Supported: {self.supported_target_types}"
                    )
                ]
            )

        domain = target_value.strip().lower()
        url = f"{_RDAP_BASE}{domain}"

        try:
            async with httpx.AsyncClient(timeout=_RDAP_TIMEOUT) as client:
                resp = await client.get(url, follow_redirects=True)
        except httpx.TimeoutException:
            return ModuleResult(errors=[f"RDAP lookup timed out for '{domain}'."])
        except httpx.HTTPError as e:
            return ModuleResult(errors=[f"RDAP HTTP error for '{domain}': {e}"])

        if resp.status_code == 404:
            return ModuleResult(errors=[f"RDAP: domain '{domain}' not found in registry."])
        if resp.status_code != 200:
            return ModuleResult(errors=[f"RDAP returned HTTP {resp.status_code} for '{domain}'."])

        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            return ModuleResult(errors=[f"RDAP: failed to parse JSON for '{domain}': {e}"])

        findings: list[dict] = []
        evidence: list[dict] = []
        raw = {"url": url, "status_code": resp.status_code}

        # --- Registrar ---
        registrar_name = self._extract_registrar(data)
        if registrar_name:
            raw["registrar"] = registrar_name
            f, e = self._make_finding(
                ftype="registrar",
                value=registrar_name,
                domain=domain,
                evidence_type="rdap_entity",
                confidence=Confidence.CONFIRMED,
                reason=(
                    f"RDAP registration data for '{domain}' names "
                    f"'{registrar_name}' as the registrar."
                ),
                meta={"domain": domain, "registrar": registrar_name},
            )
            findings.append(f)
            evidence.append(e)

        # --- Nameservers ---
        nameservers = self._extract_nameservers(data)
        raw["nameservers"] = nameservers
        for ns in nameservers:
            f, e = self._make_finding(
                ftype="nameserver",
                value=ns,
                domain=domain,
                evidence_type="rdap_nameserver",
                confidence=Confidence.CONFIRMED,
                reason=(
                    f"RDAP registration data for '{domain}' lists "
                    f"'{ns}' as an authoritative nameserver."
                ),
                meta={"domain": domain, "nameserver": ns},
            )
            findings.append(f)
            evidence.append(e)

        # --- EPP Status codes ---
        statuses = self._extract_statuses(data)
        raw["statuses"] = statuses
        for status in statuses:
            f, e = self._make_finding(
                ftype="domain_status",
                value=status,
                domain=domain,
                evidence_type="rdap_status",
                confidence=Confidence.CONFIRMED,
                reason=(
                    f"RDAP registration data for '{domain}' includes EPP status code '{status}'."
                ),
                meta={"domain": domain, "status": status},
            )
            findings.append(f)
            evidence.append(e)

        # --- Expiry date ---
        expiry = self._extract_expiry(data)
        if expiry:
            raw["expiry"] = expiry
            f, e = self._make_finding(
                ftype="expiry_date",
                value=expiry,
                domain=domain,
                evidence_type="rdap_event",
                confidence=Confidence.CONFIRMED,
                reason=(
                    f"RDAP registration data for '{domain}' records "
                    f"an expiration event at '{expiry}'."
                ),
                meta={"domain": domain, "expiry": expiry},
            )
            findings.append(f)
            evidence.append(e)

        return ModuleResult(
            findings=findings,
            evidence=evidence,
            raw=raw,
            errors=[],
        )

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_registrar(self, data: dict) -> str | None:
        """Extract registrar name from RDAP entities."""
        for entity in data.get("entities", []):
            roles = entity.get("roles", [])
            if "registrar" not in roles:
                continue
            # Try vcardArray first (structured contact data)
            vcard = entity.get("vcardArray", [])
            if len(vcard) > 1:
                for field in vcard[1]:
                    if isinstance(field, list) and len(field) >= 4 and field[0] == "fn":
                        name = field[3]
                        if isinstance(name, str) and name.strip():
                            return name.strip()
            # Fall back to publicIds or handle
            for pub_id in entity.get("publicIds", []):
                if pub_id.get("type") == "IANA Registrar ID":
                    return f"Registrar IANA#{pub_id.get('identifier', '')}"
        return None

    def _extract_nameservers(self, data: dict) -> list[str]:
        """Extract nameserver hostnames from RDAP nameservers array."""
        ns_list: list[str] = []
        for ns in data.get("nameservers", []):
            name = ns.get("ldhName") or ns.get("unicodeName", "")
            if name:
                ns_list.append(name.lower().rstrip("."))
        return sorted(set(ns_list))

    def _extract_statuses(self, data: dict) -> list[str]:
        """Extract EPP status codes."""
        return sorted(set(data.get("status", [])))

    def _extract_expiry(self, data: dict) -> str | None:
        """Extract expiration date from RDAP events."""
        for event in data.get("events", []):
            if event.get("eventAction") in ("expiration", "registrationExpiration"):
                date = event.get("eventDate", "")
                if date:
                    return date
        return None

    def _make_finding(
        self,
        *,
        ftype: str,
        value: str,
        domain: str,
        evidence_type: str,
        confidence: str,
        reason: str,
        meta: dict,
    ) -> tuple[dict, dict]:
        finding = {
            "type": ftype,
            "value": value,
            "source": self.name,
            "confidence": confidence,
            "confidence_reason": reason,
            "metadata": meta,
        }
        ev = {
            "source": self.name,
            "evidence_type": evidence_type,
            "value": value,
            "metadata": {"domain": domain, "rdap_url": f"{_RDAP_BASE}{domain}"},
        }
        return finding, ev
