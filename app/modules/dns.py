"""
app/modules/dns.py

OpenRecon DNS module.

Accepts: domain
Produces:
  - Finding type "dns_record"  — one per DNS record (A, AAAA, MX, NS, TXT, CNAME)
  - Finding type "subdomain"   — one per subdomain found via crt.sh certificate logs

Every finding is backed by one Evidence.

Data sources:
  - DNS records: dns.google JSON API (passive, no direct DNS queries)
  - Subdomains:  crt.sh certificate transparency log (passive)

Both sources are passive (no active probing of the target).
Confidence rationale:
  - dns_record: CONFIRMED — the record exists in DNS right now.
  - subdomain:  LIKELY    — the name appeared in a certificate; the subdomain
                            may no longer be live. Confirmed only if A/AAAA
                            record also resolves (not checked here).
"""

import asyncio
import logging
from typing import ClassVar

import httpx

from app.core.confidence import Confidence
from app.core.module import BaseModule, ModuleResult

logger = logging.getLogger(__name__)

_DNS_TIMEOUT = 8  # seconds per DNS query type
_CRT_TIMEOUT = 15  # crt.sh can be slow

# Record types to query.
_RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME")


class DNSModule(BaseModule):
    """
    Passive DNS reconnaissance module.

    For a given domain:
    1. Queries dns.google for A, AAAA, MX, NS, TXT, CNAME records.
    2. Queries crt.sh for subdomains from certificate transparency logs.

    Produces one Finding + one Evidence per record / subdomain.
    Does not make direct DNS queries — uses Google's DNS-over-HTTPS API.
    Does not write to the database.
    """

    name = "dns"
    description = "Passive DNS record lookup and subdomain enumeration via crt.sh."
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
                        f"DNSModule does not accept target type '{target_type}'. "
                        f"Supported: {self.supported_target_types}"
                    )
                ]
            )

        domain = target_value.strip().lower()
        findings: list[dict] = []
        evidence: list[dict] = []
        errors: list[str] = []
        raw: dict = {}

        # Run DNS queries and crt.sh in parallel.
        dns_task = asyncio.create_task(self._query_all_records(domain))
        crt_task = asyncio.create_task(self._query_crtsh(domain))

        dns_results, crt_results = await asyncio.gather(dns_task, crt_task, return_exceptions=True)

        # --- DNS records ---
        if isinstance(dns_results, dict):
            raw["dns"] = dns_results
            for rtype, records in dns_results.items():
                for record_data in records:
                    value = f"{domain} {rtype} {record_data}"
                    f, e = self._make_dns_record_finding(domain, rtype, record_data, value)
                    findings.append(f)
                    evidence.append(e)
        else:
            errors.append(f"DNS queries failed: {dns_results}")

        # --- Subdomains from crt.sh ---
        if isinstance(crt_results, list):
            raw["crt_sh"] = crt_results
            for subdomain in crt_results:
                f, e = self._make_subdomain_finding(domain, subdomain)
                findings.append(f)
                evidence.append(e)
        else:
            errors.append(f"crt.sh query failed: {crt_results}")

        return ModuleResult(
            findings=findings,
            evidence=evidence,
            raw=raw,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _query_all_records(self, domain: str) -> dict[str, list[str]]:
        """Query all configured record types in parallel via dns.google."""
        tasks = {
            rtype: asyncio.create_task(self._query_record(domain, rtype)) for rtype in _RECORD_TYPES
        }
        results: dict[str, list[str]] = {}
        for rtype, task in tasks.items():
            try:
                records = await task
                if records:
                    results[rtype] = records
            except Exception as e:  # noqa: BLE001
                logger.warning("DNS query failed for %s %s: %s", domain, rtype, e)
        return results

    async def _query_record(self, domain: str, rtype: str) -> list[str]:
        """Query a single DNS record type via dns.google DoH API."""
        url = f"https://dns.google/resolve?name={domain}&type={rtype}"
        async with httpx.AsyncClient(timeout=_DNS_TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            data = resp.json()
            return [
                str(answer.get("data", "")).strip()
                for answer in data.get("Answer", [])
                if answer.get("data")
            ]

    async def _query_crtsh(self, domain: str) -> list[str]:
        """Fetch subdomains from crt.sh certificate transparency logs."""
        url = f"https://crt.sh/?q=%25.{domain}&output=json"
        try:
            async with httpx.AsyncClient(timeout=_CRT_TIMEOUT) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                entries = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("crt.sh request failed for %s: %s", domain, e)
            return []

        seen: set[str] = set()
        subdomains: list[str] = []

        for entry in entries:
            raw_names = str(entry.get("name_value", ""))
            for name in raw_names.splitlines():
                name = name.strip().lstrip("*.").lower()
                # Skip the apex domain itself and wildcards only.
                if not name or name == domain:
                    continue
                # Must be a subdomain of the queried domain.
                if not name.endswith(f".{domain}") and name != domain:
                    continue
                if name not in seen:
                    seen.add(name)
                    subdomains.append(name)

        # Cap at 200 to avoid overwhelming the pipeline.
        return sorted(subdomains)[:200]

    def _make_dns_record_finding(
        self,
        domain: str,
        rtype: str,
        record_data: str,
        value: str,
    ) -> tuple[dict, dict]:
        finding = {
            "type": "dns_record",
            "value": value,
            "source": self.name,
            "confidence": Confidence.CONFIRMED,
            "confidence_reason": (
                f"DNS {rtype} record for {domain} returned '{record_data}' via dns.google DoH API."
            ),
            "metadata": {
                "domain": domain,
                "record_type": rtype,
                "record_data": record_data,
            },
        }
        ev = {
            "source": self.name,
            "evidence_type": "dns_record",
            "value": value,
            "metadata": {
                "domain": domain,
                "record_type": rtype,
                "api": "dns.google",
            },
        }
        return finding, ev

    def _make_subdomain_finding(
        self,
        domain: str,
        subdomain: str,
    ) -> tuple[dict, dict]:
        finding = {
            "type": "subdomain",
            "value": subdomain,
            "source": self.name,
            "confidence": Confidence.LIKELY,
            "confidence_reason": (
                f"Subdomain '{subdomain}' appeared in a TLS certificate "
                f"for '{domain}' in crt.sh logs. May no longer be live."
            ),
            "metadata": {
                "domain": domain,
                "subdomain": subdomain,
            },
        }
        ev = {
            "source": self.name,
            "evidence_type": "certificate_entry",
            "value": subdomain,
            "metadata": {
                "domain": domain,
                "source_url": f"https://crt.sh/?q=%25.{domain}",
            },
        }
        return finding, ev
