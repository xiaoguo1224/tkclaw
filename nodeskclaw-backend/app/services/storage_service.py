"""TOS (Volcengine Object Storage) service for file uploads."""

import asyncio
import uuid

import tos

from app.core.config import settings

_client: tos.TosClientV2 | None = None


def is_configured() -> bool:
    return bool(settings.TOS_ENDPOINT and settings.TOS_BUCKET)


def _get_client() -> tos.TosClientV2:
    global _client
    if _client is None:
        if not is_configured():
            raise RuntimeError("TOS 对象存储未配置")
        _client = tos.TosClientV2(
            ak=settings.TOS_ACCESS_KEY_ID,
            sk=settings.TOS_SECRET_ACCESS_KEY,
            endpoint=settings.TOS_ENDPOINT,
            region=settings.TOS_REGION,
        )
    return _client


def _upload_file_sync(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    client = _get_client()
    key = f"workspace-files/{workspace_id}/{uuid.uuid4().hex}/{filename}"
    client.put_object(
        bucket=settings.TOS_BUCKET,
        key=key,
        content=file_content,
        content_type=content_type,
    )
    return key


def _get_presigned_url_sync(tos_key: str, expires: int = 3600) -> str:
    client = _get_client()
    out = client.pre_signed_url(
        http_method=tos.HttpMethodType.Http_Method_Get,
        bucket=settings.TOS_BUCKET,
        key=tos_key,
        expires=expires,
    )
    return out.signed_url


def _delete_file_sync(tos_key: str) -> None:
    client = _get_client()
    client.delete_object(bucket=settings.TOS_BUCKET, key=tos_key)


async def upload_file(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    return await asyncio.to_thread(_upload_file_sync, file_content, filename, content_type, workspace_id)


async def get_presigned_url(tos_key: str, expires: int = 3600) -> str:
    return await asyncio.to_thread(_get_presigned_url_sync, tos_key, expires)


async def delete_file(tos_key: str) -> None:
    await asyncio.to_thread(_delete_file_sync, tos_key)
