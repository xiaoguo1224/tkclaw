"""RetentionPolicy — tiered cleanup for event_logs (hot/warm/cold) and queue items."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

HOT_RETENTION_DAYS = 30
WARM_RETENTION_DAYS = 90
MESSAGE_QUEUE_RETENTION_DAYS = 7


async def compact_warm_event_logs(db: AsyncSession) -> int:
    """Compact warm-tier events: strip JSONB data but keep metadata (30d < age <= 90d)."""
    from app.models.event_log import EventLog

    hot_cutoff = datetime.now(timezone.utc) - timedelta(days=HOT_RETENTION_DAYS)
    warm_cutoff = datetime.now(timezone.utc) - timedelta(days=WARM_RETENTION_DAYS)

    result = await db.execute(
        update(EventLog)
        .where(
            EventLog.created_at < hot_cutoff,
            EventLog.created_at >= warm_cutoff,
            EventLog.data.isnot(None),
        )
        .values(data=None)
    )
    count = result.rowcount or 0
    if count > 0:
        logger.info("Retention: compacted %d warm event_logs (stripped data column)", count)
    return count


async def cleanup_event_logs(db: AsyncSession, retention_days: int = WARM_RETENTION_DAYS) -> int:
    """Soft-delete event_logs older than warm tier."""
    from sqlalchemy import func

    from app.models.event_log import EventLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    result = await db.execute(
        update(EventLog)
        .where(
            EventLog.created_at < cutoff,
            EventLog.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    count = result.rowcount or 0
    if count > 0:
        logger.info("Retention: soft-deleted %d event_logs older than %d days", count, retention_days)
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
    warm_compacted = await compact_warm_event_logs(db)
    events_deleted = await cleanup_event_logs(db)
    queue_deleted = await cleanup_consumed_queue_items(db)
    return {
        "event_logs_warm_compacted": warm_compacted,
        "event_logs_soft_deleted": events_deleted,
        "queue_items_deleted": queue_deleted,
    }
