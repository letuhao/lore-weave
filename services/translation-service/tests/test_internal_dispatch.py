"""Internal dispatch endpoint — Auto-Draft Factory S1 (decision A).

Guards the assert-verified-user_id contract: the internal token authenticates
the SERVICE; ownership is re-verified against the asserted user_id; the core
job-create path is reused.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from tests.conftest import FakeRecord

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


# ── D-JOBS-P4-RETRY: re-submit a failed job (job-control retry action) ────────

NEW_JOB = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


def _failed_row(**over):
    base = {
        "job_id": UUID(JOB), "book_id": UUID(BOOK), "owner_user_id": UUID(USER),
        "status": "failed", "chapter_ids": [UUID(C1)], "target_language": "vi",
        "model_source": "user_model", "model_ref": uuid4(), "pipeline_version": "v3",
        "qa_depth": "standard", "max_qa_rounds": 2,
        "verifier_model_source": None, "verifier_model_ref": None,
        "eval_judge_model_source": None, "eval_judge_model_ref": None,
        "cold_start_mode": "single_pass", "block_index_filter": None, "seed_version_id": None,
    }
    base.update(over)
    return FakeRecord(base)


def test_retry_resubmits_failed_job_standalone(client, fake_pool, mocker):
    fake_pool.fetchrow.return_value = _failed_row()
    core = mocker.patch(
        "app.routers.internal_dispatch._resolve_and_create_job",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(job_id=UUID(NEW_JOB), status="pending"))
    resp = client.post(
        f"/internal/translation/job-control/{JOB}/retry",
        json={"owner_user_id": USER}, headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == NEW_JOB and body["retried_from"] == JOB
    # standalone re-run: campaign_id forced None (detached from any original campaign saga)
    assert core.call_args.kwargs["campaign_id"] is None
    # the rebuilt payload re-runs the stored set (force) with the stored model
    payload = core.call_args.args[2]
    assert payload.force_retranslate is True
    assert payload.model_source == "user_model"
    assert payload.pipeline_version == "v3"


def test_retry_404_when_not_owned(client, fake_pool):
    fake_pool.fetchrow.return_value = None  # owner-scoped SELECT matched nothing
    resp = client.post(
        f"/internal/translation/job-control/{JOB}/retry",
        json={"owner_user_id": USER}, headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 404


def test_retry_409_when_not_failed(client, fake_pool):
    fake_pool.fetchrow.return_value = _failed_row(status="running")  # only failed is retryable
    resp = client.post(
        f"/internal/translation/job-control/{JOB}/retry",
        json={"owner_user_id": USER}, headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 409


def test_retry_rejects_missing_internal_token(client):
    resp = client.post(
        f"/internal/translation/job-control/{JOB}/retry", json={"owner_user_id": USER})
    assert resp.status_code == 401


# ── D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: chapter-status truth ────────────────────

def _status_url(job_id=JOB, chapter_id=C1):
    return f"/internal/translation/jobs/{job_id}/chapters/{chapter_id}/status"


def test_chapter_status_rejects_missing_token(client):
    resp = client.get(_status_url(), params={"user_id": USER})
    assert resp.status_code == 401


def test_chapter_status_fresh_version_is_done(client, fake_pool):
    # A fresh completed version exists for the language → done (regardless of job).
    fake_pool.fetchrow.side_effect = [{"owner_user_id": USER, "status": "running",
                                       "target_language": "vi"}]
    fake_pool.fetchval.return_value = 1  # fresh-version query hit
    resp = client.get(_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"


def test_chapter_status_skipped_chapter_is_done_even_without_job_row(client, fake_pool):
    # REGRESSION (HIGH /review-impl): the S2 skip-gate excludes an already-translated
    # chapter from the job — it has NO per-job row but DOES have a fresh version.
    # The truth is keyed on (language, chapter), NOT the job, so it must be 'done'
    # (a per-job lookup would wrongly say 'failed' → false campaign failure).
    fake_pool.fetchrow.side_effect = [{"owner_user_id": USER, "status": "completed",
                                       "target_language": "vi"}]
    fake_pool.fetchval.return_value = 1  # fresh version exists from a PRIOR job
    resp = client.get(_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.json()["status"] == "done"


def test_chapter_status_no_fresh_terminal_job_is_failed(client, fake_pool):
    # No fresh version + the job is terminal → it didn't produce one → re-dispatch.
    # (Also the glossary-stale case: a stale completed row is NOT fresh → re-translate.)
    fake_pool.fetchrow.side_effect = [{"owner_user_id": USER, "status": "completed",
                                       "target_language": "vi"}]
    fake_pool.fetchval.return_value = None
    resp = client.get(_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.json()["status"] == "failed"


def test_chapter_status_no_fresh_active_job_is_running(client, fake_pool):
    fake_pool.fetchrow.side_effect = [{"owner_user_id": USER, "status": "running",
                                       "target_language": "vi"}]
    fake_pool.fetchval.return_value = None
    resp = client.get(_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.json()["status"] == "running"


def test_chapter_status_job_not_found_404(client, fake_pool):
    fake_pool.fetchrow.side_effect = [None]
    resp = client.get(_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 404


def test_chapter_status_not_owned_404(client, fake_pool):
    fake_pool.fetchrow.side_effect = [
        {"owner_user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff", "status": "running",
         "target_language": "vi"},
    ]
    resp = client.get(_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 404


def _job_status_url(job_id=JOB):
    return f"/internal/translation/jobs/{job_id}/status"


def test_job_status_rejects_missing_token(client):
    assert client.get(_job_status_url()).status_code == 401


@pytest.mark.parametrize("job_st,expected", [
    ("pending", "active"), ("running", "active"),
    ("completed", "terminal"), ("failed", "terminal"), ("cancelled", "terminal"),
])
def test_job_status_active_vs_terminal(client, fake_pool, job_st, expected):
    fake_pool.fetchrow.side_effect = [{"owner_user_id": USER, "status": job_st}]
    resp = client.get(_job_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == expected


def test_job_status_not_found_404(client, fake_pool):
    fake_pool.fetchrow.side_effect = [None]
    resp = client.get(_job_status_url(), params={"user_id": USER},
                      headers={"X-Internal-Token": TOKEN})
    assert resp.status_code == 404


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
