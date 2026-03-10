"""RoutingMiddleware — generates a DeliveryPlan by invoking the topology-based corridor router."""

from __future__ import annotations

import logging

from app.services.runtime.messaging.delivery_plan import DeliveryPlan, DeliveryTarget
from app.services.runtime.messaging.pipeline import MessageMiddleware, NextFn, PipelineContext

logger = logging.getLogger(__name__)


async def _resolve_targets_by_name(
    names: list[str], workspace_id: str, db,
) -> list[DeliveryTarget]:
    """Resolve target names (display_name or node_id) to DeliveryTarget objects."""
    from app.models.base import not_deleted
    from app.models.node_card import NodeCard
    from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY
    from sqlalchemy import or_, select

    targets: list[DeliveryTarget] = []
    for name in names:
        stmt = select(NodeCard).where(
            NodeCard.workspace_id == workspace_id,
            not_deleted(NodeCard),
            or_(NodeCard.name == name, NodeCard.node_id == name),
        )
        result = await db.execute(stmt)
        card = result.scalar_one_or_none()
        if card is None:
            logger.warning("Routing: target '%s' not found in workspace %s", name, workspace_id)
            continue

        type_spec = NODE_TYPE_REGISTRY.get(card.node_type)
        transport = type_spec.transport if type_spec else ""
        targets.append(DeliveryTarget(
            node_id=card.node_id,
            node_type=card.node_type,
            transport=transport or "",
        ))
    return targets


async def _resolve_broadcast(workspace_id: str, db) -> list[DeliveryTarget]:
    """BFS from blackboard (0,0) to find all reachable endpoints via corridor topology."""
    from app.services.corridor_router import get_blackboard_audience, has_any_connections
    from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY

    has_topo = await has_any_connections(workspace_id, db)

    if has_topo:
        endpoints = await get_blackboard_audience(workspace_id, db)
        targets: list[DeliveryTarget] = []
        for ep in endpoints:
            type_spec = NODE_TYPE_REGISTRY.get(ep.endpoint_type)
            transport = type_spec.transport if type_spec else ""
            targets.append(DeliveryTarget(
                node_id=ep.entity_id,
                node_type=ep.endpoint_type,
                transport=transport or "",
            ))
        return targets

    from app.models.base import not_deleted
    from app.models.node_card import NodeCard
    from sqlalchemy import select

    stmt = select(NodeCard).where(
        NodeCard.workspace_id == workspace_id,
        not_deleted(NodeCard),
        NodeCard.node_type.in_(["agent", "human"]),
    )
    result = await db.execute(stmt)
    targets = []
    for card in result.scalars().all():
        type_spec = NODE_TYPE_REGISTRY.get(card.node_type)
        transport = type_spec.transport if type_spec else ""
        targets.append(DeliveryTarget(
            node_id=card.node_id,
            node_type=card.node_type,
            transport=transport or "",
        ))
    return targets


def _simple_token_overlap(text_a: str, text_b: str) -> float:
    """Lightweight token-overlap similarity (no external embeddings needed)."""
    if not text_a or not text_b:
        return 0.0
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / (len(tokens_a | tokens_b) or 1)


async def _apply_semantic_scoring(
    targets: list[DeliveryTarget],
    content: str,
    workspace_id: str,
    db,
) -> list[DeliveryTarget]:
    """Score and sort targets by relevance using topology + semantic similarity."""
    if not content or len(targets) <= 1:
        return targets

    from app.models.base import not_deleted
    from app.models.node_card import NodeCard
    from sqlalchemy import select

    scored: list[tuple[float, DeliveryTarget]] = []
    for target in targets:
        result = await db.execute(
            select(NodeCard.description, NodeCard.tags).where(
                NodeCard.node_id == target.node_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            )
        )
        row = result.first()
        description = (row[0] or "") if row else ""
        tags = (row[1] or []) if row else []
        tag_text = " ".join(str(t) for t in tags)
        node_text = f"{description} {tag_text}".strip()

        semantic_score = _simple_token_overlap(content, node_text)
        topology_score = 1.0
        relevance = topology_score * 0.6 + semantic_score * 0.4
        scored.append((relevance, target))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored]


class RoutingMiddleware(MessageMiddleware):
    async def process(self, ctx: PipelineContext, next_fn: NextFn) -> None:
        data = ctx.envelope.data
        if data is None:
            await next_fn(ctx)
            return

        db = ctx.db

        if data.routing.targets:
            mode = "unicast" if len(data.routing.targets) == 1 else "multicast"
            resolved: list[DeliveryTarget] = []
            if db is not None:
                resolved = await _resolve_targets_by_name(
                    data.routing.targets, ctx.workspace_id, db,
                )
            ctx.delivery_plan = DeliveryPlan(
                targets=data.routing.targets,
                resolved_targets=resolved,
                mode=mode,
                workspace_id=ctx.workspace_id,
            )
        else:
            from app.services.runtime.route_cache import route_table

            resolved = route_table.get(ctx.workspace_id)
            if resolved is None and db is not None:
                resolved = await _resolve_broadcast(ctx.workspace_id, db)
                route_table.put(ctx.workspace_id, resolved)
            resolved = resolved or []

            sender_id = data.sender.instance_id or data.sender.id
            resolved = [t for t in resolved if t.node_id != sender_id]

            ctx.delivery_plan = DeliveryPlan(
                targets=[],
                resolved_targets=resolved,
                mode="broadcast",
                workspace_id=ctx.workspace_id,
            )

        if ctx.delivery_plan.resolved_targets and db is not None:
            ctx.delivery_plan.resolved_targets = await _apply_semantic_scoring(
                ctx.delivery_plan.resolved_targets,
                ctx.envelope.data.content if ctx.envelope.data else "",
                ctx.workspace_id,
                db,
            )

        logger.debug(
            "Routing: mode=%s resolved=%d targets for envelope %s",
            ctx.delivery_plan.mode,
            len(ctx.delivery_plan.resolved_targets),
            ctx.envelope.id,
        )

        await next_fn(ctx)
