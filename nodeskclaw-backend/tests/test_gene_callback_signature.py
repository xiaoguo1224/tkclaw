import pytest

from app.api import genes as genes_api
from app.core.exceptions import BadRequestError
from app.schemas.gene import LearningCallbackPayload
from app.services.gene_service import (
    build_gene_callback_url,
    sign_gene_callback,
    verify_gene_callback_signature,
)


def test_sign_and_verify_gene_callback_signature():
    payload = LearningCallbackPayload(
        task_id="task-1",
        instance_id="inst-1",
        mode="learn",
        decision="learned",
    )

    sig = sign_gene_callback(payload.task_id, payload.instance_id, "learn")

    assert verify_gene_callback_signature(payload, "learn", sig) is True
    assert verify_gene_callback_signature(payload, "forget", sig) is False


def test_build_gene_callback_url_includes_signature_and_instance():
    url = build_gene_callback_url(
        "https://example.com",
        "/api/v1/genes/learning-callback",
        "task-1",
        "inst-1",
        "learn",
    )

    assert "instance_id=inst-1" in url
    assert "sig=" in url


def test_validate_gene_callback_auth_allows_legacy_unsigned_callback(monkeypatch):
    payload = LearningCallbackPayload(
        task_id="task-1",
        instance_id="inst-1",
        mode="learn",
        decision="learned",
    )

    monkeypatch.setattr(genes_api.settings, "ALLOW_LEGACY_GENE_CALLBACKS", True)

    genes_api._validate_gene_callback_auth(payload, "learn", None, None)


def test_validate_gene_callback_auth_rejects_missing_partial_signature(monkeypatch):
    payload = LearningCallbackPayload(
        task_id="task-1",
        instance_id="inst-1",
        mode="learn",
        decision="learned",
    )

    monkeypatch.setattr(genes_api.settings, "ALLOW_LEGACY_GENE_CALLBACKS", True)

    with pytest.raises(BadRequestError, match="回调签名参数不完整"):
        genes_api._validate_gene_callback_auth(payload, "learn", "sig", None)


def test_validate_gene_callback_auth_rejects_legacy_callback_when_disabled(monkeypatch):
    payload = LearningCallbackPayload(
        task_id="task-1",
        instance_id="inst-1",
        mode="learn",
        decision="learned",
    )

    monkeypatch.setattr(genes_api.settings, "ALLOW_LEGACY_GENE_CALLBACKS", False)

    with pytest.raises(BadRequestError, match="缺少回调签名参数"):
        genes_api._validate_gene_callback_auth(payload, "learn", None, None)
