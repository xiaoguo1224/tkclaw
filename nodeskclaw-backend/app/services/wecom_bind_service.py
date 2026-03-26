import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.wecom_bind_session import WecomBindSession
from app.models.user import User
from app.services.channel_config_service import deploy_repo_channel
from app.services.nfs_mount import remote_fs
from app.services.runtime.config_adapter import get_config_adapter


def _to_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _normalize_base_url(base_url: str | None) -> str:
    raw = (settings.PORTAL_BASE_URL or base_url or "").strip()
    if not raw:
        raise BadRequestError(
            message="未配置回调地址，请先设置 PORTAL_BASE_URL（门户外网地址）",
            message_key="errors.wecom.portal_base_url_missing",
        )
    return raw.rstrip("/")


def _require_wecom_basic_config() -> tuple[str, str, str]:
    corp_id = settings.WECOM_CORP_ID.strip()
    agent_id = settings.WECOM_AGENT_ID.strip()
    agent_secret = settings.WECOM_AGENT_SECRET.strip()
    if not corp_id or not agent_id or not agent_secret:
        raise BadRequestError(
            message="企业微信配置不完整，请检查 WECOM_CORP_ID/WECOM_AGENT_ID/WECOM_AGENT_SECRET",
            message_key="errors.wecom.config_missing",
        )
    return corp_id, agent_id, agent_secret


async def _get_instance(instance_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", "errors.instance.not_found")
    if (instance.runtime or "openclaw") != "openclaw":
        raise BadRequestError(
            message="企业微信扫码绑定仅支持 OpenClaw 引擎",
            message_key="errors.wecom.openclaw_only",
        )
    if not instance.org_id:
        raise BadRequestError(
            message="实例缺少组织归属，无法绑定企业微信",
            message_key="errors.wecom.instance_org_missing",
        )
    return instance


def _build_callback_url(base_url: str | None) -> str:
    normalized = _normalize_base_url(base_url)
    return f"{normalized}/api/v1/webhooks/wecom/openclaw-bind"


def _build_qr_url(corp_id: str, agent_id: str, callback_url: str, state: str) -> str:
    redirect_uri = quote_plus(callback_url)
    return (
        "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
        f"?appid={corp_id}&agentid={agent_id}&redirect_uri={redirect_uri}"
        "&response_type=code&scope=snsapi_privateinfo"
        f"&state={state}"
    )


def _json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return str(data)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("empty data")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 32:
        raise ValueError("invalid padding")
    return data[:-pad_len]


def _decrypt_wecom_ciphertext(encrypt: str, aes_key: str) -> str:
    key = base64.b64decode(f"{aes_key}=")
    cipher_data = base64.b64decode(encrypt)
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    raw = decryptor.update(cipher_data) + decryptor.finalize()
    plain = _pkcs7_unpad(raw)
    xml_len = int.from_bytes(plain[16:20], "big")
    xml_bytes = plain[20:20 + xml_len]
    return xml_bytes.decode("utf-8")


def verify_wecom_signature(
    token: str,
    timestamp: str,
    nonce: str,
    encrypted: str,
    msg_signature: str,
) -> bool:
    joined = "".join(sorted([token, timestamp, nonce, encrypted]))
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return digest == msg_signature


def parse_xml_to_dict(xml_text: str) -> dict[str, str]:
    root = ElementTree.fromstring(xml_text)
    out: dict[str, str] = {}
    for child in root:
        out[child.tag] = child.text or ""
    return out


def parse_wecom_callback_payload(
    query_params: dict[str, str],
    raw_body: str,
    content_type: str,
) -> tuple[dict[str, Any], str | None]:
    payload: dict[str, Any] = {}
    echostr: str | None = None

    if query_params.get("echostr"):
        echostr = query_params.get("echostr")

    if "application/json" in content_type and raw_body.strip():
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            payload = {}
    elif "xml" in content_type and raw_body.strip():
        try:
            payload = parse_xml_to_dict(raw_body)
        except Exception:
            payload = {}
    elif raw_body.strip():
        try:
            payload = parse_xml_to_dict(raw_body)
        except Exception:
            payload = {}

    return payload, echostr


async def start_bind_session(
    instance_id: str,
    current_user: User,
    db: AsyncSession,
    base_url: str | None = None,
) -> dict[str, Any]:
    instance = await _get_instance(instance_id, db)
    corp_id, agent_id, _ = _require_wecom_basic_config()
    callback_url = _build_callback_url(base_url)

    result = await db.execute(
        select(WecomBindSession).where(
            WecomBindSession.instance_id == instance.id,
            WecomBindSession.user_id == current_user.id,
            WecomBindSession.status == "pending",
            not_deleted(WecomBindSession),
        )
    )
    old_sessions = result.scalars().all()
    for old in old_sessions:
        old.status = "cancelled"
        old.cancelled_at = _to_utc_now()
        old.soft_delete()

    state = secrets.token_urlsafe(32)
    expires_at = _to_utc_now() + timedelta(seconds=max(60, settings.WECOM_QR_EXPIRE_SECONDS))
    qr_url = _build_qr_url(corp_id, agent_id, callback_url, state)

    session = WecomBindSession(
        instance_id=instance.id,
        org_id=instance.org_id or "",
        user_id=current_user.id,
        state=state,
        status="pending",
        qr_url=qr_url,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "status": session.status,
        "qr_url": session.qr_url,
        "expires_at": _to_iso(session.expires_at),
    }


async def get_bind_status(
    instance_id: str,
    session_id: str,
    current_user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    await _get_instance(instance_id, db)
    result = await db.execute(
        select(WecomBindSession).where(
            WecomBindSession.id == session_id,
            WecomBindSession.instance_id == instance_id,
            WecomBindSession.user_id == current_user.id,
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

    return {
        "session_id": session.id,
        "status": session.status,
        "qr_url": session.qr_url,
        "expires_at": _to_iso(session.expires_at),
        "bound_user_id": session.bound_user_id,
        "message_key": "channel.wecomBindSuccess" if session.status == "bound" else None,
        "message": "绑定成功" if session.status == "bound" else None,
    }


async def cancel_bind_session(
    instance_id: str,
    current_user: User,
    db: AsyncSession,
    session_id: str | None = None,
) -> dict[str, Any]:
    await _get_instance(instance_id, db)
    stmt = select(WecomBindSession).where(
        WecomBindSession.instance_id == instance_id,
        WecomBindSession.user_id == current_user.id,
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


async def _get_wecom_access_token(corp_id: str, agent_secret: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": agent_secret},
        )
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("errcode") != 0:
        raise BadRequestError(
            message=f"获取企业微信 access_token 失败: {payload.get('errmsg', 'unknown')}",
            message_key="errors.wecom.get_token_failed",
        )
    token = str(payload.get("access_token", "")).strip()
    if not token:
        raise BadRequestError(
            message="企业微信 access_token 为空",
            message_key="errors.wecom.get_token_failed",
        )
    return token


async def _get_user_by_code(
    corp_id: str,
    agent_secret: str,
    code: str,
) -> tuple[str | None, str | None, dict[str, Any]]:
    token = await _get_wecom_access_token(corp_id, agent_secret)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
            params={"access_token": token, "code": code},
        )
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("errcode") != 0:
        return None, None, payload
    return payload.get("UserId"), payload.get("OpenId"), payload


async def _write_wecom_instance_config(
    instance: Instance,
    db: AsyncSession,
    bound_user_id: str | None,
    bound_open_user_id: str | None,
    callback_url: str,
) -> dict[str, Any]:
    corp_id, agent_id, agent_secret = _require_wecom_basic_config()
    adapter = get_config_adapter(instance.runtime or "openclaw")
    if (instance.runtime or "openclaw") != "openclaw":
        raise BadRequestError(
            message="仅 OpenClaw 实例支持企业微信绑定",
            message_key="errors.wecom.openclaw_only",
        )

    try:
        await deploy_repo_channel(instance, db, "wecom")
    except Exception:
        pass

    async with remote_fs(instance, db) as fs:
        config = await adapter.read_config(fs) or {}
        channels = adapter.extract_channels(config) or {}
        if not isinstance(channels, dict):
            channels = {}

        wecom_cfg = channels.get("wecom") if isinstance(channels.get("wecom"), dict) else {}
        accounts = wecom_cfg.get("accounts") if isinstance(wecom_cfg.get("accounts"), dict) else {}
        default_account = accounts.get("default") if isinstance(accounts.get("default"), dict) else {}

        default_account.update({
            "enabled": True,
            "corpId": corp_id,
            "agentId": agent_id,
            "agentSecret": agent_secret,
            "callbackToken": settings.WECOM_CALLBACK_TOKEN.strip(),
            "callbackAesKey": settings.WECOM_CALLBACK_AES_KEY.strip(),
            "callbackUrl": callback_url,
        })
        if bound_user_id:
            default_account["bindUserId"] = bound_user_id
        if bound_open_user_id:
            default_account["bindOpenUserId"] = bound_open_user_id

        accounts["default"] = default_account
        wecom_cfg["accounts"] = accounts
        channels["wecom"] = wecom_cfg

        config = adapter.merge_channels(config, channels)
        plugins = config.setdefault("plugins", {})
        load = plugins.setdefault("load", {})
        paths = load.setdefault("paths", [])
        plugin_path = "/root/.openclaw/extensions/openclaw-channel-wecom"
        if plugin_path not in paths:
            paths.append(plugin_path)
        entries = plugins.setdefault("entries", {})
        entries["wecom"] = {"enabled": True}

        await adapter.write_config(fs, config)

    restart_result = await adapter.restart(instance, db)
    return restart_result


async def complete_bind_by_state(
    state: str,
    db: AsyncSession,
    code: str | None = None,
    callback_payload: dict[str, Any] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    if not state:
        raise BadRequestError(
            message="回调缺少 state",
            message_key="errors.wecom.state_missing",
        )

    result = await db.execute(
        select(WecomBindSession).where(
            WecomBindSession.state == state,
            not_deleted(WecomBindSession),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("绑定会话不存在", "errors.wecom.session_not_found")

    if session.status == "bound":
        return {"session_id": session.id, "status": "bound"}

    now = _to_utc_now()
    if session.expires_at < now:
        session.status = "expired"
        await db.commit()
        return {"session_id": session.id, "status": "expired"}

    payload = callback_payload or {}
    corp_id, _, agent_secret = _require_wecom_basic_config()

    bound_user_id = payload.get("UserId") or payload.get("userid")
    bound_open_user_id = payload.get("OpenId") or payload.get("open_userid")
    auth_payload: dict[str, Any] = {}

    if not bound_user_id and code:
        user_id, open_id, auth_payload = await _get_user_by_code(corp_id, agent_secret, code)
        bound_user_id = user_id
        bound_open_user_id = open_id

    if not bound_user_id and not bound_open_user_id:
        session.status = "failed"
        session.fail_reason = "missing_user_identity"
        session.callback_raw = _json_dumps({"query_code": code, "payload": payload, "auth_payload": auth_payload})
        await db.commit()
        return {"session_id": session.id, "status": "failed"}

    instance = await _get_instance(session.instance_id, db)
    callback_url = _build_callback_url(base_url)
    restart_result = await _write_wecom_instance_config(
        instance=instance,
        db=db,
        bound_user_id=bound_user_id,
        bound_open_user_id=bound_open_user_id,
        callback_url=callback_url,
    )

    session.status = "bound"
    session.bound_user_id = bound_user_id
    session.bound_open_user_id = bound_open_user_id
    session.bound_at = _to_utc_now()
    session.callback_raw = _json_dumps({
        "query_code": code,
        "payload": payload,
        "auth_payload": auth_payload,
        "restart_result": restart_result,
    })
    await db.commit()
    return {"session_id": session.id, "status": "bound"}


def verify_and_decode_echostr(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
) -> str:
    token = settings.WECOM_CALLBACK_TOKEN.strip()
    aes_key = settings.WECOM_CALLBACK_AES_KEY.strip()
    if not token or not aes_key:
        raise HTTPException(400, {"message": "缺少企业微信回调验签配置", "message_key": "errors.wecom.callback_secret_missing"})
    if not verify_wecom_signature(token, timestamp, nonce, echostr, msg_signature):
        raise HTTPException(400, {"message": "企业微信回调签名校验失败", "message_key": "errors.wecom.signature_invalid"})
    return _decrypt_wecom_ciphertext(echostr, aes_key)


def verify_and_decode_callback_event(
    msg_signature: str | None,
    timestamp: str | None,
    nonce: str | None,
    encrypted: str | None,
) -> dict[str, Any]:
    if not (msg_signature and timestamp and nonce and encrypted):
        return {}

    token = settings.WECOM_CALLBACK_TOKEN.strip()
    aes_key = settings.WECOM_CALLBACK_AES_KEY.strip()
    if not token or not aes_key:
        raise HTTPException(400, {"message": "缺少企业微信回调验签配置", "message_key": "errors.wecom.callback_secret_missing"})
    if not verify_wecom_signature(token, timestamp, nonce, encrypted, msg_signature):
        raise HTTPException(400, {"message": "企业微信回调签名校验失败", "message_key": "errors.wecom.signature_invalid"})

    plain_xml = _decrypt_wecom_ciphertext(encrypted, aes_key)
    try:
        return parse_xml_to_dict(plain_xml)
    except Exception:
        return {}


def get_callback_base_url_from_request_url(request_url: str) -> str:
    if settings.PORTAL_BASE_URL.strip():
        return settings.PORTAL_BASE_URL.strip()
    if not request_url:
        return ""
    from urllib.parse import urlsplit
    p = urlsplit(request_url)
    return f"{p.scheme}://{p.netloc}"


def random_session_state() -> str:
    return secrets.token_urlsafe(32) + os.urandom(4).hex()
