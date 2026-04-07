"""Tunnel message protocol — type-safe definitions for WebSocket tunnel messages."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TunnelMessageType(str, Enum):
    # Backend -> Instance
    AUTH_OK = "auth.ok"
    AUTH_ERROR = "auth.error"
    CHAT_REQUEST = "chat.request"
    CHAT_CANCEL = "chat.cancel"
    LEARNING_TASK = "learning.task"
    PING = "ping"
    CONFIG_PUSH = "config.push"

    # Instance -> Backend
    AUTH = "auth"
    CHAT_RESPONSE_CHUNK = "chat.response.chunk"
    CHAT_RESPONSE_DONE = "chat.response.done"
    CHAT_RESPONSE_ERROR = "chat.response.error"
    COLLABORATION_MESSAGE = "collaboration.message"
    PONG = "pong"
    STATUS_REPORT = "status.report"


@dataclass
class TunnelMessage:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: str = ""
    trace_id: str = ""
    ts: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "ts": self.ts,
        }
        if self.reply_to:
            d["replyTo"] = self.reply_to
        if self.trace_id:
            d["traceId"] = self.trace_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TunnelMessage:
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            type=d.get("type", ""),
            payload=d.get("payload", {}),
            reply_to=d.get("replyTo", ""),
            trace_id=d.get("traceId", ""),
            ts=d.get("ts", int(time.time() * 1000)),
        )
