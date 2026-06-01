"""Q1 — eval-result persistence + score_config validation.

Mock-based (no real DB): a FakeConn/FakePool captures the SQL + params so we
assert the right rows are written, validation fails before any write, and the
re-score path replaces children.
"""

from __future__ import annotations

import uuid

import pytest

from loreweave_eval.scorer import EvalResult, JudgeScore

from app.db.eval_repo import (
    SCORE_CONFIG_SEED,
    ScoreValidationError,
    _build_scores,
    _validate_score,
    persist_eval_result,
)

USER_ID = uuid.uuid4()
RUN_UUID = uuid.uuid4()


# ── fakes ─────────────────────────────────────────────────────────────


def _cfg_rows() -> list[dict]:
    return [
        {
            "name": s["name"],
            "data_type": s["data_type"],
            "min_value": s.get("min_value"),
            "max_value": s.get("max_value"),
            "categories": None,
        }
        for s in SCORE_CONFIG_SEED
    ]


class FakeConn:
    def __init__(self, *, eval_run_id=RUN_UUID, cfg_rows=None):
        self._eval_run_id = eval_run_id
        self._cfg = cfg_rows if cfg_rows is not None else _cfg_rows()
        self.execs: list[tuple] = []
        self.fetchrows: list[tuple] = []

    def transaction(self):
        class _T:
            async def __aenter__(s):
                return None

            async def __aexit__(s, *a):
                return False

        return _T()

    async def fetch(self, sql, *params):
        if "FROM score_config" in sql:
            return self._cfg
        return []

    async def fetchrow(self, sql, *params):
        self.fetchrows.append((sql, params))
        return {"eval_run_id": self._eval_run_id}

    async def execute(self, sql, *params):
        self.execs.append((sql, params))
        return "OK"


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _A:
            async def __aenter__(s):
                return conn

            async def __aexit__(s, *a):
                return False

        return _A()


def _result(*, gemma_f1=0.888, phi4_f1=0.851, disjoint=0.869, fleiss=None) -> EvalResult:
    return EvalResult(
        variant_label="c74c",
        per_judge=[
            JudgeScore("gemma", "uuid-gemma", "independent", 0.876, 0.901, gemma_f1),
            JudgeScore("phi4", "uuid-phi4", "independent", 0.851, 0.850, phi4_f1),
        ],
        full_panel_median_f1=disjoint,
        disjoint_median_f1=disjoint,
        disjoint_ci_low=0.842,
        disjoint_ci_high=0.895,
        n_disjoint_judges=2,
        n_common_chapters=9,
        fleiss_kappa=fleiss,
        n_judges_total=2,
    )


def _count(execs, needle: str) -> int:
    return sum(1 for sql, _ in execs if needle in sql)


# ── _validate_score ───────────────────────────────────────────────────


def test_validate_rejects_unknown_metric():
    with pytest.raises(ScoreValidationError):
        _validate_score({}, "nope", 0.5, None)


def test_validate_rejects_out_of_range():
    cfgs = {"macro_f1": {"data_type": "numeric", "min_value": 0.0, "max_value": 1.0, "categories": None}}
    with pytest.raises(ScoreValidationError):
        _validate_score(cfgs, "macro_f1", 1.5, None)
    with pytest.raises(ScoreValidationError):
        _validate_score(cfgs, "macro_f1", -0.1, None)


def test_validate_accepts_in_range_and_kappa():
    cfgs = {
        "macro_f1": {"data_type": "numeric", "min_value": 0.0, "max_value": 1.0, "categories": None},
        "fleiss_kappa": {"data_type": "numeric", "min_value": -1.0, "max_value": 1.0, "categories": None},
    }
    assert _validate_score(cfgs, "macro_f1", 0.869, None) == "numeric"
    assert _validate_score(cfgs, "fleiss_kappa", -0.3, None) == "numeric"


def test_build_scores_shape():
    scores = _build_scores(_result(fleiss=0.71))
    metrics = [m for m, *_ in scores]
    assert metrics.count("macro_f1") == 2  # one per judge
    assert "disjoint_median_f1" in metrics
    assert "full_panel_median_f1" in metrics
    assert "fleiss_kappa" in metrics


# ── persist_eval_result ───────────────────────────────────────────────


async def test_persist_writes_run_results_and_scores():
    conn = FakeConn()
    rid = await persist_eval_result(
        FakePool(conn), _result(), user_id=USER_ID, dataset_version="c74c",
        source="baseline", idempotency_key="baseline:c74c",
    )
    assert rid == RUN_UUID
    # 1 eval_runs INSERT (fetchrow), 2 eval_results, 4 quality_scores (2 macro + disjoint + full)
    assert len(conn.fetchrows) == 1
    assert "INSERT INTO eval_runs" in conn.fetchrows[0][0]
    assert _count(conn.execs, "INSERT INTO eval_results") == 2
    assert _count(conn.execs, "INSERT INTO quality_scores") == 4
    # re-score replaces children
    assert _count(conn.execs, "DELETE FROM eval_results") == 1
    assert _count(conn.execs, "DELETE FROM quality_scores") == 1


async def test_persist_validation_fails_before_any_write():
    """An out-of-range judge F1 must raise BEFORE the eval_runs INSERT — no
    partial rows."""
    conn = FakeConn()
    with pytest.raises(ScoreValidationError):
        await persist_eval_result(
            FakePool(conn), _result(gemma_f1=1.5), user_id=USER_ID,
        )
    assert conn.fetchrows == []  # eval_runs INSERT never reached
    assert conn.execs == []
