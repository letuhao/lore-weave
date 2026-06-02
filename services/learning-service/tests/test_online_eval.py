"""Q4 — online structural eval: signal, sampling, persistence."""

from __future__ import annotations

import uuid

import pytest

from app.db.eval_repo import SCORE_CONFIG_SEED, ScoreValidationError
from app.db.online_eval import (
    extract_run_fields,
    persist_online_eval,
    should_sample,
    structural_completeness,
)

RUN_UUID = uuid.uuid4()


# ── structural_completeness ───────────────────────────────────────────


def test_completeness_full_yield():
    m = {"entities_merged": 5, "relations_created": 3, "events_merged": 2, "facts_merged": 1}
    assert structural_completeness(m) == 1.0


def test_completeness_partial():
    assert structural_completeness({"entities_merged": 5}) == pytest.approx(1 / 3)


def test_completeness_zero_or_empty():
    assert structural_completeness({}) == 0.0
    assert structural_completeness({"entities_merged": 0, "relations_created": 0, "events_merged": 0}) == 0.0
    assert structural_completeness(None) == 0.0


# ── should_sample ─────────────────────────────────────────────────────


def test_sample_rate_extremes():
    assert should_sample("any", 1.0) is True
    assert should_sample("any", 0.0) is False


def test_sample_deterministic():
    rid = str(uuid.uuid4())
    assert should_sample(rid, 0.5) == should_sample(rid, 0.5)


def test_sample_rate_distribution():
    ids = [str(uuid.uuid4()) for _ in range(2000)]
    hits = sum(1 for i in ids if should_sample(i, 0.25))
    # loose bound — deterministic hash, ~25%
    assert 0.18 < hits / len(ids) < 0.32


# ── extract_run_fields ────────────────────────────────────────────────


def test_extract_fields_valid():
    uid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    f = extract_run_fields({"run_id": rid, "user_id": uid, "metrics": {"entities_merged": 1}})
    assert f is not None
    assert f["run_id"] == rid
    assert str(f["user_id"]) == uid
    assert f["metrics"] == {"entities_merged": 1}


def test_extract_fields_missing_or_bad():
    assert extract_run_fields({"user_id": str(uuid.uuid4())}) is None  # no run_id
    assert extract_run_fields({"run_id": "not-a-uuid", "user_id": str(uuid.uuid4())}) is None


# ── persist_online_eval (mock conn) ───────────────────────────────────


def _cfg_rows():
    return [
        {"name": s["name"], "data_type": s["data_type"], "min_value": s.get("min_value"),
         "max_value": s.get("max_value"), "categories": None}
        for s in SCORE_CONFIG_SEED
    ]


class FakeConn:
    def __init__(self, eval_run_id=RUN_UUID):
        self._eval_run_id = eval_run_id
        self._cfg = _cfg_rows()
        self.execs: list = []

    def transaction(self):
        class _T:
            async def __aenter__(s):
                return None

            async def __aexit__(s, *a):
                return False

        return _T()

    async def fetch(self, sql, *params):
        return self._cfg if "FROM score_config" in sql else []

    async def fetchrow(self, sql, *params):
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


def _count(execs, needle):
    return sum(1 for sql, _ in execs if needle in sql)


async def test_persist_writes_online_run_and_score():
    conn = FakeConn()
    rid = await persist_online_eval(
        FakePool(conn), run_id=str(RUN_UUID), user_id=uuid.uuid4(),
        completeness=1.0, origin_event_id="ob-1",
    )
    assert rid == RUN_UUID
    assert _count(conn.execs, "DELETE FROM quality_scores") == 1
    inserts = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(inserts) == 1
    # params: (target_id=run_id, user_id, metric_name, value_num, data_type, eval_run_id)
    p = inserts[0][1]
    assert p[2] == "online_structural_completeness"
    assert p[3] == 1.0


async def test_persist_validates_completeness_range():
    conn = FakeConn()
    with pytest.raises(ScoreValidationError):
        await persist_online_eval(
            FakePool(conn), run_id=str(RUN_UUID), user_id=uuid.uuid4(), completeness=1.5,
        )
    assert conn.execs == []  # validation before any write
