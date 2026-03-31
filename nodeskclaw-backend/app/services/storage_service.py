"""File storage service with S3-compatible object storage and local filesystem backends.

S3 is used when S3_ENDPOINT + S3_BUCKET are configured.
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

import boto3
from botocore.config import Config as BotoConfig

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def _use_s3() -> bool:
    return bool(settings.S3_ENDPOINT and settings.S3_BUCKET)


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


# ── S3 backend ──────────────────────────────────────────

def _get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
        )
    return _client


def _s3_upload(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    client = _get_s3_client()
    prefix = settings.S3_KEY_PREFIX.strip("/")
    base = f"workspace-files/{workspace_id}/{uuid.uuid4().hex}/{filename}"
    key = f"{prefix}/{base}" if prefix else base
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=file_content,
        ContentType=content_type,
    )
    return key


def _s3_presigned_url(key: str, expires: int = 3600) -> str:
    client = _get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def _s3_download(key: str) -> bytes:
    client = _get_s3_client()
    resp = client.get_object(Bucket=settings.S3_BUCKET, Key=key)
    return resp["Body"].read()


def _s3_delete(key: str) -> None:
    client = _get_s3_client()
    client.delete_object(Bucket=settings.S3_BUCKET, Key=key)


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
    if _use_s3():
        return await asyncio.to_thread(_s3_upload, file_content, filename, content_type, workspace_id)
    return await asyncio.to_thread(_local_upload, file_content, filename, content_type, workspace_id)


async def get_presigned_url(key: str, expires: int = 3600) -> str:
    if _use_s3():
        return await asyncio.to_thread(_s3_presigned_url, key, expires)
    return _local_presigned_url(key, expires)


async def download_file(key: str) -> bytes:
    if _use_s3():
        return await asyncio.to_thread(_s3_download, key)
    return await asyncio.to_thread(_local_download, key)


async def delete_file(key: str) -> None:
    if _use_s3():
        await asyncio.to_thread(_s3_delete, key)
    else:
        await asyncio.to_thread(_local_delete, key)
