"""Internal dispatch endpoint — Auto-Draft Factory S1 (decision A).

Guards the assert-verified-user_id contract: the internal token authenticates
the SERVICE; ownership is re-verified against the asserted user_id; the core
job-create path is reused.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException

TOKEN = "test_internal_token"  # matches conftest INTERNAL_SERVICE_TOKEN
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
C1 = "11111111-1111-1111-1111-111111111111"
JOB = "dddddddd-dddd-dddd-dddd-dddddddddddd"


def _body(**over):
    b = {"user_id": USER, "book_id": BOOK, "chapter_ids": [C1],
         "target_language": "vi", "model_source": "user_model"}
    b.update(over)
    return b


def test_rejects_missing_internal_token(client):
    resp = client.post("/internal/translation/dispatch-job", json=_body())
    assert resp.status_code == 401


def test_rejects_wrong_internal_token(client):
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(),
        headers={"X-Internal-Token": "nope"},
    )
    assert resp.status_code == 401


def test_dispatch_creates_job_with_asserted_user(client, mocker):
    verify = mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(),
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["job_id"] == JOB
    # ownership re-verified against the asserted user_id
    verify.assert_awaited_once()
    assert verify.call_args.args[1] == USER
    # core job-create reused with the asserted user_id
    assert core.call_args.args[3] == USER


def test_dispatch_forwards_campaign_id_to_core(client, mocker):
    """S4a: a campaign-dispatched job carries campaign_id into the create core
    (→ persisted on translation_jobs + the published message → provider job_meta)."""
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    CAMP = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(campaign_id=CAMP),
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 201, resp.text
    # S4a: campaign_id is an internal-only kwarg to the core, NOT a CreateJobPayload
    # field (the public route must not accept it).
    assert str(core.call_args.kwargs["campaign_id"]) == CAMP


def test_dispatch_forwards_verifier_model_to_payload(client, mocker):
    """S5b: a campaign-picked verifier model is threaded onto the CreateJobPayload
    (which already persists+publishes it; the V3 orchestrator resolves it with a
    translator fallback)."""
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    VER = "99999999-9999-9999-9999-999999999999"
    resp = client.post(
        "/internal/translation/dispatch-job",
        json=_body(verifier_model_source="user_model", verifier_model_ref=VER),
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 201, resp.text
    created_payload = core.call_args.args[2]  # (db, book_id, CreateJobPayload, user_id)
    assert created_payload.verifier_model_source == "user_model"
    assert str(created_payload.verifier_model_ref) == VER


def test_dispatch_forwards_eval_judge_model_to_payload(client, mocker):
    """S5b-eval: a campaign-picked eval-judge model threads onto CreateJobPayload
    (rides the translation.quality event to learning's M7d-2 fidelity judge)."""
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    EJ = "88888888-8888-8888-8888-888888888888"
    resp = client.post(
        "/internal/translation/dispatch-job",
        json=_body(eval_judge_model_source="user_model", eval_judge_model_ref=EJ),
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 201, resp.text
    created_payload = core.call_args.args[2]
    assert created_payload.eval_judge_model_source == "user_model"
    assert str(created_payload.eval_judge_model_ref) == EJ


def test_dispatch_defaults_pipeline_v3(client, mocker):
    """D-FACTORY-V3-PIPELINE: a campaign dispatch defaults to V3 so the verifier +
    translation.quality emit + S5b-eval judge engage (v2 would skip them all)."""
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(),  # no pipeline_version
        headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 201, resp.text
    assert core.call_args.args[2].pipeline_version == "v3"


def test_dispatch_pipeline_version_overridable(client, mocker):
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(pipeline_version="v2"),
        headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 201, resp.text
    assert core.call_args.args[2].pipeline_version == "v2"


def test_dispatch_drops_half_verifier_override(client, mocker):
    """A verifier source with no ref is a half-override → both dropped (the
    CreateJobPayload pairing validator would otherwise 422)."""
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock, return_value=SimpleNamespace(job_id=UUID(JOB)))
    resp = client.post(
        "/internal/translation/dispatch-job",
        json=_body(verifier_model_source="user_model"),  # no ref
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 201, resp.text
    created_payload = core.call_args.args[2]
    assert created_payload.verifier_model_source is None
    assert created_payload.verifier_model_ref is None


def test_ownership_failure_propagates(client, mocker):
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail={"code": "TRANSL_FORBIDDEN"}))
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(),
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 403


def test_empty_chapter_ids_422(client, mocker):
    mocker.patch(
        "app.routers.internal_dispatch._verify_book_owner", new_callable=AsyncMock)
    resp = client.post(
        "/internal/translation/dispatch-job", json=_body(chapter_ids=[]),
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 422


# ── S3c-2 internal cancel ────────────────────────────────────────────────────

def test_cancel_rejects_missing_token(client):
    resp = client.post(f"/internal/translation/jobs/{JOB}/cancel", json={"user_id": USER})
    assert resp.status_code == 401


def test_cancel_invokes_core_with_asserted_user(client, mocker):
    core = mocker.patch(
        "app.routers.internal_dispatch._cancel_job_core", new_callable=AsyncMock)
    resp = client.post(
        f"/internal/translation/jobs/{JOB}/cancel", json={"user_id": USER},
        headers={"X-Internal-Token": TOKEN},
    )
    assert resp.status_code == 204
    core.assert_awaited_once()
    # core(db, job_id, user_id) — asserted user propagated
    assert core.call_args.args[2] == USER
    assert str(core.call_args.args[1]) == JOB
