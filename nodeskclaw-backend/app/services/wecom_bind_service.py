import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.user import User
from app.models.wecom_bind_session import WecomBindSession
from app.services.channel_config_service import (
    ensure_official_wecom_plugin_installed,
    ensure_wecom_plugin_config,
)
from app.services.nfs_mount import remote_fs
from app.services.runtime.config_adapter import get_config_adapter

WECOM_QR_GENERATE_URL = "https://work.weixin.qq.com/ai/qc/generate"
WECOM_QR_QUERY_URL = "https://work.weixin.qq.com/ai/qc/query_result"
WECOM_QR_PAGE_URL = "https://work.weixin.qq.com/ai/qc/gen?source=wecom-cli&scode="


def _to_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _platform_code() -> int:
    if sys.platform.startswith("darwin"):
        return 1
    if sys.platform.startswith("win"):
        return 2
    if sys.platform.startswith("linux"):
        return 3
    return 0


def _mask_bot_id(bot_id: str | None) -> str | None:
    value = (bot_id or "").strip()
    if not value:
        return None
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:4]}***{value[-2:]}"


def _json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)


async def _get_instance(instance_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", "errors.instance.not_found")
    if (instance.runtime or "openclaw") != "openclaw":
        raise BadRequestError(
            message="企业微信官方插件仅支持 OpenClaw 引擎",
            message_key="errors.wecom.openclaw_only",
        )
    return instance


async def _fetch_official_qr() -> tuple[str, str, dict[str, Any]]:
    params = {"source": "wecom-cli", "plat": _platform_code()}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(WECOM_QR_GENERATE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    scode = str(data.get("scode", "")).strip()
    auth_url = str(data.get("auth_url", "")).strip()
    if not scode or not auth_url:
        raise BadRequestError(
            message="企业微信官方二维码生成失败",
            message_key="errors.wecom.qr_generate_failed",
        )
    return scode, auth_url, payload


async def _query_official_qr_result(scode: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(WECOM_QR_QUERY_URL, params={"scode": scode})
        resp.raise_for_status()
        return resp.json()


async def _save_wecom_channel_config(
    instance: Instance,
    db: AsyncSession,
    *,
    bot_id: str,
    secret: str,
) -> dict[str, Any]:
    await ensure_official_wecom_plugin_installed(instance, db)
    adapter = get_config_adapter(instance.runtime or "openclaw")

    async with remote_fs(instance, db) as fs:
        config = await adapter.read_config(fs) or {}
        channels = adapter.extract_channels(config) or {}
        if not isinstance(channels, dict):
            channels = {}

        current = channels.get("wecom") if isinstance(channels.get("wecom"), dict) else {}
        wecom_config = dict(current)
        wecom_config.update({
            "botId": bot_id,
            "secret": secret,
            "enabled": True,
        })
        if "dmPolicy" not in wecom_config:
            wecom_config["dmPolicy"] = "open"
        if "groupPolicy" not in wecom_config:
            wecom_config["groupPolicy"] = "open"
        if "sendThinkingMessage" not in wecom_config:
            wecom_config["sendThinkingMessage"] = True
        if (wecom_config.get("dmPolicy") == "open" or wecom_config.get("groupPolicy") == "open"):
            allow_from = wecom_config.get("allowFrom")
            if not isinstance(allow_from, list) or len(allow_from) == 0:
                wecom_config["allowFrom"] = ["*"]

        channels["wecom"] = wecom_config
        config = adapter.merge_channels(config, channels)
        ensure_wecom_plugin_config(config)
        await adapter.write_config(fs, config)

    restart_result = await adapter.restart(instance, db)
    return restart_result


def _session_payload(session: WecomBindSession) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "status": session.status,
        "scode": session.state,
        "qr_url": session.qr_url,
        "expires_at": _to_iso(session.expires_at),
        "bot_id": _mask_bot_id(session.bound_user_id),
        "message_key": "channel.wecomBindSuccess" if session.status == "bound" else None,
        "message": "绑定成功" if session.status == "bound" else None,
    }


async def start_qr_session(
    instance_id: str,
    current_user: User | None,
    db: AsyncSession,
) -> dict[str, Any]:
    if current_user is None:
        raise BadRequestError("缺少当前用户上下文", "errors.auth.current_user_required")
    instance = await _get_instance(instance_id, db)
    await ensure_official_wecom_plugin_installed(instance, db)

    result = await db.execute(
        select(WecomBindSession).where(
            WecomBindSession.instance_id == instance.id,
            WecomBindSession.user_id == (current_user.id if current_user else ""),
            WecomBindSession.status == "pending",
            not_deleted(WecomBindSession),
        )
    )
    for old in result.scalars().all():
        old.status = "cancelled"
        old.cancelled_at = _to_utc_now()
        old.soft_delete()

    scode, auth_url, generate_payload = await _fetch_official_qr()
    expires_at = _to_utc_now() + timedelta(seconds=max(60, settings.WECOM_QR_EXPIRE_SECONDS))
    session = WecomBindSession(
        instance_id=instance.id,
        org_id=instance.org_id or "",
        user_id=current_user.id,
        state=scode,
        status="pending",
        qr_url=f"{WECOM_QR_PAGE_URL}{scode}",
        expires_at=expires_at,
        callback_raw=_json_dumps({
            "auth_url": auth_url,
            "generate_payload": generate_payload,
        }),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_payload(session)


async def get_qr_status(
    instance_id: str,
    session_id: str,
    current_user: User | None,
    db: AsyncSession,
) -> dict[str, Any]:
    if current_user is None:
        raise BadRequestError("缺少当前用户上下文", "errors.auth.current_user_required")
    instance = await _get_instance(instance_id, db)
    result = await db.execute(
        select(WecomBindSession).where(
            WecomBindSession.id == session_id,
            WecomBindSession.instance_id == instance_id,
            WecomBindSession.user_id == (current_user.id if current_user else ""),
            not_deleted(WecomBindSession),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("绑定会话不存在", "errors.wecom.session_not_found")

    now = _to_utc_now()
    if session.status == "pending" and session.expires_at < now:
        session.status = "expired"
        await db.commit()
        return _session_payload(session)

    if session.status != "pending":
        return _session_payload(session)

    payload = await _query_official_qr_result(session.state)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    status = str(data.get("status", "")).strip().lower()

    if status == "success":
        bot_info = data.get("bot_info") if isinstance(data.get("bot_info"), dict) else {}
        bot_id = str(bot_info.get("botid", "")).strip()
        secret = str(bot_info.get("secret", "")).strip()
        if not bot_id or not secret:
            session.status = "failed"
            session.fail_reason = "missing_bot_credentials"
            session.callback_raw = _json_dumps({"query_payload": payload})
            await db.commit()
            return _session_payload(session)

        restart_result = await _save_wecom_channel_config(
            instance,
            db,
            bot_id=bot_id,
            secret=secret,
        )
        session.status = "bound"
        session.bound_user_id = bot_id
        session.bound_at = _to_utc_now()
        session.callback_raw = _json_dumps({
            "query_payload": payload,
            "restart_result": restart_result,
        })
        await db.commit()
        return _session_payload(session)

    if status in {"expired", "failed", "cancelled"}:
        session.status = status
        session.fail_reason = str(data.get("errmsg", "")).strip() or status
        session.callback_raw = _json_dumps({"query_payload": payload})
        await db.commit()
        return _session_payload(session)

    return _session_payload(session)


async def cancel_qr_session(
    instance_id: str,
    current_user: User | None,
    db: AsyncSession,
    session_id: str | None = None,
) -> dict[str, Any]:
    if current_user is None:
        raise BadRequestError("缺少当前用户上下文", "errors.auth.current_user_required")
    await _get_instance(instance_id, db)
    stmt = select(WecomBindSession).where(
        WecomBindSession.instance_id == instance_id,
        WecomBindSession.user_id == (current_user.id if current_user else ""),
        WecomBindSession.status == "pending",
        not_deleted(WecomBindSession),
    )
    if session_id:
        stmt = stmt.where(WecomBindSession.id == session_id)
    result = await db.execute(stmt.order_by(WecomBindSession.created_at.desc()))
    session = result.scalars().first()
    if not session:
        raise NotFoundError("绑定会话不存在", "errors.wecom.session_not_found")

    session.status = "cancelled"
    session.cancelled_at = _to_utc_now()
    session.soft_delete()
    await db.commit()
    return {"session_id": session.id, "status": session.status}


async def install_official_plugin(
    instance_id: str,
    current_user: User | None,
    db: AsyncSession,
) -> dict[str, Any]:
    del current_user
    instance = await _get_instance(instance_id, db)
    return await ensure_official_wecom_plugin_installed(instance, db)


async def save_manual_config(
    instance_id: str,
    current_user: User | None,
    db: AsyncSession,
    *,
    bot_id: str,
    secret: str,
) -> dict[str, Any]:
    del current_user
    instance = await _get_instance(instance_id, db)
    restart_result = await _save_wecom_channel_config(
        instance,
        db,
        bot_id=bot_id.strip(),
        secret=secret.strip(),
    )
    return {
        "status": "bound",
        "bot_id": _mask_bot_id(bot_id),
        "restart_result": restart_result,
    }
