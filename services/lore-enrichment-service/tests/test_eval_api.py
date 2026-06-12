"""RAID C15 — eval-gate status HTTP handler tests.

Drives the FastAPI HANDLER (not the repo) for the internal eval-gate route
``GET /internal/eval/{project_id}/gate-status`` via TestClient + dependency
overrides. The repo layer (``EvalRunsRepo.get_latest`` Q3 scoping) is covered by
its own DB suite; the GAP here is the HTTP surface:

  * the server-to-server guard (``require_internal_token`` — X-Internal-Token),
  * the FAIL-CLOSED gate invariant: no run -> p2_p3_unlocked=False,
  * the gate reflecting the latest row's ``passed`` (never a false-green).

No DB, no live stack: ``get_eval_runs_repo`` is overridden with a fake repo so
the real ``EvalRunsRepo`` / ``get_db`` is never reached. The correct token is
``settings.internal_service_token`` (conftest sets it to "test_internal_token"
BEFORE app import — do NOT re-set env here).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import eval as eval_api
from app.config import settings
from app.db.repositories.eval_runs import EvalRun

PROJECT = UUID("019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
USER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
GOOD_TOKEN = {"X-Internal-Token": settings.internal_service_token}


class _FakeEvalRunsRepo:
    """Returns the seeded row (or None) from ``get_latest`` — the only method the
    handler calls. Records the kwargs so we can assert the scoping params reach
    the repo."""

    def __init__(self, row: EvalRun | None) -> None:
        self._row = row
        self.calls: list[dict] = []

    async def get_latest(self, *, user_id, project_id, suite_version):
        self.calls.append(
            {"user_id": user_id, "project_id": project_id, "suite_version": suite_version}
        )
        return self._row


def _run(*, passed: bool, suite_version: str = "enrichment-v1") -> EvalRun:
    """A minimal EvalRun row with the gate-relevant fields populated."""
    now = datetime.now(timezone.utc)
    return EvalRun(
        eval_run_id=uuid4(),
        project_id=PROJECT,
        user_id=USER,
        run_id="2026-06-03T00:00:00",
        suite_version=suite_version,
        baseline_version=None,
        n_proposals=10,
        schema_score=0.9,
        canon_score=0.9,
        anachronism_score=0.9,
        provenance_score=0.9,
        usefulness_score=0.9,
        composite=0.9,
        fleiss_kappa=0.71,
        judge_ensemble_acceptable=True,
        passed=passed,
        raw_report={},
        created_at=now,
    )


def _client(repo: _FakeEvalRunsRepo) -> TestClient:
    """A TestClient over just the eval router, with the eval-runs repo dep
    overridden to the fake (no DB / live stack). The internal-token guard remains
    REAL — only the data source is faked."""
    app = FastAPI()
    app.include_router(eval_api.router)
    app.dependency_overrides[eval_api.get_eval_runs_repo] = lambda: repo
    return TestClient(app)


def _get(client: TestClient, *, headers, suite_version: str | None = None):
    params = {"user_id": str(USER)}
    if suite_version is not None:
        params["suite_version"] = suite_version
    return client.get(
        f"/internal/eval/{PROJECT}/gate-status", params=params, headers=headers
    )


# ── FAIL-CLOSED: no eval run yet → gate stays BLOCKED ──────────────────────────


def test_no_run_is_fail_closed_blocked():
    """The load-bearing invariant: when no eval has run (get_latest -> None) the
    gate stays BLOCKED — has_run=False AND p2_p3_unlocked=False. Never a
    false-green when no eval exists."""
    repo = _FakeEvalRunsRepo(None)
    resp = _get(_client(repo), headers=GOOD_TOKEN)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_run"] is False
    assert body["p2_p3_unlocked"] is False
    assert body["suite_version"] == "enrichment-v1"
    # No row → the optional scorecard fields are absent/None (no fabricated data).
    assert body["passed"] is None
    assert body["run_id"] is None


# ── gate reflects the latest row's `passed` (never a false-green) ──────────────


def test_passed_row_unlocks_p2_p3():
    """A latest run with passed=True → p2_p3_unlocked=True (C16/C17 may activate)."""
    repo = _FakeEvalRunsRepo(_run(passed=True))
    resp = _get(_client(repo), headers=GOOD_TOKEN)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_run"] is True
    assert body["passed"] is True
    assert body["p2_p3_unlocked"] is True
    # the scorecard surfaces from the row (not fabricated).
    assert body["composite"] == 0.9
    assert body["run_id"] == repo._row.run_id


def test_failed_row_keeps_gate_blocked():
    """A latest run with passed=False → p2_p3_unlocked=False. The gate reflects
    the row — a failed eval must NEVER unlock the higher-cost tier (no
    false-green)."""
    repo = _FakeEvalRunsRepo(_run(passed=False))
    resp = _get(_client(repo), headers=GOOD_TOKEN)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_run"] is True
    assert body["passed"] is False
    assert body["p2_p3_unlocked"] is False


# ── scoping params reach the repo ──────────────────────────────────────────────


def test_query_params_reach_repo_get_latest():
    """The handler passes the path project_id + the trusted user_id + suite_version
    query params through to the repo's get_latest (the Q3-scoped read)."""
    repo = _FakeEvalRunsRepo(_run(passed=True, suite_version="enrichment-v2"))
    resp = _get(_client(repo), headers=GOOD_TOKEN, suite_version="enrichment-v2")
    assert resp.status_code == 200, resp.text
    assert repo.calls == [
        {"user_id": USER, "project_id": PROJECT, "suite_version": "enrichment-v2"}
    ]
    # the response echoes the row's suite_version.
    assert resp.json()["suite_version"] == "enrichment-v2"


# ── server-to-server guard: X-Internal-Token ───────────────────────────────────


def test_missing_internal_token_is_401():
    """No X-Internal-Token → 401 (server-to-server guard). The repo is never
    reached (the dependency guard rejects before the handler runs)."""
    repo = _FakeEvalRunsRepo(_run(passed=True))
    resp = _get(_client(repo), headers={})
    assert resp.status_code == 401, resp.text
    assert repo.calls == []


def test_wrong_internal_token_is_401():
    """A wrong X-Internal-Token → 401 — the correct token must equal
    settings.internal_service_token for the handler to run."""
    repo = _FakeEvalRunsRepo(_run(passed=True))
    resp = _get(_client(repo), headers={"X-Internal-Token": "not-the-token"})
    assert resp.status_code == 401, resp.text
    assert repo.calls == []
