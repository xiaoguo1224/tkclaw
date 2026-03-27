import pytest

from app.core.config import settings
from app.utils.oauth_providers.wecom import WecomProvider


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _AsyncClientMock:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, _url, params=None):
        if not self._responses:
            raise RuntimeError("unexpected get call")
        return _Resp(self._responses.pop(0))


@pytest.mark.asyncio
async def test_wecom_exchange_code_degrade_when_get_user_detail_failed(monkeypatch):
    monkeypatch.setattr(settings, "WECOM_CORP_ID", "corp-1")
    monkeypatch.setattr(settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(settings, "WECOM_APP_SECRET", "secret-1")
    monkeypatch.setattr(settings, "WECOM_REDIRECT_URI", "https://portal.example.com/login/callback/wecom")

    responses = [
        {"errcode": 0, "access_token": "token-1"},
        {"errcode": 0, "UserId": "zhangsan"},
        {"errcode": 60020, "errmsg": "no permission"},
    ]
    monkeypatch.setattr(
        "app.utils.oauth_providers.wecom.httpx.AsyncClient",
        lambda timeout=10: _AsyncClientMock(responses),
    )

    provider = WecomProvider()
    result = await provider.exchange_code("code-1")

    assert result.provider == "wecom"
    assert result.provider_user_id == "zhangsan"
    assert result.provider_tenant_id == "corp-1"
    assert result.name == "zhangsan"
    assert result.email is None
    assert result.avatar_url is None


@pytest.mark.asyncio
async def test_wecom_exchange_code_requires_userid_not_openid(monkeypatch):
    monkeypatch.setattr(settings, "WECOM_CORP_ID", "corp-1")
    monkeypatch.setattr(settings, "WECOM_AGENT_ID", "1000001")
    monkeypatch.setattr(settings, "WECOM_APP_SECRET", "secret-1")
    monkeypatch.setattr(settings, "WECOM_REDIRECT_URI", "https://portal.example.com/login/callback/wecom")

    responses = [
        {"errcode": 0, "access_token": "token-1"},
        {"errcode": 0, "OpenId": "openid-1"},
    ]
    monkeypatch.setattr(
        "app.utils.oauth_providers.wecom.httpx.AsyncClient",
        lambda timeout=10: _AsyncClientMock(responses),
    )

    provider = WecomProvider()
    with pytest.raises(ValueError) as exc_info:
        await provider.exchange_code("code-2")

    assert "UserId" in str(exc_info.value)
