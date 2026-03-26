"""NanoBot channel plugin -- integrates with NanoBot's channel system via entry_points."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("nodeskclaw_tunnel_bridge.nanobot")

try:
    from nanobot.bus.events import OutboundMessage
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.base import BaseChannel
except ImportError:
    BaseChannel = object  # type: ignore[assignment,misc]
    OutboundMessage = object  # type: ignore[assignment,misc]
    MessageBus = object  # type: ignore[assignment,misc]


class NoDeskClawChannel(BaseChannel):  # type: ignore[misc]
    """NanoBot channel that connects to NoDeskClaw tunnel for workspace group chat."""

    name = "nodeskclaw"
    display_name = "NoDeskClaw"

    def __init__(self, config: Any, bus: MessageBus) -> None:
        super().__init__(config, bus)
        self._no_reply_ids: set[str] = set()
        self._pending_requests: dict[str, tuple[str, str]] = {}
        self._tunnel_task: asyncio.Task | None = None
        self._workspace_id: str = ""

    async def start(self) -> None:
        if hasattr(self, "_client") and self._client:
            logger.warning("NoDeskClaw channel: stopping previous tunnel client before restart")
            await self._client.close()

        from .client import TunnelCallbacks, TunnelClient

        callbacks = TunnelCallbacks(
            on_auth_ok=lambda: logger.info("NoDeskClaw channel: tunnel authenticated"),
            on_auth_error=lambda reason: logger.error("NoDeskClaw channel: tunnel auth failed: %s", reason),
            on_close=lambda: logger.warning("NoDeskClaw channel: tunnel connection closed"),
            on_reconnecting=lambda attempt: logger.info("NoDeskClaw channel: tunnel reconnecting (attempt #%d)", attempt),
        )
        self._client = TunnelClient(on_chat_request=self._handle_chat_request, callbacks=callbacks)
        self._running = True
        logger.info("NoDeskClaw channel starting tunnel client...")
        await self._client.run_forever()

    async def stop(self) -> None:
        self._running = False
        if hasattr(self, "_client"):
            await self._client.close()

    async def send(self, msg: OutboundMessage) -> None:
        """Called by NanoBot's ChannelManager when AgentLoop produces a response."""
        chat_id = getattr(msg, "chat_id", "")

        if chat_id in self._no_reply_ids:
            self._no_reply_ids.discard(chat_id)
            self._pending_requests.pop(chat_id, None)
            return

        req_info = self._pending_requests.pop(chat_id, None)
        if not req_info:
            return

        reply_to, trace_id = req_info
        content = getattr(msg, "content", "") or ""

        if content:
            await self._client.send_response_chunk(reply_to, trace_id, content)
        await self._client.send_response_done(reply_to, trace_id)

    async def send_collaboration(self, target: str, text: str) -> None:
        await self._client.send_collaboration(
            self._workspace_id, self._client.instance_id, target, text,
        )

    async def list_peers(self) -> list[dict]:
        return await self._client.list_peers(self._workspace_id)

    async def _handle_chat_request(
        self,
        request_id: str,
        trace_id: str,
        messages: list[dict[str, Any]],
        workspace_id: str,
        no_reply: bool,
    ) -> None:
        if workspace_id:
            self._workspace_id = workspace_id
        user_content = _extract_full_content(messages)
        session_key = f"nodeskclaw:{workspace_id}" if workspace_id else None

        self._pending_requests[request_id] = (request_id, trace_id)

        if no_reply:
            self._no_reply_ids.add(request_id)

        await self._handle_message(
            sender_id="workspace_user",
            chat_id=request_id,
            content=user_content,
            session_key=session_key,
        )

        if no_reply:
            await self._client.send_response_done(request_id, trace_id)


def _extract_full_content(messages: list[dict[str, Any]]) -> str:
    """Concatenate all message contents so system prompt reaches NanoBot."""
    return "\n\n".join(
        msg.get("content", "") for msg in messages if msg.get("content")
    )
