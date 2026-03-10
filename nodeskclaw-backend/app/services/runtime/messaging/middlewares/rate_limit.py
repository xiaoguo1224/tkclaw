"""RateLimitMiddleware — per-sender rate limiting with priority-based receiver-side support.

Sender-side check runs in the middleware pipeline (before routing).
Receiver-side check is exposed as a helper for TransportMiddleware to call
per-target after the DeliveryPlan is generated.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from app.services.runtime.messaging.envelope import Priority
from app.services.runtime.messaging.pipeline import MessageMiddleware, NextFn, PipelineContext

logger = logging.getLogger(__name__)

DEFAULT_SENDER_RATE = 60
DEFAULT_WINDOW_S = 60

RECEIVER_RATES: dict[Priority, int] = {
    Priority.CRITICAL: 20,
    Priority.NORMAL: 60,
    Priority.BACKGROUND: 120,
}


_receiver_counters: dict[str, list[float]] = defaultdict(list)


def check_receiver_rate(
    target_node_id: str,
    *,
    priority: Priority = Priority.NORMAL,
    window_s: int = DEFAULT_WINDOW_S,
) -> tuple[bool, str]:
    """Check receiver rate limit with priority-based limits.

    Returns (allowed, action) where action is one of:
    - "ok" — within limit
    - "alert" — critical exceeded → allow but alert
    - "defer" — normal exceeded → should be deferred
    - "drop" — background exceeded → should be dropped
    """
    rate = RECEIVER_RATES.get(priority, 60)
    now = time.monotonic()
    timestamps = _receiver_counters[target_node_id]
    cutoff = now - window_s
    timestamps[:] = [t for t in timestamps if t > cutoff]

    if len(timestamps) < rate:
        timestamps.append(now)
        return True, "ok"

    if priority == Priority.CRITICAL:
        timestamps.append(now)
        return True, "alert"
    if priority == Priority.BACKGROUND:
        return False, "drop"
    return False, "defer"


class RateLimitMiddleware(MessageMiddleware):
    def __init__(self, rate: int = DEFAULT_SENDER_RATE, window_s: int = DEFAULT_WINDOW_S) -> None:
        self._rate = rate
        self._window_s = window_s
        self._counters: dict[str, list[float]] = defaultdict(list)

    async def process(self, ctx: PipelineContext, next_fn: NextFn) -> None:
        sender_id = ""
        if ctx.envelope.data:
            sender_id = ctx.envelope.data.sender.id

        if sender_id:
            now = time.monotonic()
            timestamps = self._counters[sender_id]
            cutoff = now - self._window_s
            timestamps[:] = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= self._rate:
                logger.warning("RateLimit exceeded for sender %s", sender_id)
                ctx.short_circuited = True
                ctx.error = "rate_limit_exceeded"
                return

            timestamps.append(now)

        await next_fn(ctx)
