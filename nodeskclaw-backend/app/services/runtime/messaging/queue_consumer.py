"""QueueConsumer — PG NOTIFY-driven message queue consumer with poll fallback.

Listens for `message_enqueued:{node_id}` notifications via PG NOTIFY.
On notification, immediately dequeues and delivers pending messages.
A 5-second polling loop serves as a fallback when NOTIFY is lost.
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 5
CONSUMER_BATCH_SIZE = 10

_consumer_task: asyncio.Task | None = None
_notify_event = asyncio.Event()
_target_node_hint: str | None = None


async def on_queue_notify(channel: str, payload: str) -> None:
    """Called by PGNotifyService when a message_enqueued notification arrives."""
    global _target_node_hint
    try:
        data = json.loads(payload)
        _target_node_hint = data.get("target_node_id")
    except Exception:
        _target_node_hint = None
    _notify_event.set()


async def _consume_loop(session_factory) -> None:
    """Main consumer loop: wake on NOTIFY or every POLL_INTERVAL_S.

    Only processes messages for instances connected to this Pod via tunnel.
    Messages for instances on other Pods are skipped, allowing the correct
    Pod's consumer to pick them up.
    """
    from app.services.runtime.messaging.envelope import MessageEnvelope
    from app.services.runtime.messaging.queue import ack, dequeue, nack
    from app.services.tunnel import tunnel_adapter

    logger.info("QueueConsumer: started")

    while True:
        try:
            await asyncio.wait_for(
                _notify_event.wait(), timeout=POLL_INTERVAL_S,
            )
        except asyncio.TimeoutError:
            pass
        finally:
            _notify_event.clear()

        try:
            async with session_factory() as db:
                target_hint = _target_node_hint
                local_instances = tunnel_adapter.connected_instances

                if target_hint:
                    if target_hint not in local_instances:
                        continue
                    items = await dequeue(db, target_node_id=target_hint, batch_size=CONSUMER_BATCH_SIZE)
                else:
                    from sqlalchemy import select

                    from app.models.base import not_deleted
                    from app.models.message_queue import MessageQueueItem

                    pending_q = await db.execute(
                        select(MessageQueueItem.target_node_id)
                        .where(
                            MessageQueueItem.status == "pending",
                            not_deleted(MessageQueueItem),
                        )
                        .distinct()
                        .limit(20)
                    )
                    node_ids = [row[0] for row in pending_q.all()]
                    items = []
                    for nid in node_ids:
                        if nid not in local_instances:
                            continue
                        batch = await dequeue(db, target_node_id=nid, batch_size=CONSUMER_BATCH_SIZE)
                        items.extend(batch)

                if not items:
                    continue

                for item in items:
                    try:
                        envelope = MessageEnvelope.from_dict(item.envelope or {})
                        workspace_id = item.workspace_id or envelope.workspaceid

                        result = await tunnel_adapter.deliver(
                            envelope, item.target_node_id,
                            workspace_id=workspace_id, db=db,
                        )
                        if result.success:
                            await ack(db, str(item.id))
                        else:
                            await nack(db, str(item.id), result.error or "delivery_failed")
                    except Exception as e:
                        logger.error("QueueConsumer: failed to process item %s: %s", item.id, e)
                        try:
                            await nack(db, str(item.id), str(e))
                        except Exception:
                            logger.warning("QueueConsumer: nack also failed for item %s", item.id, exc_info=True)

                await db.commit()

        except Exception as e:
            logger.error("QueueConsumer: loop error: %s", e)
            await asyncio.sleep(1)


def start_consumer(session_factory) -> asyncio.Task:
    """Start the background consumer coroutine. Returns the task."""
    global _consumer_task
    if _consumer_task is not None and not _consumer_task.done():
        return _consumer_task
    _consumer_task = asyncio.create_task(_consume_loop(session_factory))
    return _consumer_task


def stop_consumer() -> None:
    """Cancel the background consumer."""
    global _consumer_task
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
    _consumer_task = None
