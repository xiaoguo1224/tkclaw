"""PG LISTEN/NOTIFY integration for real-time cross-instance coordination.

Channels:
  - topology_changed        : topology mutation -> route cache invalidation
  - sse_push:{backend_id}   : cross-instance SSE push forwarding
  - message_enqueued:{node}  : new message in queue -> replaces 5s polling with real-time
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

NotifyHandler = Callable[[str, str], Awaitable[None]]


class PGNotifyService:
    """Manages PG LISTEN/NOTIFY subscriptions.

    Publish side uses any AsyncSession via class methods.
    Listen side requires a dedicated asyncpg connection (started in lifespan).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[NotifyHandler]] = defaultdict(list)
        self._listening = False
        self._listen_task: asyncio.Task | None = None

    def subscribe(self, channel: str, handler: NotifyHandler) -> None:
        self._handlers[channel].append(handler)

    def unsubscribe(self, channel: str, handler: NotifyHandler) -> None:
        handlers = self._handlers.get(channel, [])
        if handler in handlers:
            handlers.remove(handler)

    @staticmethod
    async def notify(db: AsyncSession, channel: str, payload: str = "") -> None:
        await db.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": channel, "payload": payload},
        )

    @staticmethod
    async def notify_topology_changed(db: AsyncSession, workspace_id: str) -> None:
        await PGNotifyService.notify(db, "topology_changed", json.dumps({"workspace_id": workspace_id}))

    @staticmethod
    async def notify_sse_push(
        db: AsyncSession, backend_instance_id: str, payload: dict[str, Any],
    ) -> None:
        channel = f"sse_push:{backend_instance_id}"
        await PGNotifyService.notify(db, channel, json.dumps(payload, default=str))

    @staticmethod
    async def notify_message_enqueued(
        db: AsyncSession, target_node_id: str,
    ) -> None:
        channel = f"message_enqueued:{target_node_id}"
        await PGNotifyService.notify(db, channel, target_node_id)

    async def _dispatch(self, channel: str, payload: str) -> None:
        handlers = self._handlers.get(channel, [])
        prefix_handlers: list[NotifyHandler] = []
        for registered_channel, h_list in self._handlers.items():
            if registered_channel.endswith("*") and channel.startswith(registered_channel[:-1]):
                prefix_handlers.extend(h_list)
        all_handlers = handlers + prefix_handlers
        for handler in all_handlers:
            try:
                await handler(channel, payload)
            except Exception:
                logger.exception("PG NOTIFY handler error: channel=%s", channel)

    async def start_listening(self, raw_conn: Any, channels: list[str]) -> None:
        """Start listening on given channels using a raw asyncpg connection.

        `raw_conn` should be an asyncpg.Connection (obtained from engine.raw_connection()).
        """
        self._listening = True
        for ch in channels:
            await raw_conn.add_listener(ch, self._asyncpg_callback)
            logger.info("PG LISTEN on channel: %s", ch)

    def _asyncpg_callback(
        self, conn: Any, pid: int, channel: str, payload: str,
    ) -> None:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(self._dispatch(channel, payload))

    async def stop_listening(self, raw_conn: Any, channels: list[str]) -> None:
        self._listening = False
        for ch in channels:
            try:
                await raw_conn.remove_listener(ch, self._asyncpg_callback)
            except Exception:
                logger.warning("Failed to remove listener for channel: %s", ch)
        logger.info("PG NOTIFY listeners stopped")


pg_notify_service = PGNotifyService()
