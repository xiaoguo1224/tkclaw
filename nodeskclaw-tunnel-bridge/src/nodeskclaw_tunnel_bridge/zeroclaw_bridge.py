"""ZeroClaw tunnel bridge -- standalone process that proxies chat.request to POST /webhook."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .client import TunnelClient

logger = logging.getLogger("nodeskclaw_tunnel_bridge.zeroclaw")

DEFAULT_GATEWAY_URL = "http://localhost:8080"


class ZeroClawBridge:
    """Proxies tunnel chat.request to ZeroClaw's POST /webhook endpoint."""

    def __init__(self) -> None:
        self._gateway_url = os.environ.get("ZEROCLAW_GATEWAY_URL", DEFAULT_GATEWAY_URL).rstrip("/")
        self._bearer_token = os.environ.get("ZEROCLAW_BEARER_TOKEN", "")
        self._client = TunnelClient(on_chat_request=self._handle_chat_request)
        self._http: httpx.AsyncClient | None = None

    async def run(self) -> None:
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        try:
            await self._client.run_forever()
        finally:
            await self._http.aclose()

    async def _handle_chat_request(
        self,
        request_id: str,
        trace_id: str,
        messages: list[dict[str, Any]],
        workspace_id: str,
        no_reply: bool,
    ) -> None:
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
