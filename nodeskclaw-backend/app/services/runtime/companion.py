"""Companion Process — lightweight HTTP proxy for CLI-based agents.

Wraps CLI agents (claude, aider, codex, etc.) as HTTP services with a
standardized API surface: POST /send, GET /health, GET /status,
POST /cancel, GET /caps.

The actual companion binary runs as a sidecar container (K8s) or
linked service (Docker). This module provides the Python client
interface for the backend to communicate with a running Companion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CompanionConfig:
    base_url: str
    agent_command: str = ""
    working_dir: str = ""
    env_vars: dict = field(default_factory=dict)
    timeout_s: int = 300


@dataclass
class CompanionStatus:
    healthy: bool = False
    agent_running: bool = False
    pid: int | None = None
    uptime_s: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class CompanionCapabilities:
    supports_streaming: bool = False
    supports_tool_use: bool = False
    supports_multi_turn: bool = False
    supports_cancel: bool = True
    agent_type: str = ""
    extra: dict = field(default_factory=dict)


class CompanionClient:
    """Client interface for communicating with a running Companion sidecar."""

    def __init__(self, config: CompanionConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
            timeout=config.timeout_s,
        )

    @property
    def base_url(self) -> str:
        return self._config.base_url

    async def send(self, messages: list[dict], *, session_id: str = "") -> dict:
        """POST /send — Send messages to the CLI agent and get response."""
        resp = await self._client.post(
            f"{self._config.base_url}/send",
            json={
                "messages": messages,
                "session_id": session_id,
                "working_dir": self._config.working_dir,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> bool:
        """GET /health — Check if the companion process is alive."""
        try:
            resp = await self._client.get(
                f"{self._config.base_url}/health",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            logger.debug("Companion health check failed for %s", self._config.base_url, exc_info=True)
            return False

    async def status(self) -> CompanionStatus:
        """GET /status — Get detailed status of the companion and its managed agent."""
        try:
            resp = await self._client.get(
                f"{self._config.base_url}/status",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return CompanionStatus(
                    healthy=True,
                    agent_running=data.get("agent_running", False),
                    pid=data.get("pid"),
                    uptime_s=data.get("uptime_s", 0),
                    extra=data,
                )
        except Exception:
            logger.debug("Companion status check failed for %s", self._config.base_url, exc_info=True)
        return CompanionStatus(healthy=False)

    async def cancel(self, session_id: str = "") -> bool:
        """POST /cancel — Cancel the currently running agent task."""
        try:
            resp = await self._client.post(
                f"{self._config.base_url}/cancel",
                json={"session_id": session_id},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            logger.debug("Companion cancel failed for %s", self._config.base_url, exc_info=True)
            return False

    async def capabilities(self) -> CompanionCapabilities:
        """GET /caps — Query the capabilities of the companion/agent pair."""
        try:
            resp = await self._client.get(
                f"{self._config.base_url}/caps",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return CompanionCapabilities(
                    supports_streaming=data.get("supports_streaming", False),
                    supports_tool_use=data.get("supports_tool_use", False),
                    supports_multi_turn=data.get("supports_multi_turn", False),
                    supports_cancel=data.get("supports_cancel", True),
                    agent_type=data.get("agent_type", ""),
                    extra=data,
                )
        except Exception:
            logger.debug("Companion capabilities check failed for %s", self._config.base_url, exc_info=True)
        return CompanionCapabilities()

    async def close(self) -> None:
        await self._client.aclose()
