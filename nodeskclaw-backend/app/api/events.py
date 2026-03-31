"""K8s events endpoints: REST listing and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.exceptions import NotFoundError
from app.core.security import get_current_user
from app.models.cluster import Cluster
from app.models.user import User
from app.services.runtime.registries.compute_registry import require_k8s_client

logger = logging.getLogger(__name__)

router = APIRouter()

WATCH_TIMEOUT_SECONDS = 1800
HEARTBEAT_INTERVAL_SECONDS = 15


def _map_k8s_event(obj, event_type: str = "OBJECT") -> dict:
    """Map a K8s CoreV1Event object to a flat dict."""
    return {
        "type": event_type,
        "event_type": obj.type or "Normal",
        "reason": obj.reason,
        "message": obj.message,
        "involved": obj.involved_object.name if obj.involved_object else None,
        "involved_kind": obj.involved_object.kind if obj.involved_object else None,
        "namespace": obj.metadata.namespace,
        "count": obj.count,
        "last_timestamp": obj.last_timestamp.isoformat() if obj.last_timestamp else None,
        "first_timestamp": (
            obj.event_time.isoformat() if obj.event_time else (
                obj.first_timestamp.isoformat() if obj.first_timestamp else None
            )
        ),
    }


async def _get_cluster(cluster_id: str, db: AsyncSession) -> Cluster:
    result = await db.execute(
        select(Cluster).where(Cluster.id == cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")
    return cluster


@router.get("/recent")
async def events_recent(
    cluster_id: str = Query(..., description="集群 ID"),
    namespace: str = Query("", description="命名空间，留空则查询所有"),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """REST: 返回 K8s 最近事件列表。非 K8s 集群返回空列表。"""
    cluster = await _get_cluster(cluster_id, db)

    if not cluster.is_k8s:
        return JSONResponse({"data": []})

    k8s = await require_k8s_client(cluster)

    if namespace:
        resp = await k8s.core.list_namespaced_event(namespace)
    else:
        resp = await k8s.core.list_event_for_all_namespaces()

    items = [_map_k8s_event(obj) for obj in resp.items]
    items.sort(key=lambda e: e["last_timestamp"] or "", reverse=True)

    return JSONResponse({"data": items[:limit]})


@router.get("/stream")
async def events_stream(
    cluster_id: str = Query(..., description="集群 ID"),
    namespace: str = Query("", description="命名空间，留空则监听所有"),
    _current_user: User = Depends(get_current_user),
):
    """SSE 流: 实时推送 K8s 事件（deprecated，保留兼容）。"""
    from app.core.deps import async_session_factory

    async with async_session_factory() as db:
        cluster = await _get_cluster(cluster_id, db)
    k8s = await require_k8s_client(cluster)

    async def generate():
        yield ": connected\n\n"

        event_queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def watch_loop():
            try:
                while True:
                    try:
                        if namespace:
                            event_gen = k8s.watch_events(namespace)
                        else:
                            event_gen = _watch_all_events(k8s)

                        async for event in event_gen:
                            data = json.dumps(event, default=str)
                            await event_queue.put(f"event: k8s_event\ndata: {data}\n\n")
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("K8s watch 断开, 5 秒后重连: %s", e)
                        await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass
            finally:
                await event_queue.put(None)

        watch_task = asyncio.create_task(watch_loop())
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(
                        event_queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS
                    )
                    if msg is None:
                        break
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _watch_all_events(k8s: K8sClient):
    """Watch events across all namespaces."""
    from kubernetes_asyncio import watch

    w = watch.Watch()
    async for event in w.stream(
        k8s.core.list_event_for_all_namespaces,
        timeout_seconds=WATCH_TIMEOUT_SECONDS,
    ):
        yield _map_k8s_event(event["object"], event["type"])
