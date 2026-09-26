"""Tests for API-key gating and HMAC-signed identity assertions.

Includes a fixed cross-language test vector generated with Node's
``crypto.createHmac`` (see ``src/lib/identity.ts`` in the UI repo) so the
TypeScript and Python implementations are provably compatible:

    secret = "openrecon-test-secret"
    payload = "user_abc123:1790000000"
    sig = HMAC-SHA256(secret, payload) hex
"""

import asyncio
import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException, Request

from app.core.auth import (
    IDENTITY_TTL_SECONDS,
    get_current_user_id,
    require_api_key,
    verify_identity_assertion,
)

VECTOR = {
    "secret": "openrecon-test-secret",
    "user_id": "user_abc123",
    "exp": 1790000000,
    "sig": "d7a9d3f0fe88e716ea2df88e33763bd5722641b6b2c0f6125d7273448fc2ba82",
}


def make_request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": raw,
    }
    return Request(scope)


def sign(user_id: str, exp: int, secret: str) -> str:
    return hmac.new(secret.encode(), f"{user_id}:{exp}".encode(), hashlib.sha256).hexdigest()


def assertion_headers(
    user_id: str = "user_abc123",
    secret: str = "s3cret",
    now: int | None = None,
    exp: int | None = None,
    sig: str | None = None,
) -> dict[str, str]:
    now = int(time.time()) if now is None else now
    exp = now + IDENTITY_TTL_SECONDS if exp is None else exp
    sig = sign(user_id, exp, secret) if sig is None else sig
    return {
        "X-User-Id": user_id,
        "X-User-Exp": str(exp),
        "X-User-Sig": sig,
    }


# ─── Cross-language vector ───────────────────────────────────────────────────


def test_node_generated_signature_vector():
    """The committed vector must match Python's HMAC (Node/Python parity)."""
    computed = hmac.new(
        VECTOR["secret"].encode(),
        f"{VECTOR['user_id']}:{VECTOR['exp']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert computed == VECTOR["sig"]


def test_verify_accepts_node_generated_vector():
    now = VECTOR["exp"] - 100
    user_id = verify_identity_assertion(
        VECTOR["user_id"],
        str(VECTOR["exp"]),
        VECTOR["sig"],
        VECTOR["secret"],
        now=now,
    )
    assert user_id == VECTOR["user_id"]


# ─── verify_identity_assertion ───────────────────────────────────────────────


def test_valid_assertion_returns_user_id():
    now = int(time.time())
    headers = assertion_headers(now=now)
    assert (
        verify_identity_assertion(
            headers["X-User-Id"],
            headers["X-User-Exp"],
            headers["X-User-Sig"],
            "s3cret",
            now=now,
        )
        == "user_abc123"
    )


def test_tampered_user_id_rejected():
    now = int(time.time())
    headers = assertion_headers(user_id="user_abc123", now=now)
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion(
            "victim_456",
            headers["X-User-Exp"],
            headers["X-User-Sig"],
            "s3cret",
            now=now,
        )
    assert exc.value.status_code == 401


def test_wrong_signature_rejected():
    now = int(time.time())
    headers = assertion_headers(now=now, sig="0" * 64)
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion(
            headers["X-User-Id"],
            headers["X-User-Exp"],
            headers["X-User-Sig"],
            "s3cret",
            now=now,
        )
    assert exc.value.status_code == 401


def test_expired_assertion_rejected():
    now = int(time.time())
    exp = now - 31  # beyond the 30s skew
    headers = assertion_headers(exp=exp, sig=sign("user_abc123", exp, "s3cret"))
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion(
            headers["X-User-Id"],
            headers["X-User-Exp"],
            headers["X-User-Sig"],
            "s3cret",
            now=now,
        )
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_expiry_too_far_in_future_rejected():
    now = int(time.time())
    exp = now + IDENTITY_TTL_SECONDS + 31  # beyond TTL + skew
    headers = assertion_headers(exp=exp, sig=sign("user_abc123", exp, "s3cret"))
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion(
            headers["X-User-Id"],
            headers["X-User-Exp"],
            headers["X-User-Sig"],
            "s3cret",
            now=now,
        )
    assert exc.value.status_code == 401


def test_non_numeric_expiry_rejected():
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion("user_abc123", "not-a-number", "0" * 64, "s3cret", now=1790000000)
    assert exc.value.status_code == 401


def test_missing_secret_fails_closed_with_503():
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion("u", "1", "sig", secret="", now=1)
    assert exc.value.status_code == 503


def test_missing_headers_rejected_when_secret_set():
    with pytest.raises(HTTPException) as exc:
        verify_identity_assertion("", "", "", "s3cret", now=1)
    assert exc.value.status_code == 401


# ─── get_current_user_id (header assembly + degraded mode) ───────────────────


def test_no_headers_without_degraded_raises_401(monkeypatch):
    monkeypatch.delenv("AUTH_ALLOW_DEGRADED", raising=False)
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(make_request({}))
    assert exc.value.status_code == 401


def test_no_headers_with_degraded_returns_none(monkeypatch):
    monkeypatch.setenv("AUTH_ALLOW_DEGRADED", "true")
    assert get_current_user_id(make_request({})) is None


def test_partial_headers_rejected_even_in_degraded_mode(monkeypatch):
    monkeypatch.setenv("AUTH_ALLOW_DEGRADED", "true")
    monkeypatch.setenv("USER_SIGNING_SECRET", "s3cret")
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(make_request({"X-User-Id": "user_abc123"}))
    assert exc.value.status_code == 401


def test_valid_headers_accepted(monkeypatch):
    monkeypatch.setenv("USER_SIGNING_SECRET", "s3cret")
    monkeypatch.delenv("AUTH_ALLOW_DEGRADED", raising=False)
    headers = assertion_headers()
    assert get_current_user_id(make_request(headers)) == "user_abc123"


def test_valid_headers_missing_secret_503(monkeypatch):
    monkeypatch.delenv("USER_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("AUTH_ALLOW_DEGRADED", raising=False)
    headers = assertion_headers()
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(make_request(headers))
    assert exc.value.status_code == 503


# ─── require_api_key ─────────────────────────────────────────────────────────


def test_api_key_unset_fails_closed_503(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_api_key(make_request({"X-API-Key": "anything"})))
    assert exc.value.status_code == 503


def test_api_key_mismatch_401(monkeypatch):
    monkeypatch.setenv("API_KEY", "right-key")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_api_key(make_request({"X-API-Key": "wrong-key"})))
    assert exc.value.status_code == 401


def test_api_key_match_passes(monkeypatch):
    monkeypatch.setenv("API_KEY", "right-key")
    assert asyncio.run(require_api_key(make_request({"X-API-Key": "right-key"}))) is None
