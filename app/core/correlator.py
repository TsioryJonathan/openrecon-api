"""
app/core/correlator.py

Deterministic correlation rules.

Each rule takes a list of Finding dicts (already normalized) and returns
a list of Relation dicts — one per detected relationship.

Rules:
- Are pure functions: no DB access, no side effects.
- Only create relations that can be explained from the Finding data.
- Never invent relations — every relation must reference real Finding IDs.
- Return empty list if no relation can be derived.

A Relation dict has:
    source_finding_id: str
    target_finding_id: str
    relation_type: str  (from RelationType constants)
    confidence: str     (CONFIRMED / LIKELY / POSSIBLE)
    reason: str
    metadata: dict | None

Rules implemented:
1. dns_record_resolves_to_ip
   A dns_record finding of type A or AAAA links the domain to an ip_address
   finding if one exists for that IP. Confidence: CONFIRMED (DNS is ground truth).

2. subdomain_of_domain
   A subdomain finding is a child of its parent domain finding.
   Confidence: CONFIRMED (structural, derivable from the name itself).

3. social_account_found_on
   A social_account finding links a username target to its platform.
   Confidence: LIKELY (Sherlock confirmed the URL, attribution is strong).

4. shares_ip
   Two dns_record findings (A/AAAA) that resolve to the same IP address
   are linked via SHARES_IP.
   Confidence: POSSIBLE (shared IP ≠ same operator; CDN, shared hosting).
"""

import re

from app.core.confidence import Confidence
from app.models.Relation import RelationType


def run_all_rules(findings: list[dict]) -> list[dict]:
    """
    Run all correlation rules against a flat list of Finding dicts.

    Each dict must have at minimum:
        id, type, value, normalized_value, source, target_id

    Returns a list of Relation dicts (not yet persisted).
    Deduplicates by (source_finding_id, target_finding_id, relation_type).
    """
    relations: list[dict] = []

    relations.extend(_rule_dns_resolves_to_ip(findings))
    relations.extend(_rule_subdomain_of_domain(findings))
    relations.extend(_rule_social_account_found_on(findings))
    relations.extend(_rule_shares_ip(findings))

    return _deduplicate(relations)


# ---------------------------------------------------------------------------
# Rule 1 — DNS record RESOLVES_TO ip_address
# ---------------------------------------------------------------------------

_IP_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$")


def _rule_dns_resolves_to_ip(findings: list[dict]) -> list[dict]:
    """
    For each dns_record finding of type A or AAAA, if the resolved IP
    exists as a separate ip_address finding, create a RESOLVES_TO relation.

    Pattern: "example.com A 1.2.3.4" → RESOLVES_TO → "1.2.3.4"
    """
    relations = []

    # Index ip_address findings by their normalized value.
    ip_findings: dict[str, dict] = {
        f["normalized_value"]: f for f in findings if f["type"] == "ip_address"
    }

    for f in findings:
        if f["type"] != "dns_record":
            continue

        # Extract record type and data from value: "example.com A 1.2.3.4"
        parts = f["value"].split()
        if len(parts) < 3:
            continue
        rtype = parts[1].upper()
        if rtype not in ("A", "AAAA"):
            continue
        ip = parts[2].strip()

        if ip in ip_findings:
            target_f = ip_findings[ip]
            relations.append(
                {
                    "source_finding_id": f["id"],
                    "target_finding_id": target_f["id"],
                    "relation_type": RelationType.RESOLVES_TO,
                    "confidence": Confidence.CONFIRMED,
                    "reason": (
                        f"DNS {rtype} record for '{parts[0]}' resolves to '{ip}', "
                        f"which matches ip_address finding '{target_f['value']}'."
                    ),
                    "metadata": {"record_type": rtype, "ip": ip},
                }
            )

    return relations


# ---------------------------------------------------------------------------
# Rule 2 — subdomain SUBDOMAIN_OF domain
# ---------------------------------------------------------------------------


def _rule_subdomain_of_domain(findings: list[dict]) -> list[dict]:
    """
    For each subdomain finding, if its parent domain exists as a finding,
    create a SUBDOMAIN_OF relation.

    Pattern: "api.example.com" → SUBDOMAIN_OF → "example.com"
    """
    relations = []

    domain_findings: dict[str, dict] = {
        f["normalized_value"]: f for f in findings if f["type"] in ("domain", "dns_record")
    }

    # Also index dns_record findings by their domain part.
    # A dns_record value like "example.com A 1.2.3.4" → domain "example.com"
    dns_domain_findings: dict[str, dict] = {}
    for f in findings:
        if f["type"] == "dns_record":
            parts = f["value"].split()
            if parts:
                dns_domain_findings[parts[0].lower()] = f

    for f in findings:
        if f["type"] != "subdomain":
            continue

        sub = f["normalized_value"]
        parts = sub.split(".")
        if len(parts) < 3:
            continue

        # Try progressively shorter suffixes as candidate parent domains.
        for i in range(1, len(parts) - 1):
            parent = ".".join(parts[i:])
            if parent in domain_findings:
                relations.append(
                    {
                        "source_finding_id": f["id"],
                        "target_finding_id": domain_findings[parent]["id"],
                        "relation_type": RelationType.SUBDOMAIN_OF,
                        "confidence": Confidence.CONFIRMED,
                        "reason": (
                            f"'{sub}' is structurally a subdomain of '{parent}', "
                            f"which exists as a finding."
                        ),
                        "metadata": {"subdomain": sub, "parent_domain": parent},
                    }
                )
                break  # Use the most specific (longest) match only.
            if parent in dns_domain_findings:
                relations.append(
                    {
                        "source_finding_id": f["id"],
                        "target_finding_id": dns_domain_findings[parent]["id"],
                        "relation_type": RelationType.SUBDOMAIN_OF,
                        "confidence": Confidence.CONFIRMED,
                        "reason": (
                            f"'{sub}' is structurally a subdomain of '{parent}', "
                            f"which appears in DNS records."
                        ),
                        "metadata": {"subdomain": sub, "parent_domain": parent},
                    }
                )
                break

    return relations


# ---------------------------------------------------------------------------
# Rule 3 — social_account FOUND_ON platform
# ---------------------------------------------------------------------------

# Map domain → platform name for common social platforms.
_PLATFORM_DOMAINS: dict[str, str] = {
    "github.com": "GitHub",
    "reddit.com": "Reddit",
    "twitter.com": "Twitter",
    "x.com": "Twitter/X",
    "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "twitch.tv": "Twitch",
    "mastodon.social": "Mastodon",
    "gitlab.com": "GitLab",
    "bitbucket.org": "Bitbucket",
    "stackoverflow.com": "Stack Overflow",
    "medium.com": "Medium",
    "dev.to": "DEV",
    "keybase.io": "Keybase",
    "patreon.com": "Patreon",
    "soundcloud.com": "SoundCloud",
    "spotify.com": "Spotify",
    "last.fm": "Last.fm",
    "flickr.com": "Flickr",
    "vimeo.com": "Vimeo",
    "pinterest.com": "Pinterest",
    "tumblr.com": "Tumblr",
    "paypal.com": "PayPal",
    "cash.app": "Cash App",
    "venmo.com": "Venmo",
    "t.me": "Telegram",
}


def _rule_social_account_found_on(findings: list[dict]) -> list[dict]:
    """
    For each social_account finding, extract the host and link it to
    a domain or dns_record finding for the same platform if one exists.

    This rule does NOT create fictitious domain findings — it only links
    to findings that genuinely exist in the current target's finding set.
    Confidence: LIKELY (platform confirmed, but link to target is inferred).
    """
    from urllib.parse import urlparse

    relations = []

    # Index domain-type findings by normalized host.
    domain_index: dict[str, dict] = {}
    for f in findings:
        if f["type"] in ("domain", "subdomain", "http_service"):
            domain_index[f["normalized_value"]] = f
        elif f["type"] == "dns_record":
            parts = f["value"].split()
            if parts:
                domain_index[parts[0].lower()] = f

    for f in findings:
        if f["type"] != "social_account":
            continue

        try:
            host = urlparse(f["value"]).netloc.lower().removeprefix("www.")
        except Exception:  # noqa: BLE001, S112
            continue

        if host in domain_index:
            target_f = domain_index[host]
            platform = _PLATFORM_DOMAINS.get(host, host)
            relations.append(
                {
                    "source_finding_id": f["id"],
                    "target_finding_id": target_f["id"],
                    "relation_type": RelationType.FOUND_ON,
                    "confidence": Confidence.LIKELY,
                    "reason": (
                        f"Social account at '{f['value']}' is hosted on '{host}' "
                        f"({platform}), which matches finding '{target_f['value']}'."
                    ),
                    "metadata": {"platform": platform, "host": host},
                }
            )

    return relations


# ---------------------------------------------------------------------------
# Rule 4 — SHARES_IP between dns_record findings
# ---------------------------------------------------------------------------


def _rule_shares_ip(findings: list[dict]) -> list[dict]:
    """
    If two different dns_record A/AAAA findings resolve to the same IP,
    create a SHARES_IP relation between them.

    Confidence: POSSIBLE — shared IP could be CDN, shared hosting, etc.
    Only links findings within the same finding set (same target).
    """
    relations = []

    # Group A/AAAA dns_record findings by resolved IP.
    # Deduplicate by finding id first to avoid duplicate dicts in input
    # producing spurious bidirectional pairs.
    ip_to_findings: dict[str, list[dict]] = {}
    for f in findings:
        if f["type"] != "dns_record":
            continue
        parts = f["value"].split()
        if len(parts) < 3:
            continue
        if parts[1].upper() not in ("A", "AAAA"):
            continue
        ip = parts[2].strip()
        bucket = ip_to_findings.setdefault(ip, [])
        # Only add if this finding id is not already in the bucket.
        if not any(existing["id"] == f["id"] for existing in bucket):
            bucket.append(f)

    for ip, group in ip_to_findings.items():
        if len(group) < 2:
            continue
        # Create a relation between each distinct ordered pair (i < j only).
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["id"] == b["id"]:
                    continue
                relations.append(
                    {
                        "source_finding_id": a["id"],
                        "target_finding_id": b["id"],
                        "relation_type": RelationType.SHARES_IP,
                        "confidence": Confidence.POSSIBLE,
                        "reason": (
                            f"Both '{a['value']}' and '{b['value']}' resolve to "
                            f"the same IP address '{ip}'. "
                            f"May indicate shared hosting or CDN."
                        ),
                        "metadata": {"shared_ip": ip},
                    }
                )

    return relations


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _deduplicate(relations: list[dict]) -> list[dict]:
    """
    Remove duplicate relations by (source_finding_id, target_finding_id, relation_type).
    Keeps the first occurrence (highest-confidence rules run first).
    """
    seen: set[tuple] = set()
    result: list[dict] = []
    for r in relations:
        key = (r["source_finding_id"], r["target_finding_id"], r["relation_type"])
        if key not in seen:
            seen.add(key)
            result.append(r)
    return result
