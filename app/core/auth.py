"""API-key + trusted-proxy user-header authentication.

Two layers:

- ``require_api_key``: fail-closed gate for /api/investigations. Reads
  API_KEY from the environment. If unset → 503 (misconfiguration is
  never treated as "open"). If the ``X-API-Key`` header does not match
  → 401. Comparison is constant-time.

- ``get_current_user_id``: reads the ``X-User-Id`` header injected by
  the trusted Next.js proxy (never exposed to the browser). Returns the
  user id, or ``None`` when the header is absent AND
  ``AUTH_ALLOW_DEGRADED=true`` (local development only). In production
  the header is required → 401 otherwise.

The header is trusted only because it originates server-to-server from
the UI proxy; the browser can never set it on the API directly (CORS +
network position).
"""

import os
import secrets

from fastapi import HTTPException, Request, status


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


def get_current_user_id(request: Request) -> str | None:
    user_id = (request.headers.get("X-User-Id") or "").strip()
    if user_id:
        return user_id
    if _env_truthy("AUTH_ALLOW_DEGRADED"):
        return None
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )
