from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.oauth_connection import UserOAuthConnection
from app.models.org_membership import OrgMembership
from app.models.org_oauth_binding import OrgOAuthBinding
from app.models.user import User
from app.schemas.auth import UserInfo
from app.services import auth_service
from app.utils.oauth_providers.base import OAuthUserInfo


class _ScalarResult:
    def __init__(self, one_or_none=None, one=None):
        self._one_or_none = one_or_none
        self._one = one

    def scalar_one_or_none(self):
        return self._one_or_none

    def scalar_one(self):
        if self._one is not None:
            return self._one
        if self._one_or_none is not None:
            return self._one_or_none
        raise RuntimeError("no scalar_one value")


class _FakeSession:
    def __init__(self, execute_results):
        self._results = list(execute_results)
        self.added = []
        self.execute = AsyncMock(side_effect=self._execute_impl)
        self.flush = AsyncMock()
        self.commit = AsyncMock()

    async def _execute_impl(self, *_args, **_kwargs):
        if not self._results:
            raise RuntimeError("unexpected execute call")
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)


async def _fake_build_user_info(user: User, _db):
    return UserInfo.model_validate(user)


def _make_user(name: str, email: str) -> User:
    user = User(name=name, email=email, role="user")
    user.id = "user-" + name.lower().replace(" ", "-")
    user.is_active = True
    user.is_super_admin = False
    user.must_change_password = False
    return user


class _Provider:
    def __init__(self, oauth_info: OAuthUserInfo):
        self._oauth_info = oauth_info

    async def exchange_code(self, _code: str, _redirect_uri: str | None = None, client_id: str | None = None):
        return self._oauth_info


@pytest.mark.asyncio
async def test_oauth_login_auto_bind_existing_user_by_email(monkeypatch):
    user = _make_user("Old Name", "a@example.com")
    oauth_info = OAuthUserInfo(
        provider="wecom",
        provider_user_id="wecom-u-1",
        provider_tenant_id="corp-1",
        name="New Name",
        email="a@example.com",
        avatar_url="https://avatar.example.com/1.png",
    )
    db = _FakeSession(
        [
            _ScalarResult(one_or_none=None),
            _ScalarResult(one_or_none=user),
            _ScalarResult(one_or_none=None),
            _ScalarResult(one=user),
        ]
    )

    monkeypatch.setattr(auth_service, "get_provider", lambda _name: _Provider(oauth_info))
    monkeypatch.setattr(auth_service, "_build_user_info", _fake_build_user_info)
    monkeypatch.setattr(auth_service, "create_access_token", lambda _uid: "access-token")
    monkeypatch.setattr(auth_service, "create_refresh_token", lambda _uid: "refresh-token")

    result = await auth_service.oauth_login("wecom", "code-1", db)

    assert result.access_token == "access-token"
    assert result.refresh_token == "refresh-token"
    assert result.provider == "wecom"
    assert result.needs_org_setup is True
    assert user.name == "New Name"
    assert user.avatar_url == "https://avatar.example.com/1.png"
    assert any(isinstance(item, UserOAuthConnection) for item in db.added)
    assert not any(isinstance(item, User) and item is not user for item in db.added)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_login_auto_create_user_when_email_not_found(monkeypatch):
    oauth_info = OAuthUserInfo(
        provider="wecom",
        provider_user_id="wecom-u-2",
        provider_tenant_id=None,
        name="Create User",
        email="new@example.com",
        avatar_url=None,
    )
    created_user = _make_user("Create User", "new@example.com")
    db = _FakeSession(
        [
            _ScalarResult(one_or_none=None),
            _ScalarResult(one_or_none=None),
            _ScalarResult(one=created_user),
        ]
    )

    monkeypatch.setattr(auth_service, "get_provider", lambda _name: _Provider(oauth_info))
    monkeypatch.setattr(auth_service, "_build_user_info", _fake_build_user_info)
    monkeypatch.setattr(auth_service, "create_access_token", lambda _uid: "access-token")
    monkeypatch.setattr(auth_service, "create_refresh_token", lambda _uid: "refresh-token")

    result = await auth_service.oauth_login("wecom", "code-2", db)

    assert result.provider == "wecom"
    assert any(isinstance(item, User) for item in db.added)
    assert any(isinstance(item, UserOAuthConnection) for item in db.added)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_login_binding_org_marks_not_need_setup(monkeypatch):
    user = _make_user("User A", "a2@example.com")
    binding = OrgOAuthBinding(org_id="org-1", provider="wecom", provider_tenant_id="corp-1")
    oauth_info = OAuthUserInfo(
        provider="wecom",
        provider_user_id="wecom-u-3",
        provider_tenant_id="corp-1",
        name="User A",
        email="a2@example.com",
        avatar_url=None,
    )
    db = _FakeSession(
        [
            _ScalarResult(one_or_none=None),
            _ScalarResult(one_or_none=user),
            _ScalarResult(one_or_none=binding),
            _ScalarResult(one_or_none=None),
            _ScalarResult(one=user),
        ]
    )

    monkeypatch.setattr(auth_service, "get_provider", lambda _name: _Provider(oauth_info))
    monkeypatch.setattr(auth_service, "_build_user_info", _fake_build_user_info)
    monkeypatch.setattr(auth_service, "create_access_token", lambda _uid: "access-token")
    monkeypatch.setattr(auth_service, "create_refresh_token", lambda _uid: "refresh-token")

    result = await auth_service.oauth_login("wecom", "code-3", db)

    assert result.needs_org_setup is False
    assert user.current_org_id == "org-1"
    assert any(isinstance(item, OrgMembership) for item in db.added)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_login_provider_error_returns_http_401(monkeypatch):
    db = _FakeSession([])

    class _FailProvider:
        async def exchange_code(self, _code: str, _redirect_uri: str | None = None, client_id: str | None = None):
            raise ValueError("boom")

    monkeypatch.setattr(auth_service, "get_provider", lambda _name: _FailProvider())

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.oauth_login("wecom", "code-x", db)

    exc = exc_info.value
    assert exc.status_code == 401
    assert isinstance(exc.detail, dict)
    assert exc.detail.get("message_key") == "errors.auth.oauth_exchange_failed"
    assert exc.detail.get("error_code") == 40130
