"""System ingestion — wraps system-generated messages into MessageEnvelopes."""

from __future__ import annotations

from app.services.runtime.messaging.envelope import (
    IntentType,
    MessageData,
    MessageEnvelope,
    MessageRouting,
    MessageSender,
    Priority,
    SenderType,
)


def build_system_envelope(
    *,
    workspace_id: str,
    content: str,
    source_label: str = "system",
    targets: list[str] | None = None,
    mention_targets: list[str] | None = None,
) -> MessageEnvelope:
    routing_targets = targets or []
    resolved_mention_targets = mention_targets or []
    mode = "broadcast"
    if routing_targets:
        mode = "unicast" if len(routing_targets) == 1 else "multicast"

    return MessageEnvelope(
        source=f"system/{source_label}",
        type="deskclaw.msg.v1.notify",
        workspaceid=workspace_id,
        data=MessageData(
            sender=MessageSender(
                id="system",
                type=SenderType.SYSTEM,
                name="System",
            ),
            intent=IntentType.NOTIFY,
            content=content,
            priority=Priority.NORMAL,
            extensions={"mention_targets": resolved_mention_targets},
            routing=MessageRouting(mode=mode, targets=routing_targets),
        ),
    )
