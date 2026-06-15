"""`/v1/jobs` list + detail — owner-scoping, control_caps, pagination shape.

The store is patched (its SQL is exercised on real PG in the live-smoke); these
lock the router contract: owner forwarded, control_caps derived, 404 anti-oracle."""

from unittest.mock import AsyncMock, patch

from tests.conftest import TEST_USER


def _job(**over):
    base = {
        "service": "knowledge", "job_id": "22222222-2222-2222-2222-222222222222",
        "owner_user_id": TEST_USER, "kind": "extraction", "status": "running",
        "parent_job_id": None, "detail_status": "ch 3/40",
        "progress": {"done": 3, "total": 40}, "title": "extract",
        "error": None, "created_at": "2026-06-15T10:00:00+00:00",
        "updated_at": "2026-06-15T10:05:00+00:00", "child_count": 0,
    }
    base.update(over)
    return base


def test_list_returns_items_with_control_caps(client):
    with patch("app.routers.jobs.store.list_jobs", new=AsyncMock(return_value=([_job()], "CURSOR"))):
        r = client.get("/v1/jobs", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    body = r.json()
    assert body["next_cursor"] == "CURSOR"
    item = body["items"][0]
    # running + extraction (multi-unit) → pause + cancel
    assert item["control_caps"] == ["pause", "cancel"]


def test_list_forwards_owner_and_filters(client):
    spy = AsyncMock(return_value=([], None))
    with patch("app.routers.jobs.store.list_jobs", new=spy):
        client.get(
            "/v1/jobs?status=running&kind=extraction&q=神&limit=10",
            headers={"Authorization": "Bearer x"},
        )
    assert spy.await_args.args[1] == TEST_USER  # owner scoping
    kw = spy.await_args.kwargs
    assert kw["status"] == "running" and kw["kind"] == "extraction"
    assert kw["q"] == "神" and kw["limit"] == 10


def test_list_parent_children(client):
    spy = AsyncMock(return_value=([], None))
    with patch("app.routers.jobs.store.list_jobs", new=spy):
        client.get("/v1/jobs?parent=99999999-9999-9999-9999-999999999999",
                   headers={"Authorization": "Bearer x"})
    assert spy.await_args.kwargs["parent"] == "99999999-9999-9999-9999-999999999999"


def test_detail_returns_job(client):
    with patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=_job(status="paused", kind="campaign"))):
        r = client.get("/v1/jobs/campaign/22222222-2222-2222-2222-222222222222",
                       headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json()["control_caps"] == ["resume", "cancel"]


def test_detail_404_when_not_found_or_not_owned(client):
    with patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=None)):
        r = client.get("/v1/jobs/knowledge/22222222-2222-2222-2222-222222222222",
                       headers={"Authorization": "Bearer x"})
    assert r.status_code == 404


def test_detail_forwards_owner_scope(client):
    spy = AsyncMock(return_value=None)
    with patch("app.routers.jobs.store.get_job", new=spy):
        client.get("/v1/jobs/knowledge/22222222-2222-2222-2222-222222222222",
                   headers={"Authorization": "Bearer x"})
    # get_job(db, owner, service, job_id) — owner is the verified sub
    assert spy.await_args.args[1] == TEST_USER
    assert spy.await_args.args[2] == "knowledge"


def test_health(client):
    assert client.get("/health").text == "ok"
