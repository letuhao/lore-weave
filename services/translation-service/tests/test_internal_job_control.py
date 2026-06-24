"""Internal job-control endpoint — Unified Job Control Plane P3-4.

`POST /internal/translation/job-control/{job_id}/{action}` is the control surface the
central jobs-service forwards user actions to. Translation supports cancel + stop-dispatch
pause/resume + retry (B2 — D-JOBS-P3-TRANSLATION-PAUSE), on a DISTINCT prefix from the
campaign cancel (`/internal/translation/jobs/{job_id}/cancel`, which takes a `user_id`
body) so the control-plane `owner_user_id` contract doesn't collide. These drive the route
over the TestClient (real internal-token guard + payload validation), with the DB pool
mocked; the action cores (cancel/pause/resume) are owner-scoped (M4 — 404 if not owned,
409 on an illegal transition) and covered in detail by test_internal_dispatch.py."""

from uuid import uuid4

OWNER = "0a000000-0000-4000-8000-000000000003"
JOB = str(uuid4())
TOKEN = "test_internal_token"  # matches tests/conftest.py INTERNAL_SERVICE_TOKEN
PATH = f"/internal/translation/job-control/{JOB}"


def test_cancel_owned_running_job_200(client, fake_pool):
    fake_pool.fetchrow.return_value = {"owner_user_id": OWNER, "status": "running"}
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER},
                     headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    assert r.json() == {"job_id": JOB, "status": "cancelled"}


def test_cancel_not_owned_404(client, fake_pool):
    # _cancel_job_core: row owner != asserted owner → anti-oracle 404 (M4 re-check).
    fake_pool.fetchrow.return_value = {"owner_user_id": str(uuid4()), "status": "running"}
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER},
                     headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 404


def test_cancel_terminal_409(client, fake_pool):
    fake_pool.fetchrow.return_value = {"owner_user_id": OWNER, "status": "completed"}
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER},
                     headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 409


def test_pause_running_job_200(client, fake_pool):
    # B2: pause running→paused (the UPDATE … RETURNING owner_user_id matched).
    fake_pool.fetchrow.return_value = {"owner_user_id": OWNER}
    r = client.post(f"{PATH}/pause", json={"owner_user_id": OWNER},
                    headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["status"] == "paused"


def test_resume_paused_job_200(client, fake_pool):
    # B2: resume paused→running (no un-done chapters → fetch returns []; no re-publish).
    fake_pool.fetchrow.return_value = {
        "job_id": JOB, "owner_user_id": OWNER, "book_id": str(uuid4()),
        "model_source": "user_model", "model_ref": uuid4(), "system_prompt": "s",
        "user_prompt_tpl": "t", "target_language": "vi",
        "compact_model_source": None, "compact_model_ref": None,
        "compact_system_prompt": "c", "compact_user_prompt_tpl": "ct",
        "chunk_size_tokens": 2000, "invoke_timeout_secs": 300, "pipeline_version": "v3",
        "qa_depth": "standard", "max_qa_rounds": 2, "verifier_model_source": None,
        "verifier_model_ref": None, "eval_judge_model_source": None,
        "eval_judge_model_ref": None, "cold_start_mode": "single_pass",
        "campaign_id": None, "block_index_filter": None, "seed_version_id": None,
    }
    fake_pool.fetch.return_value = []
    r = client.post(f"{PATH}/resume", json={"owner_user_id": OWNER},
                    headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["status"] == "running"


def test_unknown_action_400(client):
    r = client.post(f"/internal/translation/job-control/{JOB}/explode",
                    json={"owner_user_id": OWNER}, headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 400


# ── D-JOBS-SECONDARY-KIND-CONTROL — glossary-extract / glossary-translate cancel dispatch ──

def test_glossary_extraction_cancel_dispatches_to_extraction_jobs(client, fake_pool):
    from unittest.mock import AsyncMock, patch
    # kind=glossary_extraction → _cancel_secondary_core on extraction_jobs: owned + running →
    # UPDATE cancelling + emit (kind=glossary_extraction). Mocked pool/conn via conftest acquire.
    fake_pool.fetchrow.return_value = {"owner_user_id": OWNER, "status": "running"}
    with patch("app.routers.internal_dispatch.emit_job_event", new_callable=AsyncMock) as emit:
        r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER, "kind": "glossary_extraction"},
                        headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200 and r.json()["status"] == "cancelling"
    kw = emit.await_args.kwargs
    assert kw["kind"] == "glossary_extraction" and kw["status"] == "cancelling"
    # the cancelling UPDATE targeted extraction_jobs, not translation_jobs
    assert any("extraction_jobs" in str(c.args[0]) for c in fake_pool.execute.await_args_list)


def test_glossary_translation_cancel_terminal_409(client, fake_pool):
    fake_pool.fetchrow.return_value = {"owner_user_id": OWNER, "status": "completed"}
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER, "kind": "glossary_translation"},
                    headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 409


def test_glossary_secondary_not_owned_404(client, fake_pool):
    from uuid import uuid4
    fake_pool.fetchrow.return_value = {"owner_user_id": str(uuid4()), "status": "running"}
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER, "kind": "glossary_extraction"},
                    headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 404


def test_glossary_secondary_pause_unsupported_400(client, fake_pool):
    # secondary kinds are cancel-only — a pause/resume must 400 (never touch the row)
    r = client.post(f"{PATH}/pause", json={"owner_user_id": OWNER, "kind": "glossary_translation"},
                    headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 400


def test_missing_internal_token_401(client):
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER})
    assert r.status_code == 401


def test_reconcile_jobs_maps_partial_to_completed(client, fake_pool):
    from datetime import datetime, timezone
    ts = datetime(2026, 6, 15, tzinfo=timezone.utc)
    # The reconcile now UNIONs translation_jobs + extraction_jobs, so each row carries its
    # own `kind` (the SQL discriminator). `partial`/`completed_with_errors` → `completed`.
    fake_pool.fetch.return_value = [
        {"job_id": JOB, "owner_user_id": OWNER, "status": "partial", "error_message": None,
         "kind": "translation", "ts": ts},
    ]
    r = client.get("/internal/translation/jobs", params={"since": ts.isoformat()},
                   headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    p = r.json()["jobs"][0]
    assert p["service"] == "translation" and p["kind"] == "translation"
    assert p["status"] == "completed"  # 'partial' → 'completed'
    assert p["job_id"] == JOB and p["occurred_at"] == ts.isoformat()


def test_reconcile_includes_glossary_extraction(client, fake_pool):
    # D-JOBS-GLOSSARY-EXTRACT-UNWIRED: the reconcile UNION now also surfaces glossary-extract
    # jobs (kind='glossary_extraction'); 'completed_with_errors' normalizes to 'completed'.
    from datetime import datetime, timezone
    ts = datetime(2026, 6, 16, tzinfo=timezone.utc)
    fake_pool.fetch.return_value = [
        {"job_id": JOB, "owner_user_id": OWNER, "status": "completed_with_errors",
         "error_message": None, "kind": "glossary_extraction", "ts": ts},
    ]
    r = client.get("/internal/translation/jobs", params={"since": ts.isoformat()},
                   headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    p = r.json()["jobs"][0]
    assert p["service"] == "translation" and p["kind"] == "glossary_extraction"
    assert p["status"] == "completed"  # completed_with_errors → completed


def test_reconcile_includes_glossary_translation(client, fake_pool):
    # D-JOBS-GLOSSARY-TRANSLATE-UNWIRED: the reconcile UNION also surfaces glossary batch
    # translation jobs (kind='glossary_translation'); 'failed' carries a kind-scoped error.
    from datetime import datetime, timezone
    ts = datetime(2026, 6, 17, tzinfo=timezone.utc)
    fake_pool.fetch.return_value = [
        {"job_id": JOB, "owner_user_id": OWNER, "status": "failed",
         "error_message": "boom", "kind": "glossary_translation", "ts": ts},
    ]
    r = client.get("/internal/translation/jobs", params={"since": ts.isoformat()},
                   headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    p = r.json()["jobs"][0]
    assert p["service"] == "translation" and p["kind"] == "glossary_translation"
    assert p["status"] == "failed"
    assert p["error"] == {"code": "glossary_translation_failed", "message": "boom"}


def test_reconcile_requires_internal_token(client):
    r = client.get("/internal/translation/jobs", params={"since": "2026-06-15T00:00:00+00:00"})
    assert r.status_code == 401
