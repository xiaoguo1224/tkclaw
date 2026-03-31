"""ChannelTransportAdapter — delivers messages to human nodes via channel strategies."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.services.runtime.messaging.envelope import MessageEnvelope
from app.services.runtime.transport.base import DeliveryResult

logger = logging.getLogger(__name__)


class ChannelStrategy(Protocol):
    """Strategy for delivering messages to human nodes via a specific channel."""

    channel_id: str

    async def deliver(
        self,
        *,
        workspace_id: str,
        target_node_id: str,
        user_id: str,
        source_name: str,
        content: str,
        envelope: MessageEnvelope,
        channel_config: dict,
    ) -> bool: ...

    async def receive_webhook(self, payload: dict, headers: dict) -> dict | None:
        """Process an inbound webhook from the channel. Returns parsed message dict or None."""
        ...

    async def verify_signature(self, payload: bytes, headers: dict, secret: str) -> bool:
        """Verify webhook signature. Returns True if valid."""
        ...


class SSEChannelStrategy:
    channel_id = "sse"

    async def deliver(
        self,
        *,
        workspace_id: str,
        target_node_id: str,
        user_id: str,
        source_name: str,
        content: str,
        envelope: MessageEnvelope,
        channel_config: dict,
    ) -> bool:
        from app.api.workspaces import broadcast_event

        broadcast_event(workspace_id, "human:message_delivered", {
            "human_hex_id": target_node_id,
            "user_id": user_id,
            "source_name": source_name,
            "content": content[:200],
            "delivered_via": "sse",
            "trace_id": envelope.traceid,
        })
        return True

    async def receive_webhook(self, payload: dict, headers: dict) -> dict | None:
        return None

    async def verify_signature(self, payload: bytes, headers: dict, secret: str) -> bool:
        return True


class OfflineQueueStrategy:
    """Fallback: enqueue message for later delivery when all channels fail."""

    channel_id = "offline_queue"

    async def deliver(
        self,
        *,
        workspace_id: str,
        target_node_id: str,
        user_id: str,
        source_name: str,
        content: str,
        envelope: MessageEnvelope,
        channel_config: dict,
    ) -> bool:
        try:
            from app.core.deps import async_session_factory
            from app.services.runtime.messaging.envelope import Priority
            from app.services.runtime.messaging.queue import enqueue

            async with async_session_factory() as db:
                await enqueue(
                    db,
                    target_node_id=target_node_id,
                    workspace_id=workspace_id,
                    priority=Priority.NORMAL,
                    envelope=envelope.to_dict(),
                )
                await db.commit()
            logger.info("Message enqueued to offline queue for %s", target_node_id)
            return True
        except Exception as e:
            logger.error("Offline queue enqueue failed: %s", e)
            return False

    async def receive_webhook(self, payload: dict, headers: dict) -> dict | None:
        return None

    async def verify_signature(self, payload: bytes, headers: dict, secret: str) -> bool:
        return True


class FeishuChannelStrategy:
    channel_id = "feishu"

    async def deliver(
        self,
        *,
        workspace_id: str,
        target_node_id: str,
        user_id: str,
        source_name: str,
        content: str,
        envelope: MessageEnvelope,
        channel_config: dict,
    ) -> bool:
        from app.core.config import settings

        if not settings.FEISHU_APP_ID_PORTAL:
            return False

        receive_id: str | None = None
        receive_id_type: str | None = None

        if channel_config.get("chat_id"):
            receive_id = channel_config["chat_id"]
            receive_id_type = "chat_id"
        else:
            from app.core.deps import async_session_factory
            from app.services.channel_adapters.feishu import get_feishu_open_id

            async with async_session_factory() as db:
                open_id = await get_feishu_open_id(user_id, db)
            if open_id:
                receive_id = open_id
                receive_id_type = "open_id"

        if not receive_id or not receive_id_type:
            return False

        try:
            from app.services.channel_adapters.feishu import (
                FeishuChannelAdapter,
                build_workspace_message_card,
            )

            workspace_name = ""
            from app.core.deps import async_session_factory
            from app.models.workspace import Workspace

            async with async_session_factory() as db:
                ws_q = await db.execute(
                    select(Workspace.name).where(
                        Workspace.id == workspace_id,
                        not_deleted(Workspace),
                    )
                )
                workspace_name = ws_q.scalar_one_or_none() or ""

            adapter = FeishuChannelAdapter(
                app_id=settings.FEISHU_APP_ID_PORTAL,
                app_secret=settings.FEISHU_APP_SECRET_PORTAL,
            )
            card = build_workspace_message_card(
                workspace_name=workspace_name,
                workspace_id=workspace_id,
                source_name=source_name,
                content=content,
                human_hex_name="",
                portal_base_url=settings.PORTAL_BASE_URL,
            )
            return await adapter.send_card(
                receive_id=receive_id,
                receive_id_type=receive_id_type,
                card_content=card,
                workspace_id=workspace_id,
            )
        except Exception as e:
            logger.error("Feishu delivery failed: %s", e)
            return False

    async def receive_webhook(self, payload: dict, headers: dict) -> dict | None:
        encrypt = payload.get("encrypt")
        if encrypt:
            logger.debug("Feishu webhook received (encrypted, needs decryption)")
            return None
        event = payload.get("event", {})
        msg = event.get("message", {})
        return {
            "message_id": msg.get("message_id"),
            "content": msg.get("content", ""),
            "sender_id": event.get("sender", {}).get("sender_id", {}).get("open_id", ""),
        } if msg else None

    async def verify_signature(self, payload: bytes, headers: dict, secret: str) -> bool:
        import hashlib
        import hmac

        timestamp = headers.get("X-Lark-Request-Timestamp", "")
        nonce = headers.get("X-Lark-Request-Nonce", "")
        signature = headers.get("X-Lark-Signature", "")
        if not all([timestamp, nonce, signature]):
            return False
        body = f"{timestamp}{nonce}{secret}".encode() + payload
        expected = hashlib.sha256(body).hexdigest()
        return hmac.compare_digest(expected, signature)


class ChannelTransportAdapter:
    """Delivers messages to human nodes via channel strategies (Feishu, SSE, etc.)."""

    transport_id = "channel"

    def __init__(self) -> None:
        self._strategies: dict[str, ChannelStrategy] = {}
        self.register_channel(SSEChannelStrategy())
        self.register_channel(FeishuChannelStrategy())
        self.register_channel(OfflineQueueStrategy())

    def register_channel(self, strategy: ChannelStrategy) -> None:
        self._strategies[strategy.channel_id] = strategy

    async def deliver(
        self,
        envelope: MessageEnvelope,
        target_node_id: str,
        *,
        workspace_id: str = "",
        db: AsyncSession | None = None,
    ) -> DeliveryResult:
        start = time.monotonic()
        data = envelope.data
        source_name = data.sender.name if data else "System"
        content = data.content if data else ""


        if db is None:
            from app.core.deps import async_session_factory
            async with async_session_factory() as db:
                return await self._do_deliver(
                    envelope, target_node_id, workspace_id,
                    source_name, content, db, start,
                )
        return await self._do_deliver(
            envelope, target_node_id, workspace_id,
            source_name, content, db, start,
        )

    async def _do_deliver(
        self,
        envelope: MessageEnvelope,
        target_node_id: str,
        workspace_id: str,
        source_name: str,
        content: str,
        db: AsyncSession,
        start: float,
    ) -> DeliveryResult:
        from app.models.node_card import NodeCard

        card_result = await db.execute(
            select(NodeCard).where(
                NodeCard.node_id == target_node_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            )
        )
        card = card_result.scalar_one_or_none()

        meta = card.metadata_ or {} if card else {}
        channel_type = meta.get("channel_type", "sse")
        user_id = meta.get("user_id", "")
        channel_config = meta.get("channel_config", {})

        fallback_order = self._build_fallback_order(channel_type)

        for strategy_id in fallback_order:
            strategy = self._strategies.get(strategy_id)
            if strategy is None:
                continue
            try:
                ok = await strategy.deliver(
                    workspace_id=workspace_id,
                    target_node_id=target_node_id,
                    user_id=user_id,
                    source_name=source_name,
                    content=content,
                    envelope=envelope,
                    channel_config=channel_config,
                )
                if ok:
                    return DeliveryResult(
                        success=True, target_node_id=target_node_id,
                        transport=self.transport_id,
                        latency_ms=int((time.monotonic() - start) * 1000),
                        extra={"channel": strategy_id},
                    )
                logger.warning(
                    "Channel %s delivery failed for %s, trying fallback",
                    strategy_id, target_node_id,
                )
            except Exception as e:
                logger.error("Channel %s error: %s", strategy_id, e)

        return DeliveryResult(
            success=False, target_node_id=target_node_id,
            transport=self.transport_id, error="all_channels_failed",
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def _build_fallback_order(self, primary: str) -> list[str]:
        """Build fallback chain: primary channel -> SSE -> offline queue."""
        order = []
        if primary and primary not in ("sse", "offline_queue") and primary in self._strategies:
            order.append(primary)
        if "sse" not in order:
            order.append("sse")
        order.append("offline_queue")
        return order

    async def health_check(self, target_node_id: str) -> bool:
        return True


channel_transport = ChannelTransportAdapter()
