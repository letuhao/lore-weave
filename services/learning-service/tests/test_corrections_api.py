"""Corrections read API — strict per-owner scoping + page shape."""

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.deps import get_current_user, get_db
from app.main import app

USER = str(uuid.uuid4())


def _row(**over):
    base = {
        "id": uuid.uuid4(),
        "user_id": uuid.UUID(USER),
        "project_id": None,
        "book_id": None,
        "target_type": "entity",
        "target_id": "ent-1",
        "op": "update",
        "before_structural": {"kind": "person"},
        "after_structural": {"kind": "person"},
        "before_content_hash": "h1",
        "after_content_hash": "h2",
        "diff_class": "boundary",
        "source_extraction_run_id": None,
        "source_chapter": None,
        "actor_type": "user",
        "actor_id": uuid.UUID(USER),
        "origin_service": "glossary",
        "origin_event_type": "glossary.entity_updated",
        "emitted_at": datetime(2026, 5, 31, tzinfo=timezone.utc),
        "created_at": datetime(2026, 5, 31, tzinfo=timezone.utc),
    }
    base.update(over)
    return base


class FakeReadPool:
    def __init__(self, rows):
        self.rows = rows
        self.fetch_calls = []

    async def fetch(self, sql, *params):
        self.fetch_calls.append((sql, params))
        if "GROUP BY" in sql:
            return []
        return self.rows

    async def fetchval(self, sql, *params):
        return len(self.rows)


def _client(pool):
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_db] = lambda: pool
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_corrections_scopes_to_jwt_user():
    pool = FakeReadPool([_row()])
    client = _client(pool)
    resp = client.get("/v1/learning/corrections")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["user_id"] == USER
    assert body["next_cursor"] is None
    # The query MUST filter on the JWT user as the FIRST bound param (strict isolation).
    sql, params = pool.fetch_calls[0]
    assert "user_id = $1" in sql
    assert str(params[0]) == USER


def test_list_corrections_redacts_raw_content():
    # No before_content / after_content fields are ever exposed (R2 redact).
    pool = FakeReadPool([_row()])
    client = _client(pool)
    body = client.get("/v1/learning/corrections").json()
    item = body["items"][0]
    assert "before_content" not in item and "after_content" not in item
    assert item["before_content_hash"] == "h1"


def test_next_cursor_emitted_when_more_than_limit():
    rows = [_row() for _ in range(3)]
    pool = FakeReadPool(rows)
    client = _client(pool)
    body = client.get("/v1/learning/corrections?limit=2").json()
    assert len(body["items"]) == 2  # peek-ahead trims to limit
    assert body["next_cursor"] is not None


def test_invalid_cursor_400():
    pool = FakeReadPool([])
    client = _client(pool)
    resp = client.get("/v1/learning/corrections?cursor=not-base64!!")
    assert resp.status_code == 400
