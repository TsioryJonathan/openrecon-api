"""Optional API-key authentication.

Reads the API_KEY environment variable:

- When API_KEY is set, every /api route requires it via the
  ``X-API-Key`` header (Bearer tokens in ``Authorization`` also work).
- When API_KEY is empty/unset, the API stays open. Useful for local
  development and for keeping the public deployment usable until the
  owner decides to lock it down.

Comparison uses a constant-time check to avoid timing attacks.
"""

import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def validate_api_key(api_key: str | None = Security(api_key_scheme)) -> None:
    expected = os.getenv("API_KEY", "")
    if not expected:
        return
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )