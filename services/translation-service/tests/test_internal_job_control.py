"""Internal job-control endpoint — Unified Job Control Plane P3-4.

`POST /internal/translation/job-control/{job_id}/{action}` is the control surface the
central jobs-service forwards user actions to. Translation is cancel-only (no pause
impl yet — D-JOBS-P3-TRANSLATION-PAUSE), on a DISTINCT prefix from the campaign cancel
(`/internal/translation/jobs/{job_id}/cancel`, which takes a `user_id` body) so the
control-plane `owner_user_id` contract doesn't collide. These drive the route over the
TestClient (real internal-token guard + payload validation), with the DB pool mocked;
cancel delegates to the owner-scoped `_cancel_job_core` (M4 — 404 if not owned, 409 if
terminal), which is itself covered by the campaign-cancel tests."""

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


def test_pause_unsupported_400(client):
    # translation is cancel-only — pause/resume 400 (the caps-gate also won't offer them).
    for action in ("pause", "resume", "explode"):
        r = client.post(f"/internal/translation/job-control/{JOB}/{action}",
                        json={"owner_user_id": OWNER}, headers={"X-Internal-Token": TOKEN})
        assert r.status_code == 400


def test_missing_internal_token_401(client):
    r = client.post(f"{PATH}/cancel", json={"owner_user_id": OWNER})
    assert r.status_code == 401


def test_reconcile_jobs_maps_partial_to_completed(client, fake_pool):
    from datetime import datetime, timezone
    ts = datetime(2026, 6, 15, tzinfo=timezone.utc)
    fake_pool.fetch.return_value = [
        {"job_id": JOB, "owner_user_id": OWNER, "status": "partial", "error_message": None, "ts": ts},
    ]
    r = client.get("/internal/translation/jobs", params={"since": ts.isoformat()},
                   headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    p = r.json()["jobs"][0]
    assert p["service"] == "translation" and p["kind"] == "translation"
    assert p["status"] == "completed"  # 'partial' → 'completed'
    assert p["job_id"] == JOB and p["occurred_at"] == ts.isoformat()


def test_reconcile_requires_internal_token(client):
    r = client.get("/internal/translation/jobs", params={"since": "2026-06-15T00:00:00+00:00"})
    assert r.status_code == 401
