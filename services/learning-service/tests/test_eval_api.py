"""Q1 — eval-run read API (GET /v1/learning/eval-runs).

TestClient WITHOUT lifespan (no real DB/Redis); routes use dependency_overrides.
Asserts per-owner isolation (the JWT sub is the only user_id ever queried) +
JSONB decode + the 404 path.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.deps import get_current_user, get_db
from app.main import app

USER_ID = uuid.uuid4()
USER_STR = str(USER_ID)
RUN_ID = uuid.uuid4()


class FakeEvalPool:
    """Captures fetch/fetchrow params; returns configurable rows."""

    def __init__(self, *, rows=None, detail=None, results=None):
        self._rows = rows if rows is not None else []
        self._detail = detail
        self._results = results if results is not None else []
        self.fetch_params: list = []
        self.fetchrow_params: list = []

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
        if "FROM eval_results" in sql:
            return self._results
        return self._rows

    async def fetchrow(self, sql, *params):
        self.fetchrow_params.append((sql, params))
        return self._detail


def _run_row(**over):
    base = {
        "eval_run_id": RUN_ID,
        "user_id": USER_ID,
        "project_id": None,
        "book_id": None,
        "source_extraction_run_id": None,
        "config_hash": None,
        "dataset_version": "c74c",
        "source": "baseline",
        # JSONB columns come back as str from asyncpg — exercise the decode path.
        "judges": json.dumps(
            [{"label": "gemma", "uuid": "u-g", "role": "independent",
              "macro_p": 0.876, "macro_r": 0.901, "macro_f1": 0.888}]
        ),
        "disjoint_median_f1": 0.869,
        "full_panel_median_f1": 0.869,
        "fleiss_kappa": None,
        "bootstrap_ci": json.dumps({"low": 0.842, "high": 0.895, "n_common_chapters": 9}),
        "bias_metrics": None,
        "n_chapters": 9,
        "n_disjoint_judges": 2,
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    base.update(over)
    return base


def _client(pool: FakeEvalPool) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: USER_STR
    app.dependency_overrides[get_db] = lambda: pool
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_eval_runs_returns_decoded_rows():
    pool = FakeEvalPool(rows=[_run_row()])
    client = _client(pool)
    resp = client.get("/v1/learning/eval-runs")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["eval_run_id"] == str(RUN_ID)
    assert item["disjoint_median_f1"] == 0.869
    assert item["judges"][0]["macro_f1"] == 0.888          # JSONB decoded
    assert item["bootstrap_ci"]["high"] == 0.895           # JSONB decoded


def test_list_eval_runs_owner_scoped():
    """The only user_id ever sent to SQL is the JWT subject."""
    pool = FakeEvalPool(rows=[])
    client = _client(pool)
    resp = client.get("/v1/learning/eval-runs")
    assert resp.status_code == 200
    assert pool.fetch_params, "a query should have run"
    sql, params = pool.fetch_params[0]
    assert "user_id = $1" in sql
    assert params[0] == USER_ID  # not any caller-supplied value


def test_get_eval_run_404_when_missing():
    pool = FakeEvalPool(detail=None)
    client = _client(pool)
    resp = client.get(f"/v1/learning/eval-runs/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_eval_run_detail_includes_results():
    pool = FakeEvalPool(
        detail=_run_row(),
        results=[
            {"category": "all", "judge_label": "gemma", "judge_uuid": "u-g",
             "precision": 0.876, "recall": 0.901, "f1": 0.888, "chapter_ref": None}
        ],
    )
    client = _client(pool)
    resp = client.get(f"/v1/learning/eval-runs/{RUN_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["eval_run_id"] == str(RUN_ID)
    assert len(body["results"]) == 1
    assert body["results"][0]["f1"] == 0.888
