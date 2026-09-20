"""
app/core/normalizer.py

Produces a canonical normalized form for Finding values.

Goals:
- Two findings that represent the same thing must produce the same
  normalized value so the deduplicator can detect them.
- Normalization is type-aware: a URL and a subdomain normalize differently.
- Never lose information — normalization is only for comparison and keying,
  the original value is always stored in Finding.value.

Normalized value is stored in Finding.normalized_value (added this batch).
It is never shown to the user directly; it is an internal dedup key.
"""

from urllib.parse import urlparse


def normalize_finding_value(finding_type: str, value: str) -> str:
    """
    Return a canonical string for (finding_type, value).

    Rules by type:
    - social_account / url / http_service:
        Parse as URL, lowercase scheme+host, strip trailing slash on path,
        drop fragment, keep query string (it can be meaningful for some platforms).
    - subdomain / domain / hostname:
        Lowercase, strip leading "*." wildcards, strip trailing dot.
    - ip_address:
        Strip whitespace, leave as-is (IPs are already canonical).
    - email:
        Lowercase the whole address.
    - dns_record:
        Lowercase, collapse internal whitespace to single space.
    - repository:
        Lowercase, strip trailing slash.
    - default (unknown types):
        Strip whitespace, lowercase.

    The original value is never modified — this function only produces a key.
    """
    v = value.strip()

    if finding_type in ("social_account", "url", "http_service"):
        return _normalize_url(v)

    if finding_type in ("subdomain", "domain", "hostname"):
        return _normalize_hostname(v)

    if finding_type == "ip_address":
        return v  # already canonical

    if finding_type == "email":
        return v.lower()

    if finding_type == "dns_record":
        return " ".join(v.lower().split())

    if finding_type == "repository":
        return _normalize_url(v) if v.startswith("http") else v.lower().rstrip("/")

    # Default
    return v.lower()


def _normalize_url(value: str) -> str:
    """
    Canonical form for a URL:
    - lowercase scheme and host
    - strip trailing slash from path (unless path is just "/")
    - drop fragment (#...)
    - keep query string
    """
    try:
        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or ""
        query = parsed.query
        result = f"{scheme}://{netloc}{path}"
        if query:
            result += f"?{query}"
        return result
    except ValueError:
        return value.lower()


def _normalize_hostname(value: str) -> str:
    """
    Canonical form for a hostname/domain/subdomain:
    - strip leading "*." (wildcard cert entries)
    - lowercase
    - strip trailing dot
    """
    v = value.lower().strip()
    v = v.removeprefix("*.")
    v = v.rstrip(".")
    return v
