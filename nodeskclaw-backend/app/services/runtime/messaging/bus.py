"""MessageBus — central entry point for all messages in the DeskClaw runtime platform."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.runtime.messaging.envelope import MessageEnvelope
from app.services.runtime.messaging.middlewares.audit import AuditMiddleware
from app.services.runtime.messaging.middlewares.circuit_breaker import CircuitBreakerMiddleware
from app.services.runtime.messaging.middlewares.content_filter import ContentFilterMiddleware
from app.services.runtime.messaging.middlewares.metrics import MetricsMiddleware
from app.services.runtime.messaging.middlewares.rate_limit import RateLimitMiddleware
from app.services.runtime.messaging.middlewares.routing import RoutingMiddleware
from app.services.runtime.messaging.middlewares.semantic import SemanticMiddleware
from app.services.runtime.messaging.middlewares.transport import TransportMiddleware
from app.services.runtime.messaging.middlewares.validation import ValidationMiddleware
from app.services.runtime.messaging.pipeline import MessagePipeline, PipelineContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MessageBus:
    def __init__(self) -> None:
        self._pipeline = MessagePipeline()
        self._pipeline.use(MetricsMiddleware())
        self._pipeline.use(ValidationMiddleware())
        self._pipeline.use(ContentFilterMiddleware())
        self._pipeline.use(RateLimitMiddleware())
        self._pipeline.use(SemanticMiddleware())
        self._pipeline.use(RoutingMiddleware())
        self._pipeline.use(CircuitBreakerMiddleware())
        self._pipeline.use(TransportMiddleware())
        self._pipeline.use(AuditMiddleware())

    async def publish(
        self, envelope: MessageEnvelope, *, db: AsyncSession | None = None,
    ) -> PipelineContext:
        logger.info(
            "MessageBus.publish: id=%s type=%s workspace=%s sender=%s",
            envelope.id,
            envelope.type,
            envelope.workspaceid,
            envelope.data.sender.name if envelope.data else "?",
        )

        ctx = PipelineContext(
            envelope=envelope,
            workspace_id=envelope.workspaceid,
            db=db,
        )

        result = await self._pipeline.execute(ctx)

        if result.error:
            logger.error("MessageBus: pipeline error for %s: %s", envelope.id, result.error)

        return result


message_bus = MessageBus()
