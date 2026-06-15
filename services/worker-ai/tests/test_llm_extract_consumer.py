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

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app import decoupled_extract as dx
from app.llm_extract_consumer import (
    DEFAULT_DECOUPLED_SUBMIT_CAP,
    _persist_chunk,
    _resume,
    _submit_map,
)

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


# ── D-WX-RUN-SAMPLE-DECOUPLE ─────────────────────────────────────────────────

async def test_persist_chunk_writes_run_sample_when_opted_in():
    """An opted-in project (save_raw_extraction) writes the extraction_run_sample at
    finalize, keyed by the run_payload's run_id, on `pool` OUTSIDE the finalize tx
    (a swallowed best-effort error inside the tx would poison it)."""
    conn = FakeConn([{"resume_state": {"stage": dx.PERSIST}}])
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()
    rs = _persist_rs()
    rs["save_raw_extraction"] = True
    rs["chunk_text"] = "Alice fell down the hole."

    await _persist_chunk(pool, kc, EJ, rs)

    sample_idx = next(
        i for i, (s, _) in enumerate(conn.executed)
        if "extraction_run_samples" in s
    )
    cursor_idx = next(
        i for i, (s, _) in enumerate(conn.executed) if "current_cursor" in s
    )
    assert sample_idx < cursor_idx                      # sample before the event/tx
    assert conn.executed_in_tx[sample_idx] is False     # written OUTSIDE the finalize tx
    sample_args = conn.executed[sample_idx][1]
    assert str(sample_args[0]) == rs["run_payload"]["run_id"]  # same run_id as the event
    assert sample_args[6] == "Alice fell down the hole."       # source_text


async def test_persist_chunk_skips_run_sample_when_not_opted():
    conn = FakeConn([{"resume_state": {"stage": dx.PERSIST}}])
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()

    await _persist_chunk(pool, kc, EJ, _persist_rs())  # no save_raw_extraction

    assert "extraction_run_samples" not in _sqls(conn)


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


# ── D-WX-TRIO-FANIN-RACE (entity stage) — the entity fold is now under FOR UPDATE ──

async def test_entity_fold_skips_when_superseded():
    # The entity-stage claim: provider_job_ids no longer contains this entity job (a
    # concurrent driver — the sweeper, or another replica — already folded + advanced
    # it), so the FOR UPDATE claim returns None → skip, no double trio-submit.
    conn = FakeConn([None])  # claim returns no row
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})

    await _resume(pool, kc, llm, None, "entity-job", EJ, {"stage": dx.ENTITY, "user_id": USER})

    assert "FOR UPDATE" in conn.fetchrow_calls[0][0]
    assert "provider_job_ids @>" in conn.fetchrow_calls[0][0]  # the claim
    llm.submit_job.assert_not_awaited()   # no double trio-submit
    kc.persist_pass2.assert_not_awaited()
    assert conn.executed == []


async def test_entity_fold_under_lock_submits_trio(monkeypatch):
    conn = FakeConn([{"resume_state": {"stage": dx.ENTITY, "user_id": USER}}])  # claim matches
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    llm.submit_job = AsyncMock(side_effect=[SimpleNamespace(job_id=f"t{i}") for i in range(3)])
    monkeypatch.setattr(dx, "fold_entity_job", lambda rs, job: {**rs, "stage": dx.TRIO})
    monkeypatch.setattr(dx, "assemble_trio_submits",
                        lambda rs: {"relation": {}, "event": {}, "fact": {}})
    monkeypatch.setattr(dx, "begin_trio", lambda rs, tj: {**rs, "trio_jobs": tj})

    await _resume(pool, kc, llm, None, "entity-job", EJ, {"stage": dx.ENTITY, "user_id": USER})

    assert llm.submit_job.await_count == 3              # 3 trio jobs submitted
    assert any("resume_state=$3" in s for s, _ in conn.executed)  # in-flight persisted
    assert all(conn.executed_in_tx)                     # under the lock
    kc.persist_pass2.assert_not_awaited()               # not finalized (TRIO not complete)


# ── D-C12-CONCURRENCY-DECOUPLED — concurrency_level bounds the submit fan-out ─────
# C12's concurrency_level capped the SDK *sync* gather Semaphore but NOT the decoupled
# trio submit fan-out (fire-and-forget, no gather). These lock that the decoupled path
# now honours the same knob: _submit_map gates concurrent in-flight submits to N.

class _ConcurrencyRecorder:
    """A fake submit_job that records the peak number of submits in flight at once.
    Each call enters, bumps the live counter, yields the loop so a bounded gather can
    interleave (proving the Semaphore actually limits overlap), then exits."""

    def __init__(self):
        self.live = 0
        self.max_live = 0
        self.total = 0
        self._n = 0

    async def __call__(self, *, user_id, **kwargs):
        self.live += 1
        self.total += 1
        self.max_live = max(self.max_live, self.live)
        try:
            # yield twice so all admitted coros pile up before any releases — without
            # a Semaphore every coro would be admitted ⇒ max_live == fan-out size.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        finally:
            self.live -= 1
        self._n += 1
        return SimpleNamespace(job_id=f"t{self._n}")


async def test_submit_map_bounds_inflight_to_concurrency_level():
    """_submit_map with concurrency_level=2 over a 5-way fan-out never runs >2 submits
    concurrently, yet submits all 5 (a precise wiring/spy assertion on the bound)."""
    rec = _ConcurrencyRecorder()
    llm = AsyncMock()
    llm.submit_job = rec
    rs = {"user_id": USER, "concurrency_level": 2}
    submits = {f"k{i}": {"operation": "chat"} for i in range(5)}

    jobs = await _submit_map(llm, rs, submits)

    assert rec.total == 5                       # all 5 submitted
    assert len(jobs) == 5                        # all mapped key→job_id
    assert rec.max_live <= 2                      # never more than N in flight at once
    assert rec.max_live == 2                      # AND the cap is actually saturated


async def test_submit_map_applies_default_cap_when_unset():
    """D-078: no concurrency_level ⇒ the DEFAULT cap, NOT unbounded. A fan-out larger
    than the default never runs more than `DEFAULT_DECOUPLED_SUBMIT_CAP` in flight, yet
    submits them all (was: every submit concurrent at once)."""
    rec = _ConcurrencyRecorder()
    llm = AsyncMock()
    llm.submit_job = rec
    rs = {"user_id": USER}  # NO concurrency_level key (legacy / synthetic resume blob)
    fan_out = DEFAULT_DECOUPLED_SUBMIT_CAP + 3
    submits = {f"k{i}": {"operation": "chat"} for i in range(fan_out)}

    jobs = await _submit_map(llm, rs, submits)

    assert rec.total == fan_out and len(jobs) == fan_out  # all submitted
    assert rec.max_live <= DEFAULT_DECOUPLED_SUBMIT_CAP    # never exceeds the default cap
    assert rec.max_live == DEFAULT_DECOUPLED_SUBMIT_CAP    # AND the cap is saturated


async def test_submit_map_default_cap_for_zero_none_negative():
    """D-078: concurrency_level of 0 / None / a negative is invalid as a cap ⇒ the
    DEFAULT cap applies (not unbounded)."""
    fan_out = DEFAULT_DECOUPLED_SUBMIT_CAP + 2
    for bad in (0, None, -3):
        rec = _ConcurrencyRecorder()
        llm = AsyncMock()
        llm.submit_job = rec
        rs = {"user_id": USER, "concurrency_level": bad}
        submits = {f"k{i}": {"operation": "chat"} for i in range(fan_out)}
        await _submit_map(llm, rs, submits)
        assert rec.max_live == DEFAULT_DECOUPLED_SUBMIT_CAP, (
            f"concurrency_level={bad!r} should fall back to the default cap"
        )


async def test_entity_fold_trio_submit_respects_concurrency_level(monkeypatch):
    """The live trio submit site (entity→trio under the row lock) routes through the
    bounded _submit_map, so a 3-op trio with concurrency_level=1 serialises the submits
    (max_live==1) while still submitting all three and recording all three job ids."""
    rec = _ConcurrencyRecorder()
    seed = {"stage": dx.ENTITY, "user_id": USER, "concurrency_level": 1}
    conn = FakeConn([{"resume_state": dict(seed)}])  # claim matches
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    llm.submit_job = rec
    monkeypatch.setattr(dx, "fold_entity_job",
                        lambda rs, job: {**rs, "stage": dx.TRIO})
    monkeypatch.setattr(dx, "assemble_trio_submits",
                        lambda rs: {"relation": {}, "event": {}, "fact": {}})
    captured = {}
    monkeypatch.setattr(dx, "begin_trio",
                        lambda rs, tj: captured.update(trio_jobs=tj) or {**rs, "trio_jobs": tj})

    await _resume(pool, kc, llm, None, "entity-job", EJ, dict(seed))

    assert rec.total == 3                          # 3 trio jobs submitted
    assert rec.max_live == 1                        # concurrency_level=1 → fully serial
    assert len(captured["trio_jobs"]) == 3          # all 3 ids recorded (ops unchanged)
    assert set(captured["trio_jobs"]) == {"relation", "event", "fact"}


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


# ── WX Wave 4 — recovery/filter stage dispatch (orchestration, not fold) ─────────
# Fold/finalize correctness lives in test_decoupled_extract; here we lock that the
# consumer, on a stage COMPLETING, submits the next fan-out UNDER the lock (or persists),
# exactly like the entity→trio transition.

def _trio_complete_rs(has_recovery=False, has_filter=False):
    rs = dx.new_extract_state(
        chunk_text="t", known_entities=[], has_recovery=has_recovery, has_filter=has_filter,
    )
    rs = dx.apply_entity_result(rs, ["e1"])
    rs = dx.begin_trio(rs, {"relation": "jr", "event": "je", "fact": "jf"})
    rs["user_id"] = USER
    return rs


async def test_trio_complete_dispatches_recovery_under_lock(monkeypatch):
    fresh = _trio_complete_rs(has_recovery=True)
    conn = FakeConn([{"resume_state": fresh}])  # trio FOR UPDATE re-read
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    llm.submit_job = AsyncMock(return_value=SimpleNamespace(job_id="rjob0"))
    monkeypatch.setattr(dx, "op_for_job", lambda rs, jid: "fact")
    monkeypatch.setattr(dx, "fold_trio_job", lambda rs, op, job: {**rs, "stage": dx.RECOVERY})
    monkeypatch.setattr(dx, "assemble_recovery",
                        lambda rs: ({"r0": {"operation": "chat"}}, {**rs, "stage": dx.RECOVERY}))

    await _resume(pool, kc, llm, None, "jf", EJ, _trio_complete_rs(has_recovery=True))

    llm.submit_job.assert_awaited_once()                          # recovery batch submitted
    assert any("provider_job_ids" in s and "resume_state=$3" in s for s, _ in conn.executed)
    assert all(conn.executed_in_tx)                               # under the lock
    kc.persist_pass2.assert_not_awaited()                         # recovery in flight, not done


async def test_recovery_complete_dispatches_filter(monkeypatch):
    base = dx.new_extract_state(
        chunk_text="t", known_entities=[], has_recovery=True, has_filter=True,
    )
    base["stage"] = dx.RECOVERY
    base["user_id"] = USER
    base = dx.begin_recovery(base, {"r0": "rj0"})
    conn = FakeConn([{"resume_state": base}])
    pool = FakePool(conn)
    kc = AsyncMock()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    llm.submit_job = AsyncMock(return_value=SimpleNamespace(job_id="fjob0"))
    monkeypatch.setattr(dx, "recovery_task_for_job", lambda rs, jid: "r0")
    monkeypatch.setattr(dx, "fold_recovery_terminal", lambda rs, k, job: {**rs, "stage": dx.FILTER})
    monkeypatch.setattr(dx, "assemble_filter",
                        lambda rs: ({"f:entity:0": {"operation": "chat"}}, {**rs, "stage": dx.FILTER}))

    await _resume(pool, kc, llm, None, "rj0", EJ, {**base})

    llm.submit_job.assert_awaited_once()                          # filter batch submitted
    kc.persist_pass2.assert_not_awaited()


async def test_filter_complete_finalizes_and_persists(monkeypatch):
    base = dx.new_extract_state(
        chunk_text="t", known_entities=[], has_recovery=False, has_filter=True,
    )
    base["stage"] = dx.FILTER
    base.update(_persist_rs(stage=dx.FILTER))
    base = dx.begin_filter(base, {"f:entity:0": "fj0"})
    conn = FakeConn([{"resume_state": base}, {"resume_state": {"stage": dx.PERSIST}}])
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    monkeypatch.setattr(dx, "filter_task_for_job", lambda rs, jid: "f:entity:0")
    monkeypatch.setattr(dx, "fold_filter_terminal", lambda rs, k, job: {**rs, "stage": dx.PERSIST})
    captured = {}
    monkeypatch.setattr(dx, "finalize_filter",
                        lambda rs: captured.update(called=True) or rs)

    await _resume(pool, kc, llm, None, "fj0", EJ, {**base})

    assert captured.get("called")                                 # filter stitch applied
    kc.persist_pass2.assert_awaited_once()                        # then finalized
    assert "current_month_spent_usd" in _sqls(conn)               # spend recorded once


async def test_empty_recovery_advances_through_to_persist(monkeypatch):
    # has_recovery, but assemble_recovery finds no Tier-3 work AND no filter → the
    # dispatcher walks RECOVERY→PERSIST in one pass, no submit, finalize directly.
    base = _trio_complete_rs(has_recovery=True, has_filter=False)
    conn = FakeConn([{"resume_state": base}, {"resume_state": {"stage": dx.PERSIST}}])
    pool = FakePool(conn)
    kc = AsyncMock()
    kc.persist_pass2.return_value = _persist_result()
    llm = AsyncMock()
    llm.get_job.return_value = SimpleNamespace(status="completed", result={})
    llm.submit_job = AsyncMock()
    monkeypatch.setattr(dx, "op_for_job", lambda rs, jid: "fact")
    monkeypatch.setattr(dx, "fold_trio_job",
                        lambda rs, op, job: {**rs, **_persist_rs(stage=dx.RECOVERY)})
    monkeypatch.setattr(dx, "assemble_recovery", lambda rs: ({}, rs))  # no Tier-3 work

    await _resume(pool, kc, llm, None, "jf", EJ, {**base})

    llm.submit_job.assert_not_awaited()                           # nothing to submit
    kc.persist_pass2.assert_awaited_once()                        # advanced through to persist


# ── WX Wave 1b — stuck-resume sweeper ────────────────────────────────────────

import app.llm_extract_consumer as consumer_mod  # noqa: E402
from app.llm_extract_consumer import _sweep_once  # noqa: E402


def _stranded_row(job_ids, stage=dx.TRIO):
    # extraction_jobs is keyed by job_id (NO surrogate `id` column — live-smoke caught this).
    return {
        "job_id": EJ,
        "provider_job_ids": list(job_ids),
        "resume_state": {"stage": stage, "user_id": USER},
    }


def _spy_resume(monkeypatch):
    calls = []

    async def fake_resume(pool, kc, llm, owner, jid, ej_id, rs):
        calls.append(jid)

    monkeypatch.setattr(consumer_mod, "_resume", fake_resume)
    return calls


def _sdk_job(status, result=None):
    """A get_job return that mirrors the SDK Job's is_terminal() predicate — the
    sweeper now keys on job.is_terminal(), not a hardcoded status set (review-impl)."""
    return SimpleNamespace(
        status=status,
        result={} if result is None else result,
        is_terminal=lambda: status in ("completed", "failed", "cancelled"),
    )


async def test_sweep_redrives_a_terminal_job(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["j1"])])
    llm = AsyncMock()
    llm.get_job.return_value = _sdk_job("completed")
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["j1"]


async def test_sweep_leaves_inflight_job_alone(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["j1"])])
    llm = AsyncMock()
    llm.get_job.return_value = _sdk_job("running")  # slow ≠ stuck
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
        return _sdk_job("completed")

    llm.get_job.side_effect = get_job
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["good"]  # skipped the erroring id, re-drove the next


async def test_sweep_redrives_persist_stage_row(monkeypatch):
    # Poison recovery (review-impl finding 2): a row stuck at PERSIST (a finalize that
    # poison-acked) is still swept (the WHERE filters on resume_state IS NOT NULL, not on
    # stage) and re-driven → _resume's else-branch → persist_chunk. This is the runtime
    # backstop the strict-tx finalize depends on.
    row = {"job_id": EJ, "provider_job_ids": ["j1"],
           "resume_state": {"stage": dx.PERSIST, "user_id": USER}}
    pool = FakePool(FakeConn([]), fetch_rows=[row])
    llm = AsyncMock()
    llm.get_job.return_value = _sdk_job("completed")
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["j1"]


async def test_sweep_redrives_once_per_row_then_breaks(monkeypatch):
    conn = FakeConn([])
    pool = FakePool(conn, fetch_rows=[_stranded_row(["j1", "j2"])])  # both terminal
    llm = AsyncMock()
    llm.get_job.return_value = _sdk_job("completed")
    calls = _spy_resume(monkeypatch)

    n = await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert n == 1 and calls == ["j1"]  # one re-drive advances the row; re-eval next tick


async def test_sweep_resolves_byok_owner_for_get_job(monkeypatch):
    # review-impl finding 4 — a BYOK job is OWNED by the billing user (submit_job
    # overrides user_id with the billing contextvar), so the sweeper's get_job must
    # target billing_user_id, not the project owner's user_id, or it can't see the job.
    BILL = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    row = {
        "job_id": EJ, "provider_job_ids": ["j1"],
        "resume_state": {"stage": dx.TRIO, "user_id": USER, "billing_user_id": BILL},
    }
    pool = FakePool(FakeConn([]), fetch_rows=[row])
    llm = AsyncMock()
    llm.get_job.return_value = _sdk_job("completed")
    _spy_resume(monkeypatch)

    await _sweep_once(pool, AsyncMock(), llm, timeout_s=900, batch=20)

    assert llm.get_job.call_args.kwargs["user_id"] == BILL


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
    # extraction_jobs is keyed by job_id, not a surrogate `id` (real-schema parity)
    assert "SELECT job_id" in sql
    assert captured["args"] == (900, 20)


async def test_sweep_select_uses_for_update_skip_locked(monkeypatch):
    # D-WX-TRIO-FANIN-RACE (sweep side) — two worker-ai replicas must not both claim
    # the SAME stranded row and double-submit an ENTITY-stage re-drive. FOR UPDATE
    # SKIP LOCKED makes concurrent sweeps claim DISJOINT rows: the second replica's
    # SELECT skips a row already locked by the first instead of blocking on it. The
    # trio fold's own FOR UPDATE (no SKIP — it must block) stays as-is.
    captured = {}

    class CapturingPool(FakePool):
        async def fetch(self, sql, *args):
            captured["sql"] = sql
            return []

    pool = CapturingPool(FakeConn([]))
    await _sweep_once(pool, AsyncMock(), AsyncMock(), timeout_s=900, batch=20)

    sql = captured["sql"]
    assert "FOR UPDATE SKIP LOCKED" in sql      # disjoint per-replica claim
    # the LIMIT must precede FOR UPDATE (Postgres grammar: locking clause is last)
    assert sql.index("LIMIT") < sql.index("FOR UPDATE SKIP LOCKED")


# ── Unified Job Control Plane P1 — ExtractTerminalConsumer wiring (flag-gated migration) ──
# Shared transport is unit-tested in the SDK; the legacy consume_llm_terminal_stream
# transport is covered above. These cover only the new class SEAM: handle()→_handle and
# sweep_once()→_sweep_once + the base ack/retry path (no internal ack left in handle).


async def test_extract_consumer_handle_delegates_to_handle(monkeypatch):
    from app.llm_extract_consumer import ExtractTerminalConsumer

    seen = {}

    async def _fake_handle(pool, kc, llm, fields):
        seen["fields"] = fields

    monkeypatch.setattr("app.llm_extract_consumer._handle", _fake_handle)
    c = ExtractTerminalConsumer("redis://x", object(), AsyncMock(), AsyncMock())
    r = AsyncMock()
    await c._process_msg(r, "1-0", {"job_id": "j", "owner_user_id": "u"})
    assert seen["fields"] == {"job_id": "j", "owner_user_id": "u"}
    r.xack.assert_awaited_once()  # _handle returned → base acks


async def test_extract_consumer_handle_error_leaves_unacked(monkeypatch):
    from app.llm_extract_consumer import ExtractTerminalConsumer

    async def _boom(pool, kc, llm, fields):
        raise RuntimeError("transient")

    monkeypatch.setattr("app.llm_extract_consumer._handle", _boom)
    c = ExtractTerminalConsumer("redis://x", object(), AsyncMock(), AsyncMock())
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)  # below max_retries → redelivered
    await c._process_msg(r, "1-0", {"job_id": "j"})
    r.xack.assert_not_called()


async def test_extract_consumer_sweep_once_delegates(monkeypatch):
    from app.llm_extract_consumer import ExtractTerminalConsumer

    async def _fake_sweep(pool, kc, llm, *, timeout_s, batch):
        return 7

    monkeypatch.setattr("app.llm_extract_consumer._sweep_once", _fake_sweep)
    c = ExtractTerminalConsumer("redis://x", object(), AsyncMock(), AsyncMock())
    assert await c.sweep_once(timeout_s=900, batch=20) == 7
