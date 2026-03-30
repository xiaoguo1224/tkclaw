import json
from types import SimpleNamespace

import pytest

from app.services.instance_health_checker import (
    InstanceHealthChecker,
    _INSTALLING_WECOM_INSTANCE_IDS,
)


def _make_instance(*, runtime: str = "openclaw", pending: bool = True):
    return SimpleNamespace(
        id="inst-1",
        runtime=runtime,
        advanced_config=json.dumps({
            "_nodeskclaw": {
                "wecom_auto_install_pending": pending,
                "wecom_auto_install_attempts": 0,
                "wecom_auto_install_last_error": "",
                "wecom_auto_install_installed_at": None,
            },
        }),
    )


@pytest.mark.asyncio
async def test_wecom_auto_install_on_healthy_success(monkeypatch):
    checker = InstanceHealthChecker(None)
    instance = _make_instance()
    called = {"count": 0}

    async def _fake_install(_instance, _db):
        called["count"] += 1

    monkeypatch.setattr(
        "app.services.channel_config_service.ensure_official_wecom_plugin_installed",
        _fake_install,
    )

    await checker._maybe_auto_install_wecom(instance, object(), "healthy")

    data = json.loads(instance.advanced_config)
    meta = data["_nodeskclaw"]
    assert called["count"] == 1
    assert meta["wecom_auto_install_pending"] is False
    assert meta["wecom_auto_install_attempts"] == 1
    assert meta["wecom_auto_install_last_error"] == ""
    assert isinstance(meta["wecom_auto_install_installed_at"], str)


@pytest.mark.asyncio
async def test_wecom_auto_install_failure_retry(monkeypatch):
    checker = InstanceHealthChecker(None)
    instance = _make_instance()
    called = {"count": 0}

    async def _fake_install(_instance, _db):
        called["count"] += 1
        raise RuntimeError("install failed")

    monkeypatch.setattr(
        "app.services.channel_config_service.ensure_official_wecom_plugin_installed",
        _fake_install,
    )

    await checker._maybe_auto_install_wecom(instance, object(), "healthy")
    await checker._maybe_auto_install_wecom(instance, object(), "healthy")

    data = json.loads(instance.advanced_config)
    meta = data["_nodeskclaw"]
    assert called["count"] == 2
    assert meta["wecom_auto_install_pending"] is True
    assert meta["wecom_auto_install_attempts"] == 2
    assert "install failed" in meta["wecom_auto_install_last_error"]
    assert meta["wecom_auto_install_installed_at"] is None


@pytest.mark.asyncio
async def test_wecom_auto_install_scope_and_concurrency_guard(monkeypatch):
    checker = InstanceHealthChecker(None)
    called = {"count": 0}

    async def _fake_install(_instance, _db):
        called["count"] += 1

    monkeypatch.setattr(
        "app.services.channel_config_service.ensure_official_wecom_plugin_installed",
        _fake_install,
    )

    instance_non_openclaw = _make_instance(runtime="nanobot")
    await checker._maybe_auto_install_wecom(instance_non_openclaw, object(), "healthy")
    assert called["count"] == 0

    instance_no_marker = SimpleNamespace(
        id="inst-2",
        runtime="openclaw",
        advanced_config=json.dumps({}),
    )
    await checker._maybe_auto_install_wecom(instance_no_marker, object(), "healthy")
    assert called["count"] == 0

    instance_not_pending = _make_instance(pending=False)
    await checker._maybe_auto_install_wecom(instance_not_pending, object(), "healthy")
    assert called["count"] == 0

    instance_guarded = _make_instance()
    _INSTALLING_WECOM_INSTANCE_IDS.add(instance_guarded.id)
    try:
        await checker._maybe_auto_install_wecom(instance_guarded, object(), "healthy")
    finally:
        _INSTALLING_WECOM_INSTANCE_IDS.discard(instance_guarded.id)
    assert called["count"] == 0
