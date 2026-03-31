"""MCP Server management API — CRUD for instance-level MCP configurations."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.instance_mcp_server import InstanceMcpServer
from app.schemas.mcp import McpServerCreate, McpServerInfo, McpServerUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _mcp_http_error(status_code: int, error_code: int, message_key: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message_key": message_key,
            "message": message,
        },
    )


async def _get_instance(instance_id: str, org_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.org_id == org_id,
            not_deleted(Instance),
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise _mcp_http_error(404, 40470, "errors.instance.not_found", "实例不存在")
    return instance


async def _get_mcp_server(instance_id: str, mcp_id: str, db: AsyncSession) -> InstanceMcpServer:
    result = await db.execute(
        select(InstanceMcpServer).where(
            InstanceMcpServer.id == mcp_id,
            InstanceMcpServer.instance_id == instance_id,
            not_deleted(InstanceMcpServer),
        )
    )
    mcp = result.scalar_one_or_none()
    if not mcp:
        raise _mcp_http_error(404, 40471, "errors.mcp.server_not_found", "MCP 服务不存在")
    return mcp


def _mcp_to_info(m: InstanceMcpServer) -> dict:
    return McpServerInfo(
        id=m.id, instance_id=m.instance_id, name=m.name,
        transport=m.transport, command=m.command, url=m.url,
        args=m.args, env=m.env, is_active=m.is_active,
        source=m.source, source_gene_id=m.source_gene_id,
        created_at=m.created_at,
    ).model_dump()


@router.get("/{instance_id}/mcp-servers")
async def list_mcp_servers(
    instance_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_instance(instance_id, org.id, db)
    result = await db.execute(
        select(InstanceMcpServer).where(
            InstanceMcpServer.instance_id == instance_id,
            not_deleted(InstanceMcpServer),
        )
    )
    items = [_mcp_to_info(m) for m in result.scalars().all()]
    return _ok(items)


@router.post("/{instance_id}/mcp-servers")
async def create_mcp_server(
    instance_id: str, body: McpServerCreate,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_instance(instance_id, org.id, db)

    mcp = InstanceMcpServer(
        id=str(uuid.uuid4()),
        instance_id=instance_id,
        name=body.name,
        transport=body.transport,
        command=body.command,
        url=body.url,
        args=body.args,
        env=body.env,
    )
    db.add(mcp)
    await db.commit()
    await db.refresh(mcp)
    return _ok(_mcp_to_info(mcp))


@router.put("/{instance_id}/mcp-servers/{mcp_id}")
async def update_mcp_server(
    instance_id: str, mcp_id: str, body: McpServerUpdate,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_instance(instance_id, org.id, db)
    mcp = await _get_mcp_server(instance_id, mcp_id, db)
    for field in ("name", "transport", "command", "url", "args", "env", "is_active"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(mcp, field, val)
    await db.commit()
    return _ok(_mcp_to_info(mcp))


@router.delete("/{instance_id}/mcp-servers/{mcp_id}")
async def delete_mcp_server(
    instance_id: str, mcp_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_instance(instance_id, org.id, db)
    mcp = await _get_mcp_server(instance_id, mcp_id, db)
    mcp.soft_delete()
    await db.commit()
    return _ok(message="deleted")
