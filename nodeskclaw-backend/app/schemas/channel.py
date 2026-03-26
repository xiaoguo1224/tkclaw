"""Pydantic schemas for Channel configuration APIs."""

from datetime import datetime

from pydantic import BaseModel, Field


class AvailableChannel(BaseModel):
    id: str
    label: str
    description: str = ""
    origin: str = "bundled"
    order: int = 999
    has_schema: bool = False


class ChannelSchemaField(BaseModel):
    key: str
    label: str
    type: str = "string"
    required: bool = False
    placeholder: str = ""
    default: str | bool | None = None
    options: list[dict] | None = None


class ChannelConfigsUpdate(BaseModel):
    configs: dict[str, dict] = Field(
        ...,
        description="Channel ID -> config dict, e.g. {'feishu': {'appId': '...', 'appSecret': '...'}}",
    )


class InstallNpmChannelRequest(BaseModel):
    package_name: str = Field(
        ..., min_length=1, max_length=200,
        description="npm package name, e.g. @openclaw/feishu",
    )


class DeployRepoChannelRequest(BaseModel):
    channel_id: str = Field(
        ..., min_length=1, max_length=100,
        description="Channel ID matching a repo plugin, e.g. my-channel",
    )


class ChannelWriteResult(BaseModel):
    status: str
    message: str = ""


class WecomBindStartResponse(BaseModel):
    session_id: str
    status: str
    scode: str
    qr_url: str
    expires_at: datetime


class WecomBindStatusResponse(BaseModel):
    session_id: str
    status: str
    scode: str
    qr_url: str
    expires_at: datetime
    bot_id: str | None = None
    message_key: str | None = None
    message: str | None = None


class WecomBindCancelRequest(BaseModel):
    session_id: str | None = None


class WecomManualSaveRequest(BaseModel):
    bot_id: str = Field(..., min_length=1, max_length=128)
    secret: str = Field(..., min_length=1, max_length=256)
