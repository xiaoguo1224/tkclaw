"""ZeroClaw tunnel bridge -- standalone process that proxies chat.request to POST /webhook."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from aiohttp import web

from .client import TunnelCallbacks, TunnelClient

logger = logging.getLogger("nodeskclaw_tunnel_bridge.zeroclaw")

DEFAULT_GATEWAY_URL = "http://localhost:4511"
DEFAULT_SIDECAR_PORT = 18791


class ZeroClawBridge:
    """Proxies tunnel chat.request to ZeroClaw's POST /webhook endpoint."""

    def __init__(self) -> None:
        self._gateway_url = os.environ.get("ZEROCLAW_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")
        self._bearer_token = os.environ.get("ZEROCLAW_BEARER_TOKEN", "")
        callbacks = TunnelCallbacks(
            on_auth_ok=lambda: logger.info("ZeroClaw bridge: tunnel authenticated"),
            on_auth_error=lambda reason: logger.error("ZeroClaw bridge: tunnel auth failed: %s", reason),
            on_close=lambda: logger.warning("ZeroClaw bridge: tunnel connection closed"),
            on_reconnecting=lambda attempt: logger.info("ZeroClaw bridge: tunnel reconnecting (attempt #%d)", attempt),
        )
        self._client = TunnelClient(on_chat_request=self._handle_chat_request, callbacks=callbacks)
        self._http: httpx.AsyncClient | None = None
        self._workspace_id: str = ""

    async def run(self) -> None:
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        await self._start_sidecar()
        try:
            await self._client.run_forever()
        finally:
            await self._http.aclose()

    # ── Collaboration sidecar ────────────────────────────────

    async def _start_sidecar(self) -> None:
        app = web.Application()
        app.router.add_post("/collaboration/send", self._handle_collab_send)
        app.router.add_get("/peers", self._handle_list_peers)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("NODESKCLAW_SIDECAR_PORT", str(DEFAULT_SIDECAR_PORT)))
        site = web.TCPSite(runner, "localhost", port)
        await site.start()
        logger.info("ZeroClaw bridge: collaboration sidecar listening on localhost:%d", port)

    async def _handle_collab_send(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response({"error": "invalid JSON"}, status=400)
        target = body.get("target", "")
        text = body.get("text", "")
        if not target or not text:
            return web.json_response({"error": "target and text required"}, status=400)
        await self._client.send_collaboration(
            self._workspace_id, self._client.instance_id, target, text,
        )
        return web.json_response({"ok": True})

    async def _handle_list_peers(self, request: web.Request) -> web.Response:
        peers = await self._client.list_peers(self._workspace_id)
        return web.json_response({"peers": peers})

    # ── Chat request handler ─────────────────────────────────

    async def _handle_chat_request(
        self,
        request_id: str,
        trace_id: str,
        messages: list[dict[str, Any]],
        workspace_id: str,
        no_reply: bool,
    ) -> None:
        if workspace_id:
            self._workspace_id = workspace_id
        prompt = _messages_to_prompt(messages)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        if workspace_id:
            headers["X-Session-Id"] = f"workspace:{workspace_id}"

        try:
            assert self._http is not None
            resp = await self._http.post(
                f"{self._gateway_url}/webhook",
                json={"message": prompt},
                headers=headers,
            )

            if resp.status_code != 200:
                if not no_reply:
                    await self._client.send_response_error(
                        request_id, trace_id,
                        f"ZeroClaw /webhook returned {resp.status_code}",
                    )
                else:
                    await self._client.send_response_done(request_id, trace_id)
                return

            data = resp.json()
            response_text = data.get("response", "")

            if no_reply:
                await self._client.send_response_done(request_id, trace_id)
                return

            if response_text:
                await self._client.send_response_chunk(request_id, trace_id, response_text)
            await self._client.send_response_done(request_id, trace_id)

        except Exception as exc:
            logger.error("ZeroClaw bridge: webhook call failed: %s", exc)
            if no_reply:
                await self._client.send_response_done(request_id, trace_id)
            else:
                await self._client.send_response_error(request_id, trace_id, str(exc))


def _messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Concatenate all message contents so system prompt reaches ZeroClaw."""
    return "\n\n".join(
        msg.get("content", "") for msg in messages if msg.get("content")
    )
