"""Q2 — gold-label projection over the corrections log.

Mock-based (no real DB). Asserts the preference-triple projection, the
change-magnitude computation, per-owner isolation, the exclude_noop filter, and
the endpoint.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.gold import _change_magnitude, get_gold_labels
from app.deps import get_current_user, get_db
from app.main import app

USER_ID = uuid.uuid4()
USER_STR = str(USER_ID)


class FakeGoldPool:
    def __init__(self, *, rows=None, total=0):
        self._rows = rows or []
        self._total = total
        self.fetch_params: list = []
        self.fetchval_params: list = []

    def acquire(self):
        pool = self

        class _Acq:
            async def __aenter__(self_):
                return pool

            async def __aexit__(self_, *a):
                return False

        return _Acq()

    async def fetch(self, sql, *params):
        self.fetch_params.append((sql, params))
        return self._rows

    async def fetchval(self, sql, *params):
        self.fetchval_params.append((sql, params))
        return self._total


def _corr_row(**over):
    base = {
        "target_type": "entity",
        "target_id": "eid-1",
        "op": "update",
        "diff_class": "boundary",
        "before_structural": json.dumps({"name": "Kai", "kind": "person"}),
        "after_structural": json.dumps({"name": "Kai Wei", "kind": "person"}),
        "before_content_hash": "h1",
        "after_content_hash": "h2",
        "source_chapter": "ch-1",
        "source_extraction_run_id": None,
        "origin_service": "knowledge",
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    base.update(over)
    return base


# ── _change_magnitude ─────────────────────────────────────────────────


def test_change_magnitude_edit():
    assert _change_magnitude({"name": "a", "kind": "p"}, {"name": "b", "kind": "p"}) == 1


def test_change_magnitude_create_counts_all_keys():
    assert _change_magnitude(None, {"name": "a", "kind": "p"}) == 2


def test_change_magnitude_noop_is_zero():
    assert _change_magnitude({"name": "a"}, {"name": "a"}) == 0


# ── get_gold_labels ───────────────────────────────────────────────────


async def test_projects_preference_triple_and_magnitude():
    pool = FakeGoldPool(rows=[_corr_row()], total=1)
    res = await get_gold_labels(pool, user_id=USER_ID)
    assert res["total"] == 1
    item = res["items"][0]
    assert item["non_preferred"] == {"name": "Kai", "kind": "person"}
    assert item["preferred"] == {"name": "Kai Wei", "kind": "person"}
    assert item["change_magnitude"] == 1
    assert item["origin_service"] == "knowledge"


async def test_owner_scoped_and_user_actor_only():
    pool = FakeGoldPool(rows=[], total=0)
    await get_gold_labels(pool, user_id=USER_ID)
    sql, params = pool.fetch_params[0]
    assert "user_id = $1" in sql
    assert "actor_type = 'user'" in sql  # pipeline writes excluded
    assert params[0] == USER_ID


async def test_exclude_noop_toggles_clause():
    pool = FakeGoldPool(rows=[], total=0)
    await get_gold_labels(pool, user_id=USER_ID, exclude_noop=True)
    assert "IS DISTINCT FROM" in pool.fetch_params[0][0]

    pool2 = FakeGoldPool(rows=[], total=0)
    await get_gold_labels(pool2, user_id=USER_ID, exclude_noop=False)
    assert "IS DISTINCT FROM" not in pool2.fetch_params[0][0]


# ── endpoint ──────────────────────────────────────────────────────────


def _client(pool: FakeGoldPool) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: USER_STR
    app.dependency_overrides[get_db] = lambda: pool
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_gold_labels_endpoint():
    pool = FakeGoldPool(rows=[_corr_row()], total=1)
    resp = _client(pool).get("/v1/learning/gold-labels")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["preferred"]["name"] == "Kai Wei"
    assert body["items"][0]["change_magnitude"] == 1
    assert body["items"][0]["origin_service"] == "knowledge"
