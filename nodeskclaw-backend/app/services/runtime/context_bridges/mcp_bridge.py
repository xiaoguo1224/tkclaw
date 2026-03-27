"""MCPContextBridge — configures DeskClaw MCP server for workspace context access."""

from __future__ import annotations

import json
import logging

from app.services.runtime.context_bridges.base import WorkspaceContext

logger = logging.getLogger(__name__)


class MCPContextBridge:
    bridge_id = "mcp"

    async def inject_context(
        self,
        instance_id: str,
        workspace_id: str,
        context: WorkspaceContext,
    ) -> None:
        logger.info(
            "MCPContextBridge.inject_context: instance=%s workspace=%s",
            instance_id, workspace_id,
        )
        try:
            from app.core.deps import async_session_factory

            mcp_config = {
                "workspace_id": workspace_id,
                "workspace_name": context.workspace_name,
                "agent_identity": context.agent_identity,
                "team": context.team,
                "blackboard_state": context.blackboard_state,
                "reachable_nodes": context.reachable_nodes,
            }

            from app.models.instance import Instance
            from sqlalchemy import select

            async with async_session_factory() as db:
                result = await db.execute(
                    select(Instance).where(
                        Instance.id == instance_id,
                        Instance.deleted_at.is_(None),
                    )
                )
                inst = result.scalar_one_or_none()
                if inst:
                    env_vars = json.loads(inst.env_vars or "{}")
                    env_vars["DESKCLAW_MCP_CONFIG"] = json.dumps(mcp_config)
                    inst.env_vars = json.dumps(env_vars)
                    await db.commit()
                    logger.info("MCP config injected into env_vars for %s", instance_id)
        except Exception as e:
            logger.warning("MCPContextBridge.inject_context failed: %s", e)

    async def remove_context(
        self,
        instance_id: str,
        workspace_id: str,
    ) -> None:
        try:
            from app.core.deps import async_session_factory

            from app.models.instance import Instance
            from sqlalchemy import select

            async with async_session_factory() as db:
                result = await db.execute(
                    select(Instance).where(
                        Instance.id == instance_id,
                        Instance.deleted_at.is_(None),
                    )
                )
                inst = result.scalar_one_or_none()
                if inst:
                    env_vars = json.loads(inst.env_vars or "{}")
                    env_vars.pop("DESKCLAW_MCP_CONFIG", None)
                    inst.env_vars = json.dumps(env_vars)
                    await db.commit()
        except Exception as e:
            logger.warning("MCPContextBridge.remove_context failed: %s", e)
