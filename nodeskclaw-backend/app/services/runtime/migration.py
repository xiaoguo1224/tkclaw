"""Data migration: old tables -> node_cards.

Phase 9.1: Migrate workspace_agents, human_hexes, corridor_hexes, and blackboard
data into the unified node_cards table. Safe to run multiple times (idempotent).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.node_card import NodeCard

logger = logging.getLogger(__name__)


async def migrate_workspace_agents(db: AsyncSession) -> int:
    """Migrate WorkspaceAgent records to NodeCard(node_type='agent')."""
    from app.models.workspace_agent import WorkspaceAgent

    result = await db.execute(
        select(WorkspaceAgent).where(not_deleted(WorkspaceAgent))
    )
    agents = result.scalars().all()
    migrated = 0

    for wa in agents:
        existing = await db.execute(
            select(NodeCard).where(
                NodeCard.node_id == wa.instance_id,
                NodeCard.workspace_id == wa.workspace_id,
                not_deleted(NodeCard),
            )
        )
        if existing.scalar_one_or_none():
            continue

        card = NodeCard(
            node_type="agent",
            node_id=wa.instance_id,
            workspace_id=wa.workspace_id,
            hex_q=wa.hex_q,
            hex_r=wa.hex_r,
            name=wa.display_name or "",
            status="active",
            tags=[],
            metadata_={
                "display_name": wa.display_name,
                "theme_color": wa.theme_color,
            },
        )
        db.add(card)
        migrated += 1

    if migrated:
        await db.flush()
    logger.info("Migrated %d workspace_agents -> node_cards", migrated)
    return migrated


async def migrate_corridor_hexes(db: AsyncSession) -> int:
    """Migrate CorridorHex records to NodeCard(node_type='corridor')."""
    from app.models.corridor import CorridorHex

    result = await db.execute(
        select(CorridorHex).where(not_deleted(CorridorHex))
    )
    corridors = result.scalars().all()
    migrated = 0

    for ch in corridors:
        existing = await db.execute(
            select(NodeCard).where(
                NodeCard.node_type == "corridor",
                NodeCard.workspace_id == ch.workspace_id,
                NodeCard.hex_q == ch.hex_q,
                NodeCard.hex_r == ch.hex_r,
                not_deleted(NodeCard),
            )
        )
        if existing.scalar_one_or_none():
            continue

        card = NodeCard(
            node_type="corridor",
            node_id=str(ch.id),
            workspace_id=ch.workspace_id,
            hex_q=ch.hex_q,
            hex_r=ch.hex_r,
            name=ch.display_name or "",
            status="active",
            tags=[],
            metadata_={},
        )
        db.add(card)
        migrated += 1

    if migrated:
        await db.flush()
    logger.info("Migrated %d corridor_hexes -> node_cards", migrated)
    return migrated


async def migrate_human_hexes(db: AsyncSession) -> int:
    """Migrate HumanHex records to NodeCard(node_type='human')."""
    from app.models.corridor import HumanHex

    result = await db.execute(
        select(HumanHex).where(not_deleted(HumanHex))
    )
    humans = result.scalars().all()
    migrated = 0

    for hh in humans:
        existing = await db.execute(
            select(NodeCard).where(
                NodeCard.node_type == "human",
                NodeCard.workspace_id == hh.workspace_id,
                NodeCard.hex_q == hh.hex_q,
                NodeCard.hex_r == hh.hex_r,
                not_deleted(NodeCard),
            )
        )
        if existing.scalar_one_or_none():
            continue

        card = NodeCard(
            node_type="human",
            node_id=hh.user_id or str(hh.id),
            workspace_id=hh.workspace_id,
            hex_q=hh.hex_q,
            hex_r=hh.hex_r,
            name=hh.display_name or "",
            status="active",
            tags=[],
            metadata_={
                "user_id": hh.user_id,
                "display_color": hh.display_color,
                "channel_type": hh.channel_type,
                "channel_config": hh.channel_config,
            },
        )
        db.add(card)
        migrated += 1

    if migrated:
        await db.flush()
    logger.info("Migrated %d human_hexes -> node_cards", migrated)
    return migrated


async def migrate_blackboards(db: AsyncSession) -> int:
    """Migrate Blackboard records to NodeCard(node_type='blackboard')."""
    from app.models.blackboard import Blackboard

    result = await db.execute(
        select(Blackboard).where(not_deleted(Blackboard))
    )
    boards = result.scalars().all()
    migrated = 0

    for bb in boards:
        existing = await db.execute(
            select(NodeCard).where(
                NodeCard.node_type == "blackboard",
                NodeCard.workspace_id == bb.workspace_id,
                NodeCard.hex_q == 0,
                NodeCard.hex_r == 0,
                not_deleted(NodeCard),
            )
        )
        if existing.scalar_one_or_none():
            continue

        card = NodeCard(
            node_type="blackboard",
            node_id=str(bb.id),
            workspace_id=bb.workspace_id,
            hex_q=0,
            hex_r=0,
            name="blackboard",
            status="active",
            tags=[],
            metadata_={
                "content": bb.content,
                "auto_summary": bb.auto_summary,
                "manual_notes": bb.manual_notes,
            },
        )
        db.add(card)
        migrated += 1

    if migrated:
        await db.flush()
    logger.info("Migrated %d blackboards -> node_cards", migrated)
    return migrated


async def create_builtin_node_type_records(db: AsyncSession) -> int:
    """Create node_type_definitions records for built-in types."""
    from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY

    await NODE_TYPE_REGISTRY.sync_to_db(db)
    await db.flush()
    count = len(NODE_TYPE_REGISTRY.all_types())
    logger.info("Synced %d node_type_definitions to DB", count)
    return count


async def run_full_migration(db: AsyncSession) -> dict[str, int]:
    """Run all migration steps. Safe to call multiple times."""
    results: dict[str, int] = {}

    results["node_type_definitions"] = await create_builtin_node_type_records(db)
    results["workspace_agents"] = await migrate_workspace_agents(db)
    results["corridor_hexes"] = await migrate_corridor_hexes(db)
    results["human_hexes"] = await migrate_human_hexes(db)
    results["blackboards"] = await migrate_blackboards(db)

    await db.commit()
    logger.info("Full migration complete: %s", results)
    return results
