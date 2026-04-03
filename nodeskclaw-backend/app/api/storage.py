"""Storage management endpoints: list available StorageClasses from K8s cluster."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import get_current_user
from app.models.cluster import Cluster
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.config_service import get_config
from app.services.runtime.registries.compute_registry import require_k8s_client

logger = logging.getLogger(__name__)

router = APIRouter()


class StorageClassInfo(BaseModel):
    """StorageClass 摘要信息。"""
    name: str
    provisioner: str
    reclaim_policy: str | None = None
    allow_volume_expansion: bool = False
    is_default: bool = False
    enabled: bool = False  # 是否被管理员启用（在 NoDeskClaw 允许列表中）


async def _resolve_storage_cluster(
    db: AsyncSession, cluster_id: str | None, org_id: str,
) -> Cluster | None:
    """解析 StorageClass 查询目标集群。"""
    filters = [
        Cluster.org_id == org_id,
        Cluster.status == "connected",
        Cluster.compute_provider == "k8s",
        Cluster.deleted_at.is_(None),
    ]
    if cluster_id:
        result = await db.execute(select(Cluster).where(*filters, Cluster.id == cluster_id))
        cluster = result.scalar_one_or_none()
        if not cluster:
            raise NotFoundError("集群不存在", "errors.cluster.not_found")
        return cluster

    result = await db.execute(
        select(Cluster).where(*filters).order_by(Cluster.created_at.asc(), Cluster.id.asc())
    )
    clusters = result.scalars().all()
    if len(clusters) > 1:
        raise BadRequestError("请先选择集群", "errors.cluster.id_required")
    return clusters[0] if clusters else None


async def _fetch_all_storage_classes(
    db: AsyncSession, cluster_id: str | None, org_id: str,
) -> list[StorageClassInfo]:
    """从指定已连接集群获取全部 StorageClass。"""
    cluster = await _resolve_storage_cluster(db, cluster_id, org_id)
    if not cluster:
        return []

    try:
        from kubernetes_asyncio.client import StorageV1Api

        k8s = await require_k8s_client(cluster)
        storage_api = StorageV1Api(k8s.core.api_client)
        sc_list = await storage_api.list_storage_class()

        # 读取管理员启用列表
        allowed_raw = await get_config("allowed_storage_classes", db)
        allowed_names: set[str] = set()
        if allowed_raw:
            try:
                allowed_names = set(json.loads(allowed_raw))
            except (json.JSONDecodeError, TypeError):
                pass

        items: list[StorageClassInfo] = []
        for sc in sc_list.items:
            ann = sc.metadata.annotations or {}
            is_default = ann.get("storageclass.kubernetes.io/is-default-class") == "true"
            items.append(StorageClassInfo(
                name=sc.metadata.name,
                provisioner=sc.provisioner or "",
                reclaim_policy=sc.reclaim_policy,
                allow_volume_expansion=sc.allow_volume_expansion or False,
                is_default=is_default,
                enabled=sc.metadata.name in allowed_names,
            ))
        return items
    except Exception:
        logger.exception("获取 StorageClass 列表失败")
        return []


@router.get("", response_model=ApiResponse[list[StorageClassInfo]])
async def list_storage_classes(
    scope: str = Query("allowed", description="allowed=仅启用的, all=全部"),
    cluster_id: str | None = Query(None, description="目标集群 ID"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    org_ctx=Depends(get_current_org),
):
    """获取 StorageClass 列表。

    - scope=allowed（默认）: 仅返回管理员启用的 SC（部署页使用）
    - scope=all: 返回集群中全部 SC 并标记启用状态（设置页使用）
    """
    _current_user, org = org_ctx
    all_scs = await _fetch_all_storage_classes(db, cluster_id, org.id)

    if scope == "all":
        return ApiResponse(data=all_scs)

    # 只返回 enabled=True 的
    enabled_scs = [sc for sc in all_scs if sc.enabled]
    return ApiResponse(data=enabled_scs)
