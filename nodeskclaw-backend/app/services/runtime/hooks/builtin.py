"""Built-in CE hooks registered during application startup.

EE extends via ee.backend.hooks.register_all_hooks() loaded conditionally by FeatureGate.
"""

from __future__ import annotations

import logging

from app.services.runtime.hooks.manager import node_hook_manager

logger = logging.getLogger(__name__)


async def _on_node_join(**kwargs) -> None:
    node_id = kwargs.get("node_id", "")
    node_type = kwargs.get("node_type", "")
    workspace_id = kwargs.get("workspace_id", "")
    logger.info(
        "Node joined: type=%s id=%s workspace=%s",
        node_type, node_id, workspace_id,
    )

    if node_id and workspace_id:
        try:
            from app.core.deps import async_session_factory
            from app.services.runtime.messaging.queue import dequeue

            async with async_session_factory() as db:
                pending = await dequeue(db, target_node_id=node_id, batch_size=50)
                if pending:
                    logger.info(
                        "Replaying %d offline messages for node %s",
                        len(pending), node_id,
                    )
                    from app.services.runtime.messaging.bus import message_bus
                    from app.services.runtime.messaging.envelope import MessageEnvelope

                    for item in pending:
                        try:
                            envelope = MessageEnvelope.from_dict(item.envelope)
                            envelope.data.extensions["offline_replay"] = True
                            await message_bus.publish(envelope, db=db)
                            from app.services.runtime.messaging.queue import ack
                            await ack(db, item.id)
                        except Exception as e:
                            logger.warning("Failed to replay message %s: %s", item.id, e)
                            from app.services.runtime.messaging.queue import nack
                            await nack(db, item.id, str(e))
                    await db.commit()
        except Exception as e:
            logger.warning("Offline message replay failed for %s: %s", node_id, e)


async def _on_node_leave(**kwargs) -> None:
    node_id = kwargs.get("node_id", "")
    node_type = kwargs.get("node_type", "")
    workspace_id = kwargs.get("workspace_id", "")
    logger.info(
        "Node left: type=%s id=%s workspace=%s",
        node_type, node_id, workspace_id,
    )


async def _on_card_update(**kwargs) -> None:
    node_id = kwargs.get("node_id", "")
    logger.debug("NodeCard updated: id=%s", node_id)


async def _on_status_change(**kwargs) -> None:
    node_id = kwargs.get("node_id", "")
    old_status = kwargs.get("old_status", "")
    new_status = kwargs.get("new_status", "")
    logger.info("Node status change: id=%s %s -> %s", node_id, old_status, new_status)


async def _on_agent_message_received(**kwargs) -> None:
    node_id = kwargs.get("node_id", "")
    message_id = kwargs.get("message_id", "")
    logger.debug("Agent received message: node=%s msg=%s", node_id, message_id)


def register_builtin_hooks() -> None:
    node_hook_manager.on_global("on_node_join", _on_node_join)
    node_hook_manager.on_global("on_node_leave", _on_node_leave)
    node_hook_manager.on_global("on_card_update", _on_card_update)
    node_hook_manager.on_global("on_status_change", _on_status_change)

    node_hook_manager.on_type("agent", "on_message_received", _on_agent_message_received)

    logger.info("Built-in CE hooks registered")
