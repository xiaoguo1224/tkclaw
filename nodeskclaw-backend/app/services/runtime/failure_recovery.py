"""Instance failure recovery — heartbeat monitoring and stale connection cleanup.

Runs as a periodic background task during lifespan:
  - Scans sse_connections for heartbeat timeouts (30s threshold)
  - Soft-deletes stale connections
  - PG transaction rollback auto-releases FOR UPDATE locks on message_queue
  - Surviving clients reconnect and get assigned to live backend instances
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.runtime import sse_registry

logger = logging.getLogger(__name__)

SCAN_INTERVAL_S = 30


async def _update_agent_health(db) -> None:
    """Dual-layer health check: combine heartbeat scan with tunnel connection probes."""
    try:
        from app.models.base import not_deleted
        from app.models.node_card import NodeCard
        from app.services.tunnel import tunnel_adapter
        from sqlalchemy import select

        result = await db.execute(
            select(NodeCard).where(
                NodeCard.node_type == "agent",
                NodeCard.status.in_(["active", "idle", "unhealthy"]),
                not_deleted(NodeCard),
            )
        )
        cards = result.scalars().all()
        for card in cards:
            is_healthy = await tunnel_adapter.health_check(card.node_id)
            new_status = "active" if is_healthy else "unhealthy"
            if card.status != new_status:
                old_status = card.status
                card.status = new_status
                logger.info("Agent %s health updated: %s -> %s", card.node_id, old_status, new_status)
        await db.flush()
    except Exception as e:
        logger.warning("Agent health update failed: %s", e)


async def run_heartbeat_scanner(session_factory: Any) -> None:
    """Long-running coroutine that periodically cleans up stale SSE connections and checks agent health."""
    logger.info("Heartbeat scanner started (interval=%ds)", SCAN_INTERVAL_S)
    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL_S)
            async with session_factory() as db:
                cleaned = await sse_registry.cleanup_stale_connections(db)
                await _update_agent_health(db)
                if cleaned:
                    await db.commit()
                else:
                    await db.commit()
        except asyncio.CancelledError:
            logger.info("Heartbeat scanner cancelled")
            break
        except Exception:
            logger.exception("Heartbeat scanner error")


async def shutdown_cleanup(session_factory: Any) -> None:
    """Called during graceful shutdown to unregister this backend's connections."""
    try:
        async with session_factory() as db:
            cleaned = await sse_registry.cleanup_backend_connections(db)
            await db.commit()
            logger.info("Shutdown cleanup: removed %d connections for this backend", cleaned)
    except Exception:
        logger.exception("Shutdown cleanup failed")
