"""ChannelPluginBridge — injects workspace context via Channel Plugin deployment."""

from __future__ import annotations

import logging

from app.services.runtime.context_bridges.base import WorkspaceContext

logger = logging.getLogger(__name__)


class ChannelPluginBridge:
    bridge_id = "channel_plugin"

    async def inject_context(
        self,
        instance_id: str,
        workspace_id: str,
        context: WorkspaceContext,
    ) -> None:
        logger.info(
            "ChannelPluginBridge.inject_context: instance=%s workspace=%s",
            instance_id, workspace_id,
        )
        try:
            from app.core.deps import async_session_factory
            from app.services.llm_config_service import deploy_nodeskclaw_channel_plugin

            async with async_session_factory() as db:
                from app.models.instance import Instance
                from sqlalchemy import select

                result = await db.execute(
                    select(Instance).where(
                        Instance.id == instance_id,
                        Instance.deleted_at.is_(None),
                    )
                )
                inst = result.scalar_one_or_none()
                if inst:
                    await deploy_nodeskclaw_channel_plugin(inst, db, workspace_id)
                    logger.info(
                        "ChannelPlugin deployed for instance %s in workspace %s",
                        instance_id, workspace_id,
                    )
        except Exception as e:
            logger.warning("ChannelPluginBridge.inject_context failed: %s", e)

    async def remove_context(
        self,
        instance_id: str,
        workspace_id: str,
    ) -> None:
        logger.debug(
            "ChannelPluginBridge.remove_context: instance=%s workspace=%s",
            instance_id, workspace_id,
        )
