"""Phase 2b Wave 1 — money-path correctness for the decoupled-extraction consumer.

Covers the two atomic-tx fixes added over WX-T3b (the pure fold SM is covered by
test_decoupled_extract; here we lock the *orchestration* the fixes introduce):

- D-WX-PERSIST-DOUBLE-SPEND: persist_chunk runs cursor-advance + run-emit + spend +
  resume-clear in ONE tx, and a re-read FOR UPDATE skips the whole finalize when a
  concurrent delivery already cleared resume_state (so a redelivery can't re-spend).
- D-WX-TRIO-FANIN-RACE: the trio fold re-reads the row FOR UPDATE and persists the
  MERGED state under the lock, so concurrent relation/event/fact deliveries can't
  lose an op; the terminal persist runs OUTSIDE the lock (never pins a pooled conn
  across the knowledge HTTP call).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app import decoupled_extract as dx
from app.llm_extract_consumer import _persist_chunk, _resume

USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROJ = "99999999-9999-9999-9999-999999999999"
BOOK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CHAP = "11111111-1111-1111-1111-111111111111"
JOB = "22222222-2222-2222-2222-222222222222"
EJ = "33333333-3333-3333-3333-333333333333"


# ── fake asyncpg pool/conn (records SQL + supports acquire()/transaction()) ──────

class _Tx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        self._conn.tx_depth += 1
        return self

    async def __aexit__(self, *exc):
        self._conn.tx_depth -= 1
        return False


class FakeConn:
    def __init__(self, fetchrow_results):
        self._fetchrow_results = list(fetchrow_results)
        self.executed: list[tuple[str, tuple]] = []
        self.fetchrow_calls: list[tuple[str, tuple]] = []
        self.tx_depth = 0
        self.executed_in_tx: list[bool] = []

    async def fetchrow(self, sql, *args):
        self.fetchrow_calls.append((sql, args))
        return self._fetchrow_results.pop(0) if self._fetchrow_results else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        self.executed_in_tx.append(self.tx_depth > 0)

    def transaction(self):
        return _Tx(self)


class _Acq:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, conn, fetch_rows=None):
        self._conn = conn
        self._fetch_rows = fetch_rows or []

    def acquire(self):
        return _Acq(self._conn)

    async def execute(self, sql, *args):
        await self._conn.execute(sql, *args)

    async def fetchrow(self, sql, *args):
        return await self._conn.fetchrow(sql, *args)

    async def fetch(self, sql, *args):
        return list(self._fetch_rows)


def _persist_result():
    return SimpleNamespace(
        entities_merged=2, relations_created=1, events_merged=0, facts_merged=0,
    )


def _persist_rs(stage=dx.PERSIST):
    """A finalize-ready resume_state (empty candidates → empty persist)."""
    return {
        "stage": stage,
        "user_id": USER,
        "entities": [], "relations": [], "events": [], "facts": [],
        "persist_ctx": {
            "project_id": PROJ, "source_type": "chapter", "source_id": CHAP,
            "job_id": JOB, "extraction_model": "m",
        },
        "run_payload": {"run_id": "44444444-4444-4444-4444-444444444444", "metrics": {}},
        "cursor_to_set": {"chapter_index": 1},
        "chapter_extracted": {
            "user_id": USER, "project_id": PROJ, "book_id": BOOK, "chapter_id": CHAP,
        },
    }


def _sqls(conn):
    return " || ".join(s for s, _ in conn.executed)


# ── D-WX-PERSIST-DOUBLE-SPEND ────────────────────────────────────────────────

async def test_persist_chunk_runs_full_finalize_in_one_tx():
    conn = FakeConn([{"resume_state": {"stage": dx.PERSIST}}])  # FOR UPDATE recheck → proceed
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()

    await _persist_chunk(pool, kc, EJ, _persist_rs())

    kc.persist_pass2.assert_awaited_once()              # knowledge MERGE ran (before tx)
    assert "FOR UPDATE" in conn.fetchrow_calls[0][0]    # re-read under lock
    sqls = _sqls(conn)
    assert "current_cursor" in sqls                     # cursor advanced
    assert "outbox_events" in sqls                      # run + chapter_extracted emitted
    assert "current_month_spent_usd" in sqls            # spend recorded
    assert "resume_state=NULL" in sqls                  # resume cleared
    assert all(conn.executed_in_tx), "every finalize write must be inside the tx"


async def test_persist_chunk_skips_spend_when_already_finalized():
    # The redelivery case the fix targets: a concurrent winner already cleared the row.
    conn = FakeConn([{"resume_state": None}])  # FOR UPDATE recheck → already finalized
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()

    await _persist_chunk(pool, kc, EJ, _persist_rs())

    kc.persist_pass2.assert_awaited_once()  # idempotent MERGE still runs (harmless)
    sqls = _sqls(conn)
    assert "current_month_spent_usd" not in sqls   # NO re-spend (the bug)
    assert "current_cursor" not in sqls            # NO re-advance
    assert "resume_state=NULL" not in sqls         # nothing to clear


async def test_persist_chunk_skips_when_row_vanished():
    conn = FakeConn([None])  # row gone entirely
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()

    await _persist_chunk(pool, kc, EJ, _persist_rs())

    assert _sqls(conn) == ""  # no writes at all


# ── D-WX-TRIO-FANIN-RACE ─────────────────────────────────────────────────────

def _trio_rs():
    seed = dx.new_extract_state(
        chunk_text="t", known_entities=[], has_recovery=False, has_filter=False,
    )
    seed = dx.apply_entity_result(seed, ["e1"])             # → TRIO
    seed = dx.begin_trio(seed, {"relation": "jr", "event": "je", "fact": "jf"})
    seed["user_id"] = USER
    return seed


async def test_trio_fold_serialises_under_for_update(monkeypatch):
    fresh = _trio_rs()
    conn = FakeConn([{"resume_state": fresh}])  # the locked re-read
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})

    monkeypatch.setattr(dx, "op_for_job", lambda rs, jid: "event")

    def fake_fold(rs, op, job):  # fold correctness lives in test_decoupled_extract
        rs = dict(rs)
        rs["trio_folded"] = [*rs.get("trio_folded", []), op]  # 1/3 → stays TRIO
        return rs

    monkeypatch.setattr(dx, "fold_trio_job", fake_fold)

    await _resume(pool, kc, llm, None, "je", EJ, _trio_rs())

    assert "FOR UPDATE" in conn.fetchrow_calls[0][0]            # the race guard
    assert any("resume_state=$3" in s for s, _ in conn.executed)  # merged state persisted
    assert all(conn.executed_in_tx)                            # under the lock
    kc.persist_pass2.assert_not_awaited()                      # incomplete → no finalize


async def test_trio_fold_finalizes_outside_lock_when_complete(monkeypatch):
    fresh = _trio_rs()
    # 1st fetchrow = trio lock read; 2nd = persist_chunk's own FOR UPDATE recheck.
    conn = FakeConn([{"resume_state": fresh}, {"resume_state": {"stage": dx.PERSIST}}])
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})

    monkeypatch.setattr(dx, "op_for_job", lambda rs, jid: "fact")

    def fake_fold_complete(rs, op, job):
        rs = {**rs, **_persist_rs(stage=dx.PERSIST)}  # all 3 folded → PERSIST + persist fields
        return rs

    monkeypatch.setattr(dx, "fold_trio_job", fake_fold_complete)

    await _resume(pool, kc, llm, None, "jf", EJ, _trio_rs())

    kc.persist_pass2.assert_awaited_once()         # finalized
    assert "current_month_spent_usd" in _sqls(conn)  # spend recorded once


async def test_trio_fold_skips_when_concurrent_winner_advanced(monkeypatch):
    # Another replica already folded the last op and moved the row past TRIO.
    conn = FakeConn([{"resume_state": {"stage": dx.PERSIST, "trio_jobs": {}}}])
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})

    called = {"fold": False}
    monkeypatch.setattr(dx, "fold_trio_job",
                        lambda *a: called.__setitem__("fold", True) or {})

    await _resume(pool, kc, llm, None, "jf", EJ, _trio_rs())

    assert not called["fold"]            # never folded into a stale rs
    assert _sqls(conn) == ""             # no write
    kc.persist_pass2.assert_not_awaited()


# ── /review-impl finding 3 — REAL fold (not monkeypatched) → finalize boundary ───

def _job(result: dict):
    j = MagicMock()
    j.status = "completed"
    j.result = result
    return j


def _seeded_trio_rs_real():
    """Build a resume_state the way `_start_decoupled_chunk` does (real entity fold +
    begin_trio + the persist seed), with relation+event already folded so the next
    fold completes the fan-in. Uses the REAL dx fold so a future fold refactor that
    dropped the seeded persist keys (persist_ctx/run_payload/cursor_to_set) would
    surface here as a finalize KeyError — the gap the monkeypatched tests can't see."""
    rs = dx.new_extract_state(
        chunk_text="Kai met Bob.", known_entities=[],
        has_recovery=False, has_filter=False,
    )
    rs.update(user_id=USER, project_id=PROJ, model_source="user_model", model_ref="m")
    rs = dx.fold_entity_job(rs, _job({"entities": [
        {"name": "Kai", "kind": "person", "confidence": 0.9},
    ]}))
    rs = dx.begin_trio(rs, {"relation": "jr", "event": "je", "fact": "jf"})
    rs = dx.fold_trio_job(rs, "relation", _job({"relations": []}))  # 1/3
    rs = dx.fold_trio_job(rs, "event", _job({"events": []}))        # 2/3 → still TRIO
    assert rs["stage"] == dx.TRIO
    # the per-chapter persist seed (must survive the real folds to here AND the next one)
    rs.update(
        persist_ctx={
            "project_id": PROJ, "source_type": "chapter", "source_id": CHAP,
            "job_id": JOB, "extraction_model": "m",
        },
        run_payload={"run_id": "44444444-4444-4444-4444-444444444444", "metrics": {}},
        cursor_to_set={"last_chapter_id": CHAP, "scope": "chapters"},
        chapter_extracted={
            "user_id": USER, "project_id": PROJ, "book_id": BOOK, "chapter_id": CHAP,
        },
    )
    return rs


async def test_real_fold_completes_and_finalizes_with_seed_keys_intact():
    rs = _seeded_trio_rs_real()
    conn = FakeConn([
        {"resume_state": rs},                       # trio FOR UPDATE re-read (real rs)
        {"resume_state": {"stage": dx.PERSIST}},    # persist_chunk's recheck → proceed
    ])
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()
    llm = AsyncMock()
    llm.get_job.return_value = _job({"facts": []})  # the 3rd op → completes the fan-in

    # NB: dx.fold_trio_job is the REAL implementation here (no monkeypatch).
    await _resume(pool, kc, llm, None, "jf", EJ, rs)

    # The real fold completed the trio AND the seeded persist keys survived into
    # finalize: persist_chunk ran the full tx without a KeyError.
    kc.persist_pass2.assert_awaited_once()
    sqls = _sqls(conn)
    assert "current_cursor" in sqls and "current_month_spent_usd" in sqls
    assert "resume_state=NULL" in sqls


# ── WX Wave 1b — stuck-resume sweeper ────────────────────────────────────────

import app.llm_extract_consumer as consumer_mod  # noqa: E402
from app.llm_extract_consumer import _sweep_once  # noqa: E402


def _stranded_row(job_ids, stage=dx.TRIO):
    return {
        "id": EJ,
        "provider_job_ids": list(job_ids),
        "resume_state": {"stage": stage, "user_id": USER},
    }


def _spy_resume(monkeypatch):
    calls = []

    async def fake_resume(pool, kc, llm, owner, jid, ej_id, rs):
        calls.append(jid)

    monkeypatch.setattr(consumer_mod, "_resume", fake_resume)
    return calls


async def test_sweep_redrives_a_terminal_job(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["j1"])])
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["j1"]


async def test_sweep_leaves_inflight_job_alone(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["j1"])])
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="running", result=None)  # slow ≠ stuck
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 0 and calls == []


async def test_sweep_tries_next_id_when_get_job_errors(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["bad", "good"])])
    llm = AsyncMock()

    async def get_job(jid, user_id=None):
        if jid == "bad":
            raise RuntimeError("transient")
        return SimpleNamespace(status="completed", result={})

    llm.get_job.side_effect = get_job
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["good"]  # skipped the erroring id, re-drove the next


async def test_sweep_redrives_once_per_row_then_breaks(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["j1", "j2"])])  # both terminal
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["j1"]  # one re-drive advances the row; re-eval next tick


async def test_sweep_query_filters_on_resume_and_idle(monkeypatch):
    captured = {}

    class CapturingPool(FakePool):
        async def fetch(self, sql, *args):
            captured["sql"] = sql
            captured["args"] = args
            return []

    pool = CapturingPool(FakeConn([]))
    await _sweep_once(pool, AsyncMock(), AsyncMock(), timeout_s=900, batch=20)

    sql = captured["sql"]
    assert "resume_state IS NOT NULL" in sql
    assert "make_interval" in sql and "updated_at <" in sql
    assert "status IN ('running', 'paused')" in sql
    assert captured["args"] == (900, 20)
