"""SystemPromptBridge — injects workspace context into the LLM system message."""

from __future__ import annotations

import logging

from app.services.runtime.context_bridges.base import WorkspaceContext

logger = logging.getLogger(__name__)


class SystemPromptBridge:
    bridge_id = "system_prompt"

    async def inject_context(
        self,
        instance_id: str,
        workspace_id: str,
        context: WorkspaceContext,
    ) -> None:
        logger.info(
            "SystemPromptBridge.inject_context: instance=%s workspace=%s",
            instance_id, workspace_id,
        )
        prompt = self.build_system_prompt(context)
        try:
            from app.core.deps import async_session_factory

            async with async_session_factory() as db:
                from app.services import workspace_message_service as msg_service

                await msg_service.record_message(
                    db,
                    workspace_id=workspace_id,
                    sender_type="system",
                    sender_id="context_bridge",
                    sender_name="System",
                    content=prompt,
                    message_type="system_prompt",
                )
                logger.info(
                    "System prompt injected for instance %s (%d chars)",
                    instance_id, len(prompt),
                )
        except Exception as e:
            logger.warning("SystemPromptBridge.inject_context failed: %s", e)

    async def remove_context(
        self,
        instance_id: str,
        workspace_id: str,
    ) -> None:
        pass

    def build_system_prompt(self, context: WorkspaceContext) -> str:
        """Build a system prompt string from workspace context."""
        parts = [
            f"你是 {context.agent_identity}，在智能助理「{context.workspace_name}」中工作。",
        ]

        if context.team:
            team_lines = []
            for member in context.team:
                team_lines.append(f"- [{member.get('type', 'unknown')}] {member.get('name', '?')}")
            parts.append("\n团队成员:\n" + "\n".join(team_lines))

        if context.recent_messages:
            msg_lines = []
            for msg in context.recent_messages[-20:]:
                msg_lines.append(f"[{msg.get('sender_name', '?')}]: {msg.get('content', '')[:200]}")
            parts.append("\n最近消息:\n" + "\n".join(msg_lines))

        return "\n\n".join(parts)
