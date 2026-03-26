"""Webhook endpoints for external channel integrations (Feishu, etc.)."""

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.services import wecom_bind_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/feishu/workspace-message")
async def feishu_workspace_message(request: Request):
    """Receive Feishu bot message callback, inject into workspace.

    Delegates to the shared ``_handle_message_event`` which supports both
    group chat (chat_id) and private chat (open_id) matching.
    """
    body = await request.json()

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    message = event.get("message", {})
    chat_id = message.get("chat_id", "")
    sender_open_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

    content = ""
    msg_type = message.get("message_type", "")
    if msg_type == "text":
        try:
            content = json.loads(message.get("content", "{}")).get("text", "")
        except Exception:
            content = message.get("content", "")
    else:
        content = f"[{msg_type} message]"

    if not content:
        return {"code": 0}

    from app.services.channel_adapters.feishu_ws_client import _handle_message_event

    await _handle_message_event(chat_id, sender_open_id, content)

    return {"code": 0}


@router.get("/wecom/openclaw-bind")
async def wecom_openclaw_bind_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    query = dict(request.query_params)
    msg_signature = query.get("msg_signature", "")
    timestamp = query.get("timestamp", "")
    nonce = query.get("nonce", "")
    echostr = query.get("echostr", "")
    if echostr:
        plain = wecom_bind_service.verify_and_decode_echostr(
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            echostr=echostr,
        )
        return PlainTextResponse(plain)

    state = query.get("state", "")
    code = query.get("code", "")
    base_url = wecom_bind_service.get_callback_base_url_from_request_url(str(request.url))
    data = await wecom_bind_service.complete_bind_by_state(
        state=state,
        code=code,
        callback_payload=query,
        db=db,
        base_url=base_url,
    )
    return {"code": 0, "data": data}


@router.post("/wecom/openclaw-bind")
async def wecom_openclaw_bind_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    query = dict(request.query_params)
    body_raw = (await request.body()).decode("utf-8", errors="ignore")
    payload, _ = wecom_bind_service.parse_wecom_callback_payload(
        query_params=query,
        raw_body=body_raw,
        content_type=request.headers.get("content-type", ""),
    )
    decrypted = wecom_bind_service.verify_and_decode_callback_event(
        msg_signature=query.get("msg_signature"),
        timestamp=query.get("timestamp"),
        nonce=query.get("nonce"),
        encrypted=payload.get("Encrypt") or payload.get("encrypt"),
    )

    merged_payload = {}
    merged_payload.update(payload)
    merged_payload.update(decrypted)

    state = (
        query.get("state")
        or merged_payload.get("State")
        or merged_payload.get("state")
    )
    code = query.get("code") or merged_payload.get("Code") or merged_payload.get("code")
    base_url = wecom_bind_service.get_callback_base_url_from_request_url(str(request.url))
    data = await wecom_bind_service.complete_bind_by_state(
        state=state or "",
        code=code,
        callback_payload=merged_payload,
        db=db,
        base_url=base_url,
    )
    return {"code": 0, "data": data}
