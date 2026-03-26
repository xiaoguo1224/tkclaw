"""PGMQ — PostgreSQL-backed message queue with WFQ, retry, and dead-letter support."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.dead_letter import DeadLetter
from app.models.message_queue import MessageQueueItem
from app.services.runtime.messaging.envelope import PRIORITY_WEIGHT, Priority

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 5
MAX_ATTEMPTS = 3
INITIAL_RETRY_DELAY_S = 2
BACKOFF_FACTOR = 2
JITTER = 0.1

BACKPRESSURE_THRESHOLDS = {
    "FULL": 5,
    "NORMAL_ONLY": 20,
    "CRITICAL_ONLY": 50,
}


async def enqueue(
    db: AsyncSession,
    *,
    target_node_id: str,
    workspace_id: str,
    envelope: dict,
    priority: Priority = Priority.NORMAL,
    scheduled_at: datetime | None = None,
) -> MessageQueueItem:
    import json

    item = MessageQueueItem(
        target_node_id=target_node_id,
        workspace_id=workspace_id,
        priority=PRIORITY_WEIGHT.get(priority, 4),
        status="pending",
        scheduled_at=scheduled_at or datetime.now(timezone.utc),
        envelope=envelope,
    )
    db.add(item)
    await db.flush()

    try:
        payload = json.dumps({"target_node_id": target_node_id})
        await db.execute(text("SELECT pg_notify('message_enqueued', :payload)"), {"payload": payload})
    except Exception:
        logger.warning("pg_notify for message_enqueued failed (node=%s)", target_node_id, exc_info=True)

    return item


async def dequeue(
    db: AsyncSession,
    *,
    target_node_id: str,
    batch_size: int = 1,
) -> list[MessageQueueItem]:
    """Consume messages for a target using WFQ virtual-time ordering.

    virtual_time = epoch(created_at) / weight(priority).
    Lower virtual_time = higher effective priority, preventing starvation
    because old low-priority messages eventually gain precedence.
    """
    from sqlalchemy import case, extract

    weight_expr = case(
        (MessageQueueItem.priority == PRIORITY_WEIGHT[Priority.CRITICAL], 8),
        (MessageQueueItem.priority == PRIORITY_WEIGHT[Priority.NORMAL], 4),
        else_=1,
    )
    vtime_expr = extract("epoch", MessageQueueItem.created_at) / weight_expr

    stmt = (
        select(MessageQueueItem)
        .where(
            MessageQueueItem.target_node_id == target_node_id,
            MessageQueueItem.status == "pending",
            MessageQueueItem.scheduled_at <= datetime.now(timezone.utc),
            not_deleted(MessageQueueItem),
        )
        .order_by(vtime_expr.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    for item in items:
        item.status = "delivering"
        item.attempt_count += 1

    await db.flush()
    return items


async def ack(db: AsyncSession, item_id: str) -> None:
    await db.execute(
        update(MessageQueueItem)
        .where(MessageQueueItem.id == item_id)
        .values(status="delivered")
    )


NO_RETRY_ERRORS = frozenset({
    "node_card_not_found",
    "instance_not_found",
    "workspace_isolation_violation",
})


async def nack(db: AsyncSession, item_id: str, error: str = "") -> None:
    import random

    result = await db.execute(
        select(MessageQueueItem).where(MessageQueueItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        return

    skip_retry = error in NO_RETRY_ERRORS

    if skip_retry or item.attempt_count >= item.max_attempts:
        item.status = "dead_letter"
        item.error_message = error

        dl = DeadLetter(
            message_id=item.id,
            workspace_id=item.workspace_id,
            target_node_id=item.target_node_id,
            original_priority=item.priority,
            attempt_count=item.attempt_count,
            last_error=error,
            envelope=item.envelope,
            recoverable=error not in NO_RETRY_ERRORS,
        )
        db.add(dl)
        logger.warning(
            "Message %s moved to dead letter after %d attempts (error=%s, recoverable=%s)",
            item.id, item.attempt_count, error, dl.recoverable,
        )
    else:
        jitter_factor = 1 + random.uniform(-JITTER, JITTER)
        delay = INITIAL_RETRY_DELAY_S * (BACKOFF_FACTOR ** (item.attempt_count - 1)) * jitter_factor
        item.status = "retrying"
        item.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        item.error_message = error

    await db.flush()


async def promote_retries(db: AsyncSession) -> int:
    """Move retrying items past their next_retry_at back to pending."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(MessageQueueItem)
        .where(
            MessageQueueItem.status == "retrying",
            MessageQueueItem.next_retry_at <= now,
            not_deleted(MessageQueueItem),
        )
        .values(status="pending")
    )
    return result.rowcount  # type: ignore[return-value]


async def promote_aged_priorities(db: AsyncSession) -> int:
    """Promote old messages: background > 5min -> normal, normal > 10min -> critical."""
    now = datetime.now(timezone.utc)
    count = 0

    bg_cutoff = now - timedelta(minutes=5)
    r1 = await db.execute(
        update(MessageQueueItem)
        .where(
            MessageQueueItem.status == "pending",
            MessageQueueItem.priority == PRIORITY_WEIGHT[Priority.BACKGROUND],
            MessageQueueItem.created_at <= bg_cutoff,
            not_deleted(MessageQueueItem),
        )
        .values(priority=PRIORITY_WEIGHT[Priority.NORMAL])
    )
    count += r1.rowcount  # type: ignore[operator]

    normal_cutoff = now - timedelta(minutes=10)
    r2 = await db.execute(
        update(MessageQueueItem)
        .where(
            MessageQueueItem.status == "pending",
            MessageQueueItem.priority == PRIORITY_WEIGHT[Priority.NORMAL],
            MessageQueueItem.created_at <= normal_cutoff,
            not_deleted(MessageQueueItem),
        )
        .values(priority=PRIORITY_WEIGHT[Priority.CRITICAL])
    )
    count += r2.rowcount  # type: ignore[operator]

    return count


async def get_queue_depth(
    db: AsyncSession, target_node_id: str,
) -> int:
    result = await db.execute(
        select(MessageQueueItem)
        .where(
            MessageQueueItem.target_node_id == target_node_id,
            MessageQueueItem.status.in_(["pending", "retrying"]),
            not_deleted(MessageQueueItem),
        )
    )
    return len(result.scalars().all())


def get_backpressure_level(queue_depth: int) -> str:
    if queue_depth < BACKPRESSURE_THRESHOLDS["FULL"]:
        return "FULL"
    if queue_depth < BACKPRESSURE_THRESHOLDS["NORMAL_ONLY"]:
        return "NORMAL_ONLY"
    if queue_depth < BACKPRESSURE_THRESHOLDS["CRITICAL_ONLY"]:
        return "CRITICAL_ONLY"
    return "NONE"


async def recover_dead_letter(db: AsyncSession, dead_letter_id: str, user_id: str) -> bool:
    result = await db.execute(
        select(DeadLetter).where(
            DeadLetter.id == dead_letter_id,
            DeadLetter.recovered_at.is_(None),
            not_deleted(DeadLetter),
        )
    )
    dl = result.scalar_one_or_none()
    if dl is None:
        return False

    new_item = MessageQueueItem(
        target_node_id=dl.target_node_id,
        workspace_id=dl.workspace_id,
        priority=dl.original_priority,
        status="pending",
        envelope=dl.envelope,
        attempt_count=0,
    )
    db.add(new_item)

    dl.recovered_at = datetime.now(timezone.utc)
    dl.recovered_by = user_id

    await db.flush()
    logger.info("Dead letter %s recovered by %s", dead_letter_id, user_id)
    return True
