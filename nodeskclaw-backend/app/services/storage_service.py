"""File storage service with TOS (Volcengine Object Storage) and local filesystem backends.

TOS is used when TOS_ENDPOINT + TOS_BUCKET are configured.
Otherwise, falls back to local filesystem storage automatically.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time
import uuid
from pathlib import Path

import tos

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: tos.TosClientV2 | None = None


def _use_tos() -> bool:
    return bool(settings.TOS_ENDPOINT and settings.TOS_BUCKET)


def is_configured() -> bool:
    return True


def _get_local_dir() -> Path:
    if settings.LOCAL_STORAGE_DIR:
        return Path(settings.LOCAL_STORAGE_DIR)
    docker_data = os.environ.get("DOCKER_DATA_DIR")
    if docker_data:
        return Path(docker_data) / "shared-files"
    return Path.home() / ".nodeskclaw" / "shared-files"


def _sign_url(key: str, expires_at: int) -> str:
    payload = f"{key}{expires_at}"
    sig = hmac.new(
        settings.JWT_SECRET.encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()
    return sig


def verify_signature(key: str, expires_str: str, sig: str) -> bool:
    try:
        expires_at = int(expires_str)
    except (ValueError, TypeError):
        return False
    if time.time() > expires_at:
        return False
    expected = _sign_url(key, expires_at)
    return hmac.compare_digest(expected, sig)


# ── TOS backend ──────────────────────────────────────────

def _get_tos_client() -> tos.TosClientV2:
    global _client
    if _client is None:
        _client = tos.TosClientV2(
            ak=settings.TOS_ACCESS_KEY_ID,
            sk=settings.TOS_SECRET_ACCESS_KEY,
            endpoint=settings.TOS_ENDPOINT,
            region=settings.TOS_REGION,
        )
    return _client


def _tos_upload(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    client = _get_tos_client()
    prefix = settings.TOS_KEY_PREFIX.strip("/")
    base = f"workspace-files/{workspace_id}/{uuid.uuid4().hex}/{filename}"
    key = f"{prefix}/{base}" if prefix else base
    client.put_object(
        bucket=settings.TOS_BUCKET,
        key=key,
        content=file_content,
        content_type=content_type,
    )
    return key


def _tos_presigned_url(tos_key: str, expires: int = 3600) -> str:
    client = _get_tos_client()
    out = client.pre_signed_url(
        http_method=tos.HttpMethodType.Http_Method_Get,
        bucket=settings.TOS_BUCKET,
        key=tos_key,
        expires=expires,
    )
    return out.signed_url


def _tos_download(tos_key: str) -> bytes:
    client = _get_tos_client()
    resp = client.get_object(bucket=settings.TOS_BUCKET, key=tos_key)
    return resp.read()


def _tos_delete(tos_key: str) -> None:
    client = _get_tos_client()
    client.delete_object(bucket=settings.TOS_BUCKET, key=tos_key)


# ── Local filesystem backend ─────────────────────────────

def _local_upload(file_content: bytes, filename: str, _content_type: str, workspace_id: str) -> str:
    base = f"workspace-files/{workspace_id}/{uuid.uuid4().hex}/{filename}"
    local_dir = _get_local_dir()
    file_path = local_dir / base
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(file_content)
    return base


def _local_presigned_url(key: str, expires: int = 3600) -> str:
    expires_at = int(time.time()) + expires
    sig = _sign_url(key, expires_at)
    base_url = settings.AGENT_API_BASE_URL.rstrip("/")
    return f"{base_url}/files/local/{key}?expires={expires_at}&sig={sig}"


def _local_download(key: str) -> bytes:
    file_path = _get_local_dir() / key
    return file_path.read_bytes()


def _local_delete(key: str) -> None:
    file_path = _get_local_dir() / key
    try:
        file_path.unlink()
    except FileNotFoundError:
        pass


# ── Public async API ─────────────────────────────────────

async def upload_file(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    if _use_tos():
        return await asyncio.to_thread(_tos_upload, file_content, filename, content_type, workspace_id)
    return await asyncio.to_thread(_local_upload, file_content, filename, content_type, workspace_id)


async def get_presigned_url(tos_key: str, expires: int = 3600) -> str:
    if _use_tos():
        return await asyncio.to_thread(_tos_presigned_url, tos_key, expires)
    return _local_presigned_url(tos_key, expires)


async def download_file(key: str) -> bytes:
    if _use_tos():
        return await asyncio.to_thread(_tos_download, key)
    return await asyncio.to_thread(_local_download, key)


async def delete_file(tos_key: str) -> None:
    if _use_tos():
        await asyncio.to_thread(_tos_delete, tos_key)
    else:
        await asyncio.to_thread(_local_delete, tos_key)
