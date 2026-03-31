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
