"""Phase 2b-T3b cold-start — decoupled 2-pass cold-start orchestration. The namepair
transition + resume branching (no pairs → v3_verify; pairs → pass-2 re-translate), under
the FOR UPDATE race-guard. Name-harvest correctness lives in test_bilingual_extractor."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.workers.v3 import decoupled_v3_coldstart as cs
from app.workers.v3.bilingual_extractor import NamePair


# ── FOR UPDATE harness ──────────────────────────────────────────────────────────

class _Tx:
    def __init__(self, c): self._c = c
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False


class _Conn:
    def __init__(self, fr):
        self._fr = fr
        self.executed: list = []
    async def fetchrow(self, _sql, *_a): return self._fr
    async def execute(self, sql, *a): self.executed.append((sql, a))
    def transaction(self): return _Tx(self)


class _Acq:
    def __init__(self, c): self._c = c
    async def __aenter__(self): return self._c
    async def __aexit__(self, *_): return False


class _Pool:
    def __init__(self, c): self._c = c
    def acquire(self): return _Acq(self._c)
    async def execute(self, sql, *a): self._c.executed.append((sql, a))


def _sqls(conn): return " || ".join(s for s, _ in conn.executed)


def _block_rs(**over):
    rs = {
        "blocks": [{"type": "paragraph"}], "msg": {
            "user_id": "u", "model_source": "user_model", "model_ref": "m",
            "book_id": "b", "job_id": str(uuid4()), "chapter_id": str(uuid4())},
        "source_lang": "zh", "target_code": "vi", "glossary_prompt_block": "",
        "total_input": 5, "total_output": 7, "chapter_text": "src",
        "translated_texts": {"0": "draft"},  # memo_from_translated needs this on hand-off
        "v3": {"verifier_model": ["s", "r"], "qa_depth": "standard", "use_llm": True,
               "max_rounds": 1, "cmap": {}}, "extra_system": "EXTRA", "context_window": 8192,
    }
    rs.update(over)
    return rs


# ── transition_from_block (under the block lock) ────────────────────────────────

@pytest.mark.asyncio
async def test_transition_submits_namepair(monkeypatch):
    monkeypatch.setattr(cs, "_join_translatable", lambda b: "some text")
    conn = _Conn(None)
    llm = MagicMock(); llm.submit_job = AsyncMock(return_value=MagicMock(job_id=uuid4()))

    payload = await cs.transition_from_block(conn, llm, uuid4(), _block_rs(), [{"type": "p"}])

    assert payload is None                                  # in flight
    llm.submit_job.assert_awaited_once()                    # namepair submitted
    assert "pipeline_stage='v3_coldstart'" in _sqls(conn)   # persisted under the lock


@pytest.mark.asyncio
async def test_transition_empty_text_hands_to_v3_verify(monkeypatch):
    monkeypatch.setattr(cs, "_join_translatable", lambda b: "")  # nothing to harvest
    sentinel = ("body", 1, 2, "memo")
    monkeypatch.setattr(cs.v3v, "transition_from_block",
                        AsyncMock(return_value=sentinel))
    conn = _Conn(None)
    llm = MagicMock(); llm.submit_job = AsyncMock()

    payload = await cs.transition_from_block(conn, llm, uuid4(), _block_rs(), [{"type": "p"}])

    assert payload == sentinel                              # delegated to v3_verify
    llm.submit_job.assert_not_awaited()                     # no namepair


def test_seed_coldstart_carries_block_rs_keys_and_pass1():
    rs = cs._seed_coldstart(_block_rs(), [{"r": 1}], "src", "tgt")
    assert rs["mode"] == "v3_coldstart" and rs["stage"] == "namepair"
    assert rs["pass1_result_blocks"] == [{"r": 1}]
    assert rs["base_extra"] == "EXTRA" and rs["book_id"] == "b"
    # block_rs-compatible (v3_verify._seed_v3 reads these on the no-pairs hand-off) —
    # translated_texts is load-bearing: memo_from_translated KeyErrors without it.
    for k in ("blocks", "msg", "source_lang", "target_code", "total_input",
              "translated_texts", "v3"):
        assert k in rs


@pytest.mark.asyncio
async def test_resume_no_pairs_real_v3_verify_handoff_does_not_crash(monkeypatch):
    """review-impl HIGH: the no-pairs hand-off passes the COLDSTART rs to the REAL
    v3_verify transition → _seed_v3 → memo_from_translated(rs) reads translated_texts.
    With passthrough blocks the draft set is empty → a finalize payload comes back →
    resume finalizes. A missing seed key (translated_texts) would KeyError here."""
    pj = uuid4()
    conn = _Conn({"resume_state": _coldstart_rs(), "provider_job_id": pj})
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = pj; job.status = "completed"
    monkeypatch.setattr("app.workers.v3.bilingual_extractor.parse_namepair_job", lambda j: [])
    monkeypatch.setattr("app.workers.block_classifier.classify_block", lambda b: "passthrough")
    fin = AsyncMock()

    await cs.resume(pool=pool, llm_client=MagicMock(), job=job,
                    chapter_translation_id=uuid4(), finalize_cb=fin)

    fin.assert_awaited_once()                       # finalized via the REAL v3_verify path
    assert "resume_state=NULL" in _sqls(conn)


# ── resume() — namepair terminal ────────────────────────────────────────────────

def _coldstart_rs():
    rs = _seed = cs._seed_coldstart(_block_rs(), [{"type": "p"}], "src", "tgt")
    return rs


@pytest.mark.asyncio
async def test_resume_no_pairs_hands_to_v3_verify(monkeypatch):
    pj = uuid4()
    conn = _Conn({"resume_state": _coldstart_rs(), "provider_job_id": pj})
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = pj; job.status = "completed"
    monkeypatch.setattr("app.workers.v3.bilingual_extractor.parse_namepair_job", lambda j: [])
    # v3_verify transition submits a verify under the lock → returns None (in flight)
    v3v_trans = AsyncMock(return_value=None)
    monkeypatch.setattr(cs.v3v, "transition_from_block", v3v_trans)
    pass2 = AsyncMock(); monkeypatch.setattr(cs, "_start_pass2", pass2)
    fin = AsyncMock()

    await cs.resume(pool=pool, llm_client=MagicMock(), job=job,
                    chapter_translation_id=uuid4(), finalize_cb=fin)

    v3v_trans.assert_awaited_once()        # handed to v3_verify
    pass2.assert_not_awaited()             # no pass 2
    fin.assert_not_awaited()               # verify in flight, not finalized


@pytest.mark.asyncio
async def test_resume_no_pairs_finalizes_when_verify_returns_payload(monkeypatch):
    pj = uuid4()
    conn = _Conn({"resume_state": _coldstart_rs(), "provider_job_id": pj})
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = pj; job.status = "completed"
    monkeypatch.setattr("app.workers.v3.bilingual_extractor.parse_namepair_job", lambda j: [])
    monkeypatch.setattr(cs.v3v, "transition_from_block",
                        AsyncMock(return_value=("body", 1, 2, "memo")))  # rule_only no HIGH
    fin = AsyncMock()

    await cs.resume(pool=pool, llm_client=MagicMock(), job=job,
                    chapter_translation_id=uuid4(), finalize_cb=fin)

    fin.assert_awaited_once()                       # finalized the pass-1 result
    assert "resume_state=NULL" in _sqls(conn)       # cleared


@pytest.mark.asyncio
async def test_resume_pairs_starts_pass2(monkeypatch):
    pj = uuid4()
    conn = _Conn({"resume_state": _coldstart_rs(), "provider_job_id": pj})
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = pj; job.status = "completed"
    pairs = [NamePair("仙卿", "Tien Khanh", "character")]
    monkeypatch.setattr("app.workers.v3.bilingual_extractor.parse_namepair_job", lambda j: pairs)
    pass2 = AsyncMock(); monkeypatch.setattr(cs, "_start_pass2", pass2)
    fin = AsyncMock()

    await cs.resume(pool=pool, llm_client=MagicMock(), job=job,
                    chapter_translation_id=uuid4(), finalize_cb=fin)

    pass2.assert_awaited_once()                     # pass-2 re-translate launched
    assert pass2.await_args.args[4] == pairs        # with the harvested pairs
    fin.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_skips_when_provider_job_superseded(monkeypatch):
    conn = _Conn({"resume_state": _coldstart_rs(), "provider_job_id": uuid4()})  # different
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = uuid4(); job.status = "completed"
    pass2 = AsyncMock(); monkeypatch.setattr(cs, "_start_pass2", pass2)

    await cs.resume(pool=pool, llm_client=MagicMock(), job=job,
                    chapter_translation_id=uuid4(), finalize_cb=AsyncMock())

    pass2.assert_not_awaited()
    assert conn.executed == []


@pytest.mark.asyncio
async def test_start_pass2_writes_back_and_starts_block(monkeypatch):
    rs = _coldstart_rs()
    pairs = [NamePair("仙卿", "Tien Khanh", "character")]
    wb = AsyncMock(); monkeypatch.setattr(
        "app.workers.glossary_client.writeback_name_pairs", wb)
    start = AsyncMock(); monkeypatch.setattr(
        "app.workers.decoupled_block_translate.start_chapter_blocks", start)

    await cs._start_pass2(MagicMock(), MagicMock(), uuid4(), rs, pairs)

    wb.assert_awaited_once()                        # glossary seeded
    start.assert_awaited_once()                     # pass-2 block started
    kw = start.await_args.kwargs
    assert kw["v3"]["post_block"] == "v3_verify"    # pass 2 → verify/correct
    assert "Tien Khanh" in kw["msg"]["extra_system"]  # names enforced in the prompt
    assert kw["seed_input"] == 5 and kw["seed_output"] == 7  # token parity: pass1+pass2
