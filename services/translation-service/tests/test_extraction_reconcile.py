"""OBS/M2 reconciliation-sweep endpoint (INV-O12): re-derive an extraction job's stats
from the extraction_batch_outcomes SSOT and surface drift vs the cached job-row counters.
Drives the route over the TestClient with the DB pool mocked (internal-token guarded)."""
from uuid import uuid4

TOKEN = "test_internal_token"  # matches tests/conftest.py INTERNAL_SERVICE_TOKEN


def _path() -> str:
    return f"/internal/translation/extraction-jobs/{uuid4()}/reconcile"


def test_reconcile_reports_ssot_no_drift(client, fake_pool):
    fake_pool.fetchrow.return_value = {
        "status": "completed", "completed_chapters": 2, "failed_chapters": 0, "total_chapters": 2,
    }
    # chapter A: 2 clean batches → completed. chapter B: clean + truncated → with-errors.
    fake_pool.fetch.return_value = [
        {"chapter_id": "A", "status": "ok"}, {"chapter_id": "A", "status": "empty_valid"},
        {"chapter_id": "B", "status": "ok"}, {"chapter_id": "B", "status": "truncated"},
    ]
    r = client.get(_path(), headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["ssot"]["chapters_completed"] == 1
    assert body["ssot"]["chapters_with_errors"] == 1
    assert body["ssot"]["by_status"]["truncated"] == 1
    assert body["drift"] is False  # derived finished (2) == job completed_chapters (2)


def test_reconcile_detects_drift(client, fake_pool):
    # The job row claims 5 finished chapters but the SSOT only has 1 → drift.
    fake_pool.fetchrow.return_value = {
        "status": "completed", "completed_chapters": 5, "failed_chapters": 0, "total_chapters": 5,
    }
    fake_pool.fetch.return_value = [{"chapter_id": "A", "status": "ok"}]
    r = client.get(_path(), headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 200
    assert r.json()["drift"] is True


def test_reconcile_unknown_job_404(client, fake_pool):
    fake_pool.fetchrow.return_value = None
    r = client.get(_path(), headers={"X-Internal-Token": TOKEN})
    assert r.status_code == 404


def test_reconcile_requires_internal_token(client, fake_pool):
    r = client.get(_path())
    assert r.status_code in (401, 403, 422)
