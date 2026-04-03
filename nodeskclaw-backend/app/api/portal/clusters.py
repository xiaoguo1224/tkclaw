"""Portal cluster endpoints — org-scoped.

router: read-only (list + detail) — always available, needed by CreateInstance in EE.
write_router: cluster management (CRUD, health, overview, test, kubeconfig) — CE-only.
"""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_current_org, get_db
from app.schemas.cluster import ClusterCreate, ClusterInfo, ClusterUpdate, ConnectionTestResult
from app.schemas.common import ApiResponse
from app.services import cluster_service
from app.services.runtime.registries.compute_registry import require_k8s_client

logger = logging.getLogger(__name__)

router = APIRouter()
write_router = APIRouter()


@router.get("", response_model=ApiResponse[list[ClusterInfo]])
async def list_clusters(
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    data = await cluster_service.list_clusters(db, org.id)
    return ApiResponse(data=data)


@router.get("/{cluster_id}", response_model=ApiResponse[ClusterInfo])
async def get_cluster(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    cluster = await cluster_service.get_cluster(cluster_id, db, org.id)
    return ApiResponse(data=ClusterInfo.model_validate(cluster))


@write_router.post("", response_model=ApiResponse[ClusterInfo])
async def create_cluster(
    body: ClusterCreate,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    current_user, org = org_ctx
    data = await cluster_service.create_cluster(body, current_user, db, org_id=org.id)
    await hooks.emit("operation_audit", action="cluster.created", target_type="cluster", target_id=data.id, actor_id=current_user.id, org_id=org.id)
    return ApiResponse(data=data)


@write_router.put("/{cluster_id}", response_model=ApiResponse[ClusterInfo])
async def update_cluster(
    cluster_id: str,
    body: ClusterUpdate,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    current_user, org = org_ctx
    data = await cluster_service.update_cluster(cluster_id, body, db, org.id)
    await hooks.emit("operation_audit", action="cluster.updated", target_type="cluster", target_id=cluster_id, actor_id=current_user.id, org_id=org.id)
    return ApiResponse(data=data)


@write_router.delete("/{cluster_id}", response_model=ApiResponse)
async def delete_cluster(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    current_user, org = org_ctx
    await cluster_service.delete_cluster(cluster_id, db, org.id)
    await hooks.emit("operation_audit", action="cluster.deleted", target_type="cluster", target_id=cluster_id, actor_id=current_user.id, org_id=org.id)
    return ApiResponse(message="集群已删除")


@write_router.get("/{cluster_id}/health", response_model=ApiResponse[dict])
async def cluster_health(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    from app.services.health_checker import get_cluster_health

    _current_user, org = org_ctx
    data = await get_cluster_health(cluster_id, db, org.id)
    return ApiResponse(data=data)


@write_router.get("/{cluster_id}/overview", response_model=ApiResponse[dict])
async def cluster_overview(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    cluster = await cluster_service.get_cluster(cluster_id, db, org.id)

    k8s = await require_k8s_client(cluster)

    summary = await k8s.get_cluster_overview()
    nodes = await k8s.list_nodes()

    storage_classes = []
    try:
        import json as _json
        from kubernetes_asyncio.client import StorageV1Api
        from app.services.config_service import get_config

        storage_api = StorageV1Api(k8s.core.api_client)
        sc_list = await storage_api.list_storage_class()

        allowed_raw = await get_config("allowed_storage_classes", db)
        allowed_names: set[str] = set()
        if allowed_raw:
            try:
                allowed_names = set(_json.loads(allowed_raw))
            except (_json.JSONDecodeError, TypeError):
                pass

        for sc in sc_list.items:
            ann = sc.metadata.annotations or {}
            is_default = ann.get("storageclass.kubernetes.io/is-default-class") == "true"
            storage_classes.append({
                "name": sc.metadata.name,
                "provisioner": sc.provisioner or "",
                "reclaim_policy": sc.reclaim_policy,
                "allow_volume_expansion": sc.allow_volume_expansion or False,
                "is_default": is_default,
                "enabled": sc.metadata.name in allowed_names,
            })
    except Exception:
        logger.warning("Failed to list StorageClasses for cluster %s", cluster_id, exc_info=True)

    ingress_classes = []
    try:
        from kubernetes_asyncio.client import NetworkingV1Api

        networking_api = NetworkingV1Api(k8s.core.api_client)
        ic_list = await networking_api.list_ingress_class()
        for ic in ic_list.items:
            ingress_classes.append({
                "name": ic.metadata.name,
                "controller": ic.spec.controller if ic.spec else "",
            })
    except Exception:
        logger.warning("Failed to list IngressClasses for cluster %s", cluster_id, exc_info=True)

    return ApiResponse(data={
        "summary": summary,
        "nodes": nodes,
        "storage_classes": storage_classes,
        "ingress_classes": ingress_classes,
    })


@write_router.post("/{cluster_id}/test", response_model=ApiResponse[ConnectionTestResult])
async def test_connection(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    data = await cluster_service.test_connection(cluster_id, db, org.id)
    return ApiResponse(data=data)


class KubeconfigBody(BaseModel):
    kubeconfig: str


@write_router.post("/{cluster_id}/kubeconfig", response_model=ApiResponse[ClusterInfo])
async def update_kubeconfig(
    cluster_id: str,
    body: KubeconfigBody,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    current_user, org = org_ctx
    data = await cluster_service.update_kubeconfig(cluster_id, body.kubeconfig, db, org.id)
    await hooks.emit("operation_audit", action="cluster.kubeconfig_updated", target_type="cluster", target_id=cluster_id, actor_id=current_user.id, org_id=org.id)
    return ApiResponse(data=data)
