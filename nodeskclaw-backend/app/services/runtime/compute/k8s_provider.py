"""K8sComputeProvider — manages agent instances as Kubernetes Deployments."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.runtime.compute.base import (
    ComputeHandle,
    InstanceComputeConfig,
)

if TYPE_CHECKING:
    from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)


class K8sComputeProvider:
    """Kubernetes-based compute provider.

    Delegates to the existing DeploymentAdapter (CE/EE) for K8s-specific
    differences (namespace naming, Ingress proxy, NetworkPolicy, etc.).
    """

    provider_id = "k8s"

    async def get_k8s_client(self, cluster) -> "K8sClient":
        from app.services.k8s.client_manager import k8s_manager
        from app.services.k8s.k8s_client import K8sClient

        if not cluster.credentials_encrypted:
            raise ValueError(f"集群 {cluster.name} 没有有效的连接凭证")
        api_client = await k8s_manager.get_or_create(
            cluster.id, cluster.credentials_encrypted,
        )
        return K8sClient(api_client)

    async def create_instance(
        self, config: InstanceComputeConfig, **kwargs,
    ) -> ComputeHandle:
        logger.info(
            "K8sComputeProvider.create_instance: %s in %s",
            config.instance_id, config.namespace,
        )
        db = kwargs.get("db")
        if db is None:
            return ComputeHandle(
                provider=self.provider_id,
                instance_id=config.instance_id,
                namespace=config.namespace,
                status="creating",
            )

        try:
            from app.services.deploy_service import execute_deploy_pipeline

            await execute_deploy_pipeline(config.instance_id, db)

            from app.models.instance import Instance
            from sqlalchemy import select
            result = await db.execute(
                select(Instance).where(
                    Instance.id == config.instance_id,
                    Instance.deleted_at.is_(None),
                )
            )
            inst = result.scalar_one_or_none()
            endpoint = f"https://{inst.ingress_domain}" if inst and inst.ingress_domain else ""
            status = inst.status if inst else "creating"

            return ComputeHandle(
                provider=self.provider_id,
                instance_id=config.instance_id,
                namespace=config.namespace,
                endpoint=endpoint,
                status=status,
            )
        except Exception as e:
            logger.error("K8s create_instance failed: %s", e)
            return ComputeHandle(
                provider=self.provider_id,
                instance_id=config.instance_id,
                namespace=config.namespace,
                status="failed",
                extra={"error": str(e)},
            )

    async def destroy_instance(self, handle: ComputeHandle, **kwargs) -> None:
        logger.info(
            "K8sComputeProvider.destroy_instance: %s in %s",
            handle.instance_id, handle.namespace,
        )
        db = kwargs.get("db")
        if db is None:
            return
        try:
            from app.services.instance_service import delete_instance
            await delete_instance(handle.instance_id, db)
        except Exception as e:
            logger.error("K8s destroy_instance failed: %s", e)

    async def get_status(self, handle: ComputeHandle) -> str:
        cluster_id = (handle.extra or {}).get("cluster_id")
        creds = (handle.extra or {}).get("credentials_encrypted")
        if not cluster_id or not creds:
            return handle.status
        try:
            from app.services.k8s.client_manager import k8s_manager
            from app.services.k8s.k8s_client import K8sClient

            api_client = await k8s_manager.get_or_create(cluster_id, creds)
            k8s = K8sClient(api_client)
            pods = await k8s.list_namespaced_pod(handle.namespace)
            for pod in pods.items:
                if handle.instance_id in (pod.metadata.name or ""):
                    return pod.status.phase.lower() if pod.status.phase else "unknown"
        except Exception as e:
            logger.warning("K8s get_status failed: %s", e)
        return handle.status

    async def get_endpoint(self, handle: ComputeHandle) -> str:
        return handle.endpoint

    async def get_logs(self, handle: ComputeHandle, *, tail: int = 50) -> str:
        cluster_id = (handle.extra or {}).get("cluster_id")
        creds = (handle.extra or {}).get("credentials_encrypted")
        if not cluster_id or not creds:
            return ""
        try:
            from app.services.k8s.client_manager import k8s_manager
            from app.services.k8s.k8s_client import K8sClient

            api_client = await k8s_manager.get_or_create(cluster_id, creds)
            k8s = K8sClient(api_client)
            log = await k8s.read_namespaced_pod_log(
                handle.instance_id, handle.namespace, tail_lines=tail,
            )
            return log or ""
        except Exception as e:
            logger.warning("K8s get_logs failed: %s", e)
        return ""

    async def update_instance(
        self, handle: ComputeHandle, config: InstanceComputeConfig,
    ) -> ComputeHandle:
        logger.info(
            "K8sComputeProvider.update_instance: %s in %s (rolling update)",
            handle.instance_id, handle.namespace,
        )
        cluster_id = (handle.extra or {}).get("cluster_id")
        creds = (handle.extra or {}).get("credentials_encrypted")
        if cluster_id and creds:
            try:
                from app.services.k8s.client_manager import k8s_manager
                from app.services.k8s.k8s_client import K8sClient

                api_client = await k8s_manager.get_or_create(cluster_id, creds)
                k8s = K8sClient(api_client)
                image = config.image if hasattr(config, "image") else ""
                if image:
                    deploy_name = f"deskclaw-{handle.instance_id}"
                    body = {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [{
                                        "name": "deskclaw",
                                        "image": image,
                                    }]
                                }
                            }
                        }
                    }
                    await k8s.patch_namespaced_deployment(
                        deploy_name, handle.namespace, body,
                    )
                    logger.info("Rolling update triggered for %s", handle.instance_id)
            except Exception as e:
                logger.error("K8s update_instance failed: %s", e)

        return ComputeHandle(
            provider=self.provider_id,
            instance_id=handle.instance_id,
            namespace=handle.namespace,
            endpoint=handle.endpoint,
            status="updating",
        )

    async def health_check(self, handle: ComputeHandle) -> dict:
        from app.services.tunnel import tunnel_adapter
        if handle.instance_id in tunnel_adapter.connected_instances:
            return {"healthy": True, "detail": "tunnel connected"}
        return {"healthy": False, "detail": "tunnel not connected"}
