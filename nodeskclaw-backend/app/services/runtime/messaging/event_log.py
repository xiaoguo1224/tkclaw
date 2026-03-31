"""Event sourcing log — append-only event recording for message lifecycle tracking."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_log import EventLog

logger = logging.getLogger(__name__)

EVENT_TYPES = [
    "message_created",
    "message_routed",
    "message_delivering",
    "message_delivered",
    "message_failed",
    "message_retried",
    "message_dead_lettered",
    "priority_promoted",
    "circuit_opened",
    "circuit_closed",
]


async def record_event(
    db: AsyncSession,
    *,
    event_type: str,
    message_id: str | None = None,
    workspace_id: str | None = None,
    source_node_id: str | None = None,
    target_node_id: str | None = None,
    trace_id: str | None = None,
    data: dict | None = None,
) -> EventLog:
    event = EventLog(
        event_type=event_type,
        message_id=message_id,
        workspace_id=workspace_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        trace_id=trace_id,
        data=data,
    )
    db.add(event)
    await db.flush()
    return event


async def get_message_events(
    db: AsyncSession,
    message_id: str,
) -> list[EventLog]:
    result = await db.execute(
        select(EventLog)
        .where(
            EventLog.message_id == message_id,
            EventLog.deleted_at.is_(None),
        )
        .order_by(EventLog.created_at.asc())
    )
    return list(result.scalars().all())


async def get_trace_events(
    db: AsyncSession,
    trace_id: str,
) -> list[EventLog]:
    result = await db.execute(
        select(EventLog)
        .where(
            EventLog.trace_id == trace_id,
            EventLog.deleted_at.is_(None),
        )
        .order_by(EventLog.created_at.asc())
    )
    return list(result.scalars().all())


async def get_workspace_events(
    db: AsyncSession,
    workspace_id: str,
    *,
    event_type: str | None = None,
    limit: int = 100,
    since: datetime | None = None,
) -> list[EventLog]:
    stmt = (
        select(EventLog)
        .where(
            EventLog.workspace_id == workspace_id,
            EventLog.deleted_at.is_(None),
        )
        .order_by(EventLog.created_at.desc())
        .limit(limit)
    )
    if event_type:
        stmt = stmt.where(EventLog.event_type == event_type)
    if since:
        stmt = stmt.where(EventLog.created_at >= since)
    result = await db.execute(stmt)
    return list(result.scalars().all())
