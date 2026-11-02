from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitRule:
    """Attempts allowed per window for one actor on one action."""

    max_attempts: int
    window_seconds: float


class RateLimiter:
    """Fixed-window attempt limiter, held in process memory.

    Deliberate limitation, not an oversight: state lives in this process, so it
    resets on restart and is not shared between workers. That is adequate for a
    single-user local application and is exactly why the production path is
    Redis-backed — see `shared_state` below. A login throttle that silently
    differs per worker would be a security control that does not exist.
    """

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, scope: str, actor: str, rule: RateLimitRule) -> tuple[bool, float]:
        """Return (allowed, seconds_until_a_slot_frees)."""
        now = time.monotonic()
        bucket = self._attempts[(scope, actor)]

        cutoff = now - rule.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= rule.max_attempts:
            retry_after = rule.window_seconds - (now - bucket[0])
            return False, max(retry_after, 1.0)

        bucket.append(now)
        return True, 0.0

    def remaining(self, scope: str, actor: str, rule: RateLimitRule) -> int:
        now = time.monotonic()
        bucket = self._attempts[(scope, actor)]
        cutoff = now - rule.window_seconds
        live = sum(1 for moment in bucket if moment > cutoff)
        return max(rule.max_attempts - live, 0)

    def reset(self, scope: str | None = None, actor: str | None = None) -> None:
        """Forget recorded attempts. Used by tests and after a successful login."""
        if scope is None and actor is None:
            self._attempts.clear()
            return
        keys = [
            key
            for key in self._attempts
            if (scope is None or key[0] == scope) and (actor is None or key[1] == actor)
        ]
        for key in keys:
            del self._attempts[key]


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Process-wide singleton so every request shares one set of counters."""
    return _limiter
