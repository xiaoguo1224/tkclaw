"""RetentionPolicy — periodic cleanup of aged event_logs and consumed message_queue items."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted

logger = logging.getLogger(__name__)

EVENT_LOG_RETENTION_DAYS = 30
MESSAGE_QUEUE_RETENTION_DAYS = 7


async def cleanup_event_logs(db: AsyncSession, retention_days: int = EVENT_LOG_RETENTION_DAYS) -> int:
    from app.models.event_log import EventLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        delete(EventLog).where(EventLog.created_at < cutoff)
    )
    count = result.rowcount or 0
    if count > 0:
        logger.info("Retention: deleted %d event_logs older than %d days", count, retention_days)
    return count


async def cleanup_consumed_queue_items(db: AsyncSession, retention_days: int = MESSAGE_QUEUE_RETENTION_DAYS) -> int:
    from app.models.message_queue import MessageQueueItem

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        delete(MessageQueueItem).where(
            MessageQueueItem.status == "delivered",
            MessageQueueItem.created_at < cutoff,
        )
    )
    count = result.rowcount or 0
    if count > 0:
        logger.info("Retention: deleted %d consumed queue items older than %d days", count, retention_days)
    return count


async def run_retention_cleanup(db: AsyncSession) -> dict:
    events_deleted = await cleanup_event_logs(db)
    queue_deleted = await cleanup_consumed_queue_items(db)
    return {
        "event_logs_deleted": events_deleted,
        "queue_items_deleted": queue_deleted,
    }
