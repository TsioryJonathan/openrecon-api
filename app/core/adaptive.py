"""
app/core/adaptive.py

Pure lead-extraction logic for adaptive recon.

Given a list of Finding dicts (already stored), extracts new (target_type,
target_value) pairs that could be scanned next.

Rules:
- Pure function: no DB access, no I/O, no side effects.
- Never invent targets not derivable from actual finding values.
- Each extraction rule declares the finding types it reads and the target
  type it produces — this makes the dependency graph explicit.
- Returns a list of Lead objects; the caller decides which ones to actually
  scan (after applying scope, dedup, depth limits).

Extraction rules:
1. social_account → username
   https://github.com/john123 → username:john123
   (extracts the path segment after the first slash)

2. subdomain → domain
   api.example.com → domain:api.example.com
   (the subdomain itself is a scannable domain)

3. dns_record A/AAAA → ip
   "example.com A 1.2.3.4" → ip:1.2.3.4
   (the resolved IP is a scannable target)

4. nameserver → domain
   ns1.example.com → domain:ns1.example.com
   (nameservers are domains that can be scanned)

5. registrar → (none — registrar names are not scannable targets)

Intentionally NOT producing leads from:
- expiry_date, domain_status — not scannable
- registrar — company names, not hostnames
"""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class Lead:
    """
    A potential new scan target derived from an existing finding.

    Attributes:
    - target_type: canonical type string (e.g. "domain", "ip", "username")
    - target_value: the value to scan
    - source_finding_id: which finding produced this lead
    - source_finding_type: the type of that finding (for traceability)
    - rule: which extraction rule produced this lead
    """

    target_type: str
    target_value: str
    source_finding_id: str
    source_finding_type: str
    rule: str


def extract_leads(findings: list[dict]) -> list[Lead]:
    """
    Extract potential new scan targets from a list of Finding dicts.

    Each dict must have at minimum: id, type, value, normalized_value.

    Returns a deduplicated list of Lead objects.
    The caller is responsible for:
    - Filtering against already-scanned targets (session dedup)
    - Checking scope
    - Enforcing depth limits
    - Running the actual scans
    """
    leads: list[Lead] = []

    for f in findings:
        ftype = f.get("type", "")
        fval = f.get("value", "")
        fid = f.get("id", "")

        if ftype == "social_account":
            lead = _extract_username_from_social(f)
            if lead:
                leads.append(lead)

        elif ftype == "subdomain":
            # The subdomain itself is a scannable domain.
            subdomain = f.get("normalized_value", fval).strip().lstrip("*.")
            if subdomain and "." in subdomain:
                leads.append(
                    Lead(
                        target_type="domain",
                        target_value=subdomain,
                        source_finding_id=fid,
                        source_finding_type=ftype,
                        rule="subdomain→domain",
                    )
                )

        elif ftype == "dns_record":
            lead = _extract_ip_from_dns_record(f)
            if lead:
                leads.append(lead)

        elif ftype == "nameserver":
            ns = fval.strip().lower().rstrip(".")
            if ns and "." in ns:
                leads.append(
                    Lead(
                        target_type="domain",
                        target_value=ns,
                        source_finding_id=fid,
                        source_finding_type=ftype,
                        rule="nameserver→domain",
                    )
                )

    return _deduplicate_leads(leads)


def _extract_username_from_social(finding: dict) -> Lead | None:
    """
    Extract a username from a social_account finding URL.

    https://github.com/john123       → john123
    https://reddit.com/user/john123  → john123 (last non-empty path segment)
    https://twitter.com/john123      → john123

    Returns None if the username cannot be extracted reliably.
    """
    url = finding.get("value", "")
    fid = finding.get("id", "")
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if not path_parts:
            return None
        # Skip common path prefixes that are not usernames.
        skip_prefixes = {"user", "u", "users", "profile", "p", "people", "in", "pub"}
        # Take the last meaningful segment.
        username = path_parts[-1]
        if username.lower() in skip_prefixes:
            return None
        # Sanity: usernames should be reasonable length and no path separators.
        if len(username) < 1 or len(username) > 64:
            return None
        return Lead(
            target_type="username",
            target_value=username,
            source_finding_id=fid,
            source_finding_type="social_account",
            rule="social_account→username",
        )
    except Exception:  # noqa: BLE001
        return None


def _extract_ip_from_dns_record(finding: dict) -> Lead | None:
    """
    Extract an IP address from a dns_record finding of type A or AAAA.

    Format: "example.com A 1.2.3.4" → ip:1.2.3.4
    """
    import re

    _IP_RE = re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
    )
    value = finding.get("value", "")
    fid = finding.get("id", "")
    parts = value.split()
    if len(parts) < 3:
        return None
    rtype = parts[1].upper()
    if rtype not in ("A", "AAAA"):
        return None
    ip = parts[2].strip()
    # Basic IPv4 validation for A records.
    if rtype == "A" and not _IP_RE.match(ip):
        return None
    return Lead(
        target_type="ip",
        target_value=ip,
        source_finding_id=fid,
        source_finding_type="dns_record",
        rule="dns_record→ip",
    )


def _deduplicate_leads(leads: list[Lead]) -> list[Lead]:
    """
    Remove duplicate leads by (target_type, target_value).
    Keeps the first occurrence.
    """
    seen: set[tuple] = set()
    result: list[Lead] = []
    for lead in leads:
        key = (lead.target_type, lead.target_value)
        if key not in seen:
            seen.add(key)
            result.append(lead)
    return result
