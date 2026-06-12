"""LLM re-arch Phase 3 M1 — decoupled online-judge state machine.

Unit-tests the SM control flow (plan → submit → fold → advance → finalize, dedup,
supersede, sweep) against a faithful in-memory ``llm_judges`` store + a fake SDK.
The real SQL / FOR UPDATE / ON CONFLICT semantics are covered by the cross-service
live-smoke; ``persist_online_judge`` / ``persist_translation_judge`` are mocked here
(they need real PG) so these tests stay on the SM's logic.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.judges import decoupled_judge as dj

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── in-memory llm_judges store + fake conn/pool ───────────────────────────────


class _Store:
    def __init__(self):
        self.rows: dict = {}              # id -> row dict
        self.dedup: dict = {}             # (kind, dedup_key) -> id

    def insert(self, kind, billing_user_id, judge_model, judge_model_source, rs_json, dedup):
        if (kind, dedup) in self.dedup:
            return None                   # ON CONFLICT DO NOTHING
        rid = uuid.uuid4()
        self.rows[rid] = {
            "id": rid, "kind": kind, "status": "running", "provider_job_id": None,
            "billing_user_id": billing_user_id, "judge_model": judge_model,
            "judge_model_source": judge_model_source,
            "resume_state": json.loads(rs_json), "origin_dedup_key": dedup,
            "result": None, "updated_at": 0,
        }
        self.dedup[(kind, dedup)] = rid
        return rid


class _FakeConn:
    def __init__(self, store):
        self._s = store

    def transaction(self):
        class _Tx:
            async def __aenter__(self_):
                return None

            async def __aexit__(self_, *a):
                return False

        return _Tx()

    async def fetchval(self, sql, *p):
        if "INSERT INTO llm_judges" in sql:
            # (kind, billing_user_id, judge_model, judge_model_source, rs_json, dedup)
            return self._s.insert(p[0], p[1], p[2], p[3], p[4], p[5])
        raise AssertionError(f"unexpected fetchval: {sql[:60]}")

    async def fetchrow(self, sql, *p):
        if "FOR UPDATE" in sql:           # resume: by provider_job_id + running
            for r in self._s.rows.values():
                if r["provider_job_id"] == p[0] and r["status"] == "running":
                    return r
            return None
        raise AssertionError(f"unexpected fetchrow: {sql[:60]}")

    async def execute(self, sql, *p):
        if "SET provider_job_id = $1, resume_state" in sql:   # _dispatch_task
            r = self._s.rows[p[2]]
            r["provider_job_id"] = p[0]
            r["resume_state"] = json.loads(p[1])
        elif "SET resume_state = $1::jsonb" in sql:           # finalize-pending persist
            self._s.rows[p[1]]["resume_state"] = json.loads(p[0])
        else:
            raise AssertionError(f"unexpected execute: {sql[:60]}")
        return "OK"


class _FakePool:
    def __init__(self, store):
        self._s = store

    def acquire(self):
        conn = _FakeConn(self._s)

        class _Acq:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False

        return _Acq()

    async def fetchrow(self, sql, *p):
        if "WHERE id = $1" in sql:                 # _finalize re-read
            return self._s.rows.get(p[0])
        if "provider_job_id = $1 AND status = 'running'" in sql:  # load_for_job
            for r in self._s.rows.values():
                if r["provider_job_id"] == p[0] and r["status"] == "running":
                    return r
            return None
        raise AssertionError(f"unexpected pool.fetchrow: {sql[:60]}")

    async def fetch(self, sql, *p):
        if "status = 'running'" in sql and "updated_at" in sql:   # sweep
            return [r for r in self._s.rows.values() if r["status"] == "running"]
        raise AssertionError(f"unexpected pool.fetch: {sql[:60]}")

    async def fetchval(self, sql, *p):
        if "SET status = 'completed'" in sql and "status = 'running'" in sql:  # _finalize CAS
            r = self._s.rows[p[1]]
            if r["status"] != "running":
                return None                        # lost the completion race
            r["status"] = "completed"
            r["provider_job_id"] = None
            r["result"] = json.loads(p[0]) if p[0] else None
            return r["id"]
        raise AssertionError(f"unexpected pool.fetchval: {sql[:60]}")


class _FakeSdk:
    """submit_job mints sequential job ids; get_job returns a prebuilt terminal job."""

    def __init__(self):
        self.submitted: list = []
        self._jobs: dict = {}             # job_id -> job (for get_job / sweep)

    async def submit_job(self, request, *, user_id=None):
        jid = uuid.uuid4()
        self.submitted.append((jid, request, user_id))
        return SimpleNamespace(job_id=jid)

    async def get_job(self, job_id, *, user_id=None):
        return self._jobs[str(job_id)]


def _terminal_job(job_id, content, status="completed"):
    return SimpleNamespace(
        job_id=job_id, status=status,
        result={"messages": [{"content": content}], "usage": {}},
        is_terminal=lambda: status in ("completed", "failed", "cancelled"),
    )


def _precision_content(n_items, verdict="supported"):
    return json.dumps(
        {"verdicts": [{"idx": i, "verdict": verdict, "reason": "x"} for i in range(n_items)]}
    )


async def _drive(store, sdk, row_id, *, verdict="supported"):
    """Fold every remaining batch via resume() until the row finalizes."""
    while store.rows[row_id]["status"] == "running":
        r = store.rows[row_id]
        rs = r["resume_state"]
        pjid = r["provider_job_id"]
        task = rs["tasks"][rs["cursor"]]
        if rs["kind"] == "extraction":
            content = _precision_content(task["n_items"], verdict)
        else:
            content = '{"score": 0.8, "reason": "ok"}'
        await dj.resume(_FakePool(store), sdk, _terminal_job(pjid, content))


# ── extraction ────────────────────────────────────────────────────────────────


async def test_start_extraction_plans_inserts_and_submits_first_batch(monkeypatch):
    store = _Store()
    sdk = _FakeSdk()
    items = {"entity": [{"name": f"E{i}"} for i in range(4)]}  # 2 batches at size 3
    ok = await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="run-1", owner_user_id="owner-1", billing_user_id="bill-1",
        project_id=None, book_id=None, config_hash="cfg",
        judge_model="jm", judge_model_source="user_model",
        source_text="Alice fell.", items_by_category=items,
    )
    assert ok is True
    assert len(store.rows) == 1
    row = next(iter(store.rows.values()))
    # one batch submitted, provider_job_id persisted, cursor still at 0 (not folded yet)
    assert len(sdk.submitted) == 1
    assert row["provider_job_id"] == sdk.submitted[0][0]
    assert row["resume_state"]["cursor"] == 0
    assert len(row["resume_state"]["tasks"]) >= 1
    assert sdk.submitted[0][2] == "bill-1"  # billed to the BYOK owner


async def test_start_extraction_dedup_second_call_is_noop():
    store = _Store()
    sdk = _FakeSdk()
    items = {"entity": [{"name": "E0"}]}
    kw = dict(
        run_id="run-1", owner_user_id="owner-1", billing_user_id="bill-1",
        project_id=None, book_id=None, config_hash=None,
        judge_model="jm", judge_model_source="user_model",
        source_text="x.", items_by_category=items,
    )
    assert await dj.start_extraction_judge(_FakePool(store), sdk, **kw) is True
    assert await dj.start_extraction_judge(_FakePool(store), sdk, **kw) is False  # ON CONFLICT
    assert len(store.rows) == 1
    assert len(sdk.submitted) == 1  # the dup never submitted a second job


async def test_start_extraction_no_items_returns_false():
    store = _Store()
    sdk = _FakeSdk()
    ok = await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="r", owner_user_id="o", billing_user_id="b",
        project_id=None, book_id=None, config_hash=None,
        judge_model="jm", judge_model_source="user_model",
        source_text="x", items_by_category={"entity": []},
    )
    assert ok is False
    assert not store.rows and not sdk.submitted


async def test_resume_folds_advances_and_finalizes(monkeypatch):
    persisted = {}

    async def _fake_persist_online(pool, **k):
        persisted.update(k)
        return uuid.uuid4()

    monkeypatch.setattr(dj, "persist_online_judge", _fake_persist_online)

    store = _Store()
    sdk = _FakeSdk()
    items = {"entity": [{"name": f"E{i}"} for i in range(4)]}  # 2 batches
    await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="run-1", owner_user_id=str(uuid.uuid4()), billing_user_id="bill-1",
        project_id=None, book_id=None, config_hash="cfg",
        judge_model="jm", judge_model_source="user_model",
        source_text="Alice fell.", items_by_category=items,
    )
    row_id = next(iter(store.rows))
    n_tasks = len(store.rows[row_id]["resume_state"]["tasks"])

    await _drive(store, sdk, row_id, verdict="supported")

    row = store.rows[row_id]
    assert row["status"] == "completed"
    assert row["provider_job_id"] is None
    # one submit per batch (the SM dispatched the next under the lock each fold)
    assert len(sdk.submitted) == n_tasks
    # all 4 items judged "supported" → overall precision 1.0
    assert persisted["judge_result"]["overall_precision"] == 1.0
    assert persisted["judge_result"]["n_judged"] == 4
    assert persisted["run_id"] == "run-1"


async def test_resume_superseded_job_is_noop(monkeypatch):
    async def _noop(pool, **k):
        return None

    monkeypatch.setattr(dj, "persist_online_judge", _noop)
    store = _Store()
    sdk = _FakeSdk()
    await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="run-1", owner_user_id="o", billing_user_id="b",
        project_id=None, book_id=None, config_hash=None,
        judge_model="jm", judge_model_source="user_model",
        source_text="x.", items_by_category={"entity": [{"name": "E0"}]},
    )
    row_id = next(iter(store.rows))
    # a terminal for a job id that no running row points at → no-op
    stale = _terminal_job(uuid.uuid4(), _precision_content(1))
    await dj.resume(_FakePool(store), sdk, stale)
    assert store.rows[row_id]["status"] == "running"  # untouched


# ── translation ───────────────────────────────────────────────────────────────


async def test_translation_single_batch_finalizes_and_emits(monkeypatch):
    persisted = {}
    emitted = {}

    async def _fake_persist_transl(pool, **k):
        persisted.update(k)
        return True

    async def _fake_emit(eval_payload, verdict):
        emitted["payload"] = eval_payload
        emitted["score"] = verdict.score

    monkeypatch.setattr(dj, "persist_translation_judge", _fake_persist_transl)
    monkeypatch.setattr(dj, "_emit_eval_judged", _fake_emit)

    store = _Store()
    sdk = _FakeSdk()
    owner = str(uuid.uuid4())
    ok = await dj.start_translation_judge(
        _FakePool(store), sdk,
        ct_id="ct-1", owner_user_id=owner, billing_user_id=owner,
        book_id=None, origin_event_id="ob-1",
        judge_model="cj", judge_model_source="user_model",
        source_text="他来了。", translated_text="Anh ấy đã đến.",
        emit_eval_judged=True, eval_payload={"chapter_id": "ch-1"},
    )
    assert ok is True
    row_id = next(iter(store.rows))
    assert len(store.rows[row_id]["resume_state"]["tasks"]) == 1

    await _drive(store, sdk, row_id)

    row = store.rows[row_id]
    assert row["status"] == "completed"
    assert persisted["ct_id"] == "ct-1"
    assert persisted["origin_event_id"] == "ob-1"
    assert abs(persisted["verdict"].score - 0.8) < 1e-9
    assert emitted["score"] == 0.8                 # campaign judge → eval_judged emitted
    assert emitted["payload"]["chapter_id"] == "ch-1"


async def test_translation_no_emit_when_not_campaign(monkeypatch):
    async def _noop_persist(pool, **k):
        return True

    monkeypatch.setattr(dj, "persist_translation_judge", _noop_persist)
    called = {"emit": False}

    async def _fake_emit(*a, **k):
        called["emit"] = True

    monkeypatch.setattr(dj, "_emit_eval_judged", _fake_emit)
    store = _Store()
    sdk = _FakeSdk()
    owner = str(uuid.uuid4())
    await dj.start_translation_judge(
        _FakePool(store), sdk,
        ct_id="ct-1", owner_user_id=owner, billing_user_id=owner,
        book_id=None, origin_event_id="ob-2",
        judge_model="gm", judge_model_source="user_model",
        source_text="x", translated_text="y",
        emit_eval_judged=False, eval_payload={},
    )
    await _drive(store, sdk, next(iter(store.rows)))
    assert called["emit"] is False                 # global-config judge stays telemetry-only


async def test_translation_blank_text_returns_false():
    store = _Store()
    sdk = _FakeSdk()
    ok = await dj.start_translation_judge(
        _FakePool(store), sdk,
        ct_id="ct", owner_user_id="o", billing_user_id="o",
        book_id=None, origin_event_id="ob",
        judge_model="m", judge_model_source="user_model",
        source_text="   ", translated_text="y",
        emit_eval_judged=False, eval_payload={},
    )
    assert ok is False and not store.rows


# ── load_for_job + sweeper ────────────────────────────────────────────────────


async def test_load_for_job_none_for_unknown():
    store = _Store()
    assert await dj.load_for_job(_FakePool(store), str(uuid.uuid4())) is None
    assert await dj.load_for_job(_FakePool(store), "not-a-uuid") is None


async def test_failed_job_folds_as_unjudged(monkeypatch):
    """A non-completed terminal (failed/cancelled, result=None) folds as empty content
    → unjudged; the run finalizes with overall precision None (best-effort)."""
    persisted = {}

    async def _fake_persist_online(pool, **k):
        persisted.update(k)
        return uuid.uuid4()

    monkeypatch.setattr(dj, "persist_online_judge", _fake_persist_online)
    store = _Store()
    sdk = _FakeSdk()
    await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="run-1", owner_user_id=str(uuid.uuid4()), billing_user_id="b",
        project_id=None, book_id=None, config_hash=None,
        judge_model="jm", judge_model_source="user_model",
        source_text="x.", items_by_category={"entity": [{"name": "E0"}]},  # 1 batch
    )
    row_id = next(iter(store.rows))
    pjid = store.rows[row_id]["provider_job_id"]
    failed = SimpleNamespace(job_id=pjid, status="failed", result=None,
                             is_terminal=lambda: True)
    await dj.resume(_FakePool(store), sdk, failed)
    assert store.rows[row_id]["status"] == "completed"
    assert persisted["judge_result"]["overall_precision"] is None
    assert persisted["judge_result"]["n_judged"] == 0


async def test_sweeper_finalizes_pending_row(monkeypatch):
    """Crash AFTER the last fold committed but BEFORE finalize (cursor==len, status
    still 'running', provider_job_id still set) → the sweeper takes the finalize-pending
    branch and completes the row WITHOUT a redundant get_job."""
    persisted = {}

    async def _fake_persist_online(pool, **k):
        persisted.update(k)
        return uuid.uuid4()

    monkeypatch.setattr(dj, "persist_online_judge", _fake_persist_online)
    store = _Store()
    sdk = _FakeSdk()  # empty _jobs → get_job would KeyError if (wrongly) called
    await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="run-1", owner_user_id=str(uuid.uuid4()), billing_user_id="b",
        project_id=None, book_id=None, config_hash=None,
        judge_model="jm", judge_model_source="user_model",
        source_text="x.", items_by_category={"entity": [{"name": "E0"}]},  # 1 batch
    )
    row = next(iter(store.rows.values()))
    rs = row["resume_state"]
    rs["accum"] = {"entity": [{"idx": 0, "verdict": "supported", "reason": "x"}]}
    rs["cursor"] = len(rs["tasks"])  # folded, finalize-pending
    n = await dj.sweep_once(_FakePool(store), sdk, timeout_s=0, batch=10)
    assert n == 1
    assert row["status"] == "completed"
    assert persisted["judge_result"]["overall_precision"] == 1.0


async def test_finalize_not_re_emitted_after_completion(monkeypatch):
    """/review-impl MED#1 regression-lock: a re-drive / redelivery after the row is
    completed must NOT re-emit translation.eval_judged (the CAS-on-completion guard)."""
    async def _noop_persist(pool, **k):
        return True

    monkeypatch.setattr(dj, "persist_translation_judge", _noop_persist)
    emits = {"n": 0}

    async def _fake_emit(*a, **k):
        emits["n"] += 1

    monkeypatch.setattr(dj, "_emit_eval_judged", _fake_emit)
    store = _Store()
    sdk = _FakeSdk()
    owner = str(uuid.uuid4())
    await dj.start_translation_judge(
        _FakePool(store), sdk,
        ct_id="ct-1", owner_user_id=owner, billing_user_id=owner,
        book_id=None, origin_event_id="ob-1",
        judge_model="cj", judge_model_source="user_model",
        source_text="他来了。", translated_text="Anh.",
        emit_eval_judged=True, eval_payload={},
    )
    row_id = next(iter(store.rows))
    await _drive(store, sdk, row_id)        # completes + emits once
    assert emits["n"] == 1
    await dj._finalize(_FakePool(store), row_id)   # re-drive on the completed row
    assert emits["n"] == 1                  # CAS guard → no second emit


async def test_sweep_redrives_terminal_job(monkeypatch):
    persisted = {}

    async def _fake_persist_online(pool, **k):
        persisted.update(k)
        return uuid.uuid4()

    monkeypatch.setattr(dj, "persist_online_judge", _fake_persist_online)

    store = _Store()
    sdk = _FakeSdk()
    await dj.start_extraction_judge(
        _FakePool(store), sdk,
        run_id="run-1", owner_user_id=str(uuid.uuid4()), billing_user_id="b",
        project_id=None, book_id=None, config_hash=None,
        judge_model="jm", judge_model_source="user_model",
        source_text="x.", items_by_category={"entity": [{"name": "E0"}]},  # 1 batch
    )
    row = next(iter(store.rows.values()))
    # register the in-flight job as terminal so the sweeper's get_job sees it
    sdk._jobs[str(row["provider_job_id"])] = _terminal_job(
        row["provider_job_id"], _precision_content(1, "supported"),
    )
    n = await dj.sweep_once(_FakePool(store), sdk, timeout_s=0, batch=10)
    assert n == 1
    assert row["status"] == "completed"
    assert persisted["judge_result"]["overall_precision"] == 1.0
