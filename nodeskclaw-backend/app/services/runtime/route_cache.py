"""RouteTable — in-memory topology cache with PG NOTIFY invalidation."""

from __future__ import annotations

import logging
import time

from app.services.runtime.messaging.delivery_plan import DeliveryTarget

logger = logging.getLogger(__name__)

CACHE_TTL_S = 60


class RouteTable:
    def __init__(self, ttl_s: int = CACHE_TTL_S) -> None:
        self._cache: dict[str, tuple[float, list[DeliveryTarget]]] = {}
        self._ttl_s = ttl_s

    def get(self, workspace_id: str) -> list[DeliveryTarget] | None:
        entry = self._cache.get(workspace_id)
        if entry is None:
            return None
        ts, targets = entry
        if time.monotonic() - ts > self._ttl_s:
            del self._cache[workspace_id]
            return None
        return targets

    def put(self, workspace_id: str, targets: list[DeliveryTarget]) -> None:
        self._cache[workspace_id] = (time.monotonic(), targets)

    def invalidate(self, workspace_id: str) -> None:
        self._cache.pop(workspace_id, None)
        logger.debug("RouteTable: invalidated cache for workspace %s", workspace_id)

    def invalidate_all(self) -> None:
        self._cache.clear()
        logger.debug("RouteTable: invalidated all cached routes")

    @property
    def size(self) -> int:
        return len(self._cache)


route_table = RouteTable()
