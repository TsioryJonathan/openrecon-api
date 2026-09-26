"""API-key + HMAC-signed trusted-proxy user identity.

Two layers:

- ``require_api_key``: fail-closed gate for /api/investigations. Reads
  API_KEY from the environment. If unset → 503 (misconfiguration is
  never treated as "open"). If the ``X-API-Key`` header does not match
  → 401. Comparison is constant-time.

- ``get_current_user_id``: verifies the identity assertion injected by
  the trusted Next.js proxy. Three headers are required together:

  - ``X-User-Id``: the authenticated user id.
  - ``X-User-Exp``: unix expiry timestamp (seconds).
  - ``X-User-Sig``: hex HMAC-SHA256 over ``"{user_id}:{exp}"`` keyed
    with ``USER_SIGNING_SECRET``.

  The signature is compared in constant time and the expiry must fall
  within ``[-SKEW, TTL + SKEW]`` relative to now, so a captured header
  set cannot be replayed beyond its short lifetime and a caller holding
  only the API key cannot assert an arbitrary user id.

  Fail-closed behavior:
  - ``USER_SIGNING_SECRET`` unset → 503 (mirrors ``API_KEY``).
  - headers missing/invalid/expired → 401, except when
    ``AUTH_ALLOW_DEGRADED=true`` (local development only) AND all three
    identity headers are entirely absent → ``None``.
"""

import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request, status

# Lifetime of an assertion issued by the UI proxy.
IDENTITY_TTL_SECONDS = 300
# Allowed clock skew on top of TTL, in seconds.
IDENTITY_CLOCK_SKEW_SECONDS = 30


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


async def require_api_key(request: Request) -> None:
    expected = os.getenv("API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY not configured",
        )
    provided = request.headers.get("X-API-Key")
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def verify_identity_assertion(user_id: str, exp: str, signature: str, secret: str, now: int) -> str:
    """Verify one identity assertion. Returns the user id or raises 401/503."""
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="USER_SIGNING_SECRET not configured",
        )
    if not user_id or not exp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    try:
        exp_value = int(exp)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        ) from None

    expected = hmac.new(
        secret.encode(),
        f"{user_id}:{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    if exp_value < now - IDENTITY_CLOCK_SKEW_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identity assertion expired",
        )
    if exp_value > now + IDENTITY_TTL_SECONDS + IDENTITY_CLOCK_SKEW_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identity assertion expiry too far in the future",
        )
    return user_id


def get_current_user_id(request: Request) -> str | None:
    user_id = (request.headers.get("X-User-Id") or "").strip()
    exp = (request.headers.get("X-User-Exp") or "").strip()
    signature = (request.headers.get("X-User-Sig") or "").strip()

    if not user_id and not exp and not signature:
        # No assertion at all: allowed only in local dev (degraded mode).
        if _env_truthy("AUTH_ALLOW_DEGRADED"):
            return None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    secret = os.getenv("USER_SIGNING_SECRET", "")
    return verify_identity_assertion(user_id, exp, signature, secret, now=int(time.time()))
