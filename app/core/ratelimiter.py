"""
app/core/ratelimiter.py

Simple in-memory rate limiter for OpenRecon scan requests.

Purpose: prevent accidentally hammering the same target in rapid succession,
e.g. if a client fires 50 concurrent scan requests for "example.com".

Design:
- Keyed by (target_type, target_value, module_name).
- Tracks the last execution timestamp per key.
- If the same key is attempted within `min_interval_seconds`, the request
  is rejected with a RateLimitResult.
- State is in-process memory — resets on server restart.
  For production use, replace with Redis-backed storage.
- Thread-safe for asyncio (single-threaded event loop).

This is not a quota system (no max requests per day).
It is a minimum-interval guard per (target, module) pair.
"""

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default minimum seconds between scans of the same (target, module).
DEFAULT_MIN_INTERVAL = 60  # 1 minute


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    key: str
    reason: str = ""
    retry_after_seconds: float = 0.0


class RateLimiter:
    """
    In-memory per-key rate limiter.

    Keys are strings of the form "target_type:target_value:module_name".
    State is a dict mapping key → last_allowed_timestamp (float, epoch seconds).
    """

    def __init__(self, min_interval_seconds: float = DEFAULT_MIN_INTERVAL):
        self._min_interval = min_interval_seconds
        self._last_seen: dict[str, float] = {}

    def _make_key(self, target_type: str, target_value: str, module_name: str) -> str:
        return f"{target_type}:{target_value}:{module_name}"

    def check(
        self,
        target_type: str,
        target_value: str,
        module_name: str,
    ) -> RateLimitResult:
        """
        Check if a scan is allowed for this (target, module) combination.

        Returns RateLimitResult with allowed=True if the scan may proceed,
        or allowed=False with retry_after_seconds if it is too soon.
        Does NOT record the attempt — call record() after a successful check.
        """
        key = self._make_key(target_type, target_value, module_name)
        now = time.monotonic()
        last = self._last_seen.get(key)

        if last is None:
            return RateLimitResult(allowed=True, key=key)

        elapsed = now - last
        if elapsed >= self._min_interval:
            return RateLimitResult(allowed=True, key=key)

        retry_after = self._min_interval - elapsed
        return RateLimitResult(
            allowed=False,
            key=key,
            reason=(
                f"Module '{module_name}' was run against '{target_type}:{target_value}' "
                f"{elapsed:.0f}s ago. Minimum interval is {self._min_interval:.0f}s. "
                f"Retry in {retry_after:.0f}s."
            ),
            retry_after_seconds=retry_after,
        )

    def record(
        self,
        target_type: str,
        target_value: str,
        module_name: str,
    ) -> None:
        """Record that a scan was executed now for this key."""
        key = self._make_key(target_type, target_value, module_name)
        self._last_seen[key] = time.monotonic()
        logger.debug("RateLimiter: recorded key=%s", key)

    def check_and_record(
        self,
        target_type: str,
        target_value: str,
        module_name: str,
    ) -> RateLimitResult:
        """
        Atomically check and record in one call.

        If allowed, records the attempt immediately and returns allowed=True.
        If not allowed, does NOT record and returns allowed=False.
        """
        result = self.check(target_type, target_value, module_name)
        if result.allowed:
            self.record(target_type, target_value, module_name)
        return result

    def reset(self, target_type: str, target_value: str, module_name: str) -> None:
        """Remove the rate limit record for a key (for testing / manual override)."""
        key = self._make_key(target_type, target_value, module_name)
        self._last_seen.pop(key, None)

    def reset_all(self) -> None:
        """Clear all rate limit state (for testing)."""
        self._last_seen.clear()


# ---------------------------------------------------------------------------
# Singleton rate limiter instance.
# Import and use this in scan.py rather than creating a new instance per request.
# ---------------------------------------------------------------------------
_default_limiter = RateLimiter(min_interval_seconds=DEFAULT_MIN_INTERVAL)


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide rate limiter instance."""
    return _default_limiter
