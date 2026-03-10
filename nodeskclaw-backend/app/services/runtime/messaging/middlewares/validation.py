"""ValidationMiddleware — schema validation, idempotency, and workspace isolation."""

from __future__ import annotations

import logging

from app.services.runtime.messaging.pipeline import MessageMiddleware, NextFn, PipelineContext

logger = logging.getLogger(__name__)


class ValidationMiddleware(MessageMiddleware):
    async def process(self, ctx: PipelineContext, next_fn: NextFn) -> None:
        envelope = ctx.envelope
        if envelope.data is None:
            logger.warning("ValidationMiddleware: envelope %s has no data, rejecting", envelope.id)
            ctx.short_circuited = True
            ctx.error = "envelope.data is required"
            return

        if not envelope.data.content and not envelope.data.attachments:
            logger.warning("ValidationMiddleware: envelope %s has empty content, rejecting", envelope.id)
            ctx.short_circuited = True
            ctx.error = "message content or attachments required"
            return

        if not envelope.workspaceid:
            logger.warning("ValidationMiddleware: envelope %s missing workspaceid", envelope.id)
            ctx.short_circuited = True
            ctx.error = "workspaceid is required"
            return

        db = ctx.db
        if db is not None:
            if await self._check_idempotency(ctx, db):
                return

            from app.services.runtime.security import check_workspace_isolation
            isolation_ok, _reason = await check_workspace_isolation(
                db,
                envelope.workspaceid,
                [envelope.data.sender.id] if envelope.data.sender else [],
            )
            if not isolation_ok:
                logger.warning(
                    "ValidationMiddleware: workspace isolation check failed for %s",
                    envelope.id,
                )
                ctx.short_circuited = True
                ctx.error = "workspace_isolation_violation"
                return

        await next_fn(ctx)

    async def _check_idempotency(self, ctx: PipelineContext, db) -> bool:
        """Return True if this message was already processed (short-circuits)."""
        try:
            from sqlalchemy import select

            from app.models.idempotency_cache import IdempotencyCache

            result = await db.execute(
                select(IdempotencyCache).where(
                    IdempotencyCache.message_id == ctx.envelope.id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.info("Idempotency: duplicate message %s, short-circuiting", ctx.envelope.id)
                ctx.short_circuited = True
                ctx.extra["idempotency_hit"] = True
                return True

            cache_entry = IdempotencyCache(message_id=ctx.envelope.id)
            db.add(cache_entry)
            await db.flush()
        except Exception as e:
            logger.warning("Idempotency check failed (non-fatal): %s", e)
        return False
