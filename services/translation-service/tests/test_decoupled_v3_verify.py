"""Phase 2b-T3b — decoupled V3 verify/correct loop. The pure transitions + the shell
submit-assembly + the resume()/transition orchestration (the verify→correct→finalize
loop under the FOR UPDATE race-guard). LLM/DB are faked; correctness of the rule-tier +
keep-if-improved lives in the sync v3 tests (this locks the DECOUPLE machinery)."""
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.workers.v3 import decoupled_v3_verify as dx
from app.workers.v3.quality import Issue, IssueReport


def _issue(block, sev="high", typ="wrong_name", by="rule"):
    return Issue(block, typ, sev, "detail", None, by)


# ── pure transitions ────────────────────────────────────────────────────────────

def test_issue_serde_roundtrip():
    i = _issue(2, sev="med", by="llm")
    assert dx._issue_from_dict(dx._issue_to_dict(i)) == i


def test_evaluate_correct_when_high_and_rounds_left():
    rs = {"report_issues": [dx._issue_to_dict(_issue(0)), dx._issue_to_dict(_issue(3))],
          "round": 0, "max_rounds": 1}
    out = dx._evaluate(rs)
    assert out["stage"] == dx.CORRECT and out["flagged"] == [0, 3] and out["correct_cursor"] == 0


def test_evaluate_finalize_when_no_high():
    rs = {"report_issues": [dx._issue_to_dict(_issue(0, sev="med"))], "round": 0, "max_rounds": 1}
    assert dx._evaluate(rs)["stage"] == dx.FINALIZE


def test_evaluate_finalize_when_rounds_exhausted():
    rs = {"report_issues": [dx._issue_to_dict(_issue(0))], "round": 1, "max_rounds": 1}
    assert dx._evaluate(rs)["stage"] == dx.FINALIZE  # HIGH remains but no round left


def test_fold_verify_merges_rule_and_caps_llm_high_to_med():
    rs = {"rule_issues": [dx._issue_to_dict(_issue(0, sev="high"))]}
    out = dx.fold_verify(rs, [_issue(1, sev="high", by="llm")])
    report = dx._report_from_dicts(out["report_issues"])
    # the rule HIGH survives; the LLM 'high' is capped to 'med' (never alone triggers churn)
    sev_by_block = {i.block_index: i.severity for i in report.issues}
    assert sev_by_block[0] == "high" and sev_by_block[1] == "med"


def test_begin_correct_next_walks_then_exhausts():
    rs = {"flagged": [2, 5], "correct_cursor": 0}
    assert dx.begin_correct_next(rs)[1] == 2
    assert dx.begin_correct_next({**rs, "correct_cursor": 1})[1] == 5
    assert dx.begin_correct_next({**rs, "correct_cursor": 2})[1] is None


def test_apply_corrected_accepts_when_improved(monkeypatch):
    # keep-if-improved: orig rule-high on block 0 = 1; the corrected text yields 0 → accept.
    monkeypatch.setattr("app.workers.v3.verifier.verify_rules",
                        lambda s, d, c, t: IssueReport([]))  # corrected → 0 high
    rs = {"report_issues": [dx._issue_to_dict(_issue(0))], "source_texts": {"0": "s"},
          "draft_texts": {"0": "old"}, "blocks": [{"type": "paragraph"}],
          "result_blocks": [{"type": "paragraph"}], "cmap": {}, "target": "vi",
          "correct_cursor": 0}
    monkeypatch.setattr("app.workers.block_classifier.rebuild_block", lambda b, t: {"rebuilt": t})
    out = dx.apply_corrected(rs, 0, "better")
    assert out["draft_texts"]["0"] == "better"           # accepted
    assert out["result_blocks"][0] == {"rebuilt": "better"}
    assert out["correct_cursor"] == 1                     # cursor advanced


def test_apply_corrected_rejects_when_not_improved(monkeypatch):
    # corrected still has 1 rule-high (not < orig 1) → reject, keep original draft.
    monkeypatch.setattr("app.workers.v3.verifier.verify_rules",
                        lambda s, d, c, t: IssueReport([_issue(0)]))
    rs = {"report_issues": [dx._issue_to_dict(_issue(0))], "source_texts": {"0": "s"},
          "draft_texts": {"0": "old"}, "blocks": [{}], "result_blocks": [{}],
          "cmap": {}, "target": "vi", "correct_cursor": 0}
    out = dx.apply_corrected(rs, 0, "worse")
    assert out["draft_texts"]["0"] == "old"              # rejected
    assert out["correct_cursor"] == 1


def test_start_next_round_bumps_and_routes(monkeypatch):
    monkeypatch.setattr(dx, "_rule_report", lambda rs, d: IssueReport([_issue(0)]))
    base = {"round": 0, "draft_texts": {"0": "x"}, "source_texts": {"0": "s"},
            "cmap": {}, "target": "vi"}
    llm_rs = dx.start_next_round({**base, "use_llm": True})
    assert llm_rs["round"] == 1 and llm_rs["stage"] == dx.VERIFY
    rule_rs = dx.start_next_round({**base, "use_llm": False})
    assert rule_rs["round"] == 1 and rule_rs["report_issues"] == rule_rs["rule_issues"]


def test_seed_v3_carries_chapter_text_and_block_tokens(monkeypatch):
    """review-impl A+B: the v3_verify seed carries the source chapter_text (for the M7d
    judge) and the BLOCK tokens (the finalize counts block-only, matching sync v3)."""
    monkeypatch.setattr("app.workers.block_classifier.classify_block", lambda b: "text")
    monkeypatch.setattr("app.workers.block_classifier.extract_translatable_text",
                        lambda b: b.get("t", ""))
    monkeypatch.setattr("app.workers.decoupled_block_translate.memo_from_translated",
                        lambda rs: "memo")
    block_rs = {
        "v3": {"verifier_model": ["s", "r"], "qa_depth": "standard", "use_llm": True,
               "max_rounds": 1, "cmap": {}},
        "blocks": [{"t": "src"}], "msg": {"user_id": "u"},
        "source_lang": "zh", "target_code": "vi", "glossary_prompt_block": "",
        "total_input": 11, "total_output": 22, "chapter_text": "the source",
    }
    rs = dx._seed_v3(block_rs, [{"t": "draft"}])
    assert rs["chapter_text"] == "the source"           # B — source carried for the judge
    assert rs["total_in"] == 11 and rs["total_out"] == 22  # A — block tokens only
    assert rs["source_texts"] == {"0": "src"} and rs["draft_texts"] == {"0": "draft"}


# ── shell: submit assembly over the seams ───────────────────────────────────────

def _v3_rs(**over):
    rs = {
        "mode": "v3_verify", "stage": dx.VERIFY, "round": 0,
        "source_texts": {"0": "源"}, "draft_texts": {"0": "draft"},
        "result_blocks": [{"type": "paragraph"}], "blocks": [{"type": "paragraph"}],
        "cmap": {}, "glossary_prompt_block": "GLOSS", "knowledge_brief": "BRIEF",
        "source_lang": "zh", "target": "vi", "verifier_model": ["user_model", "vm"],
        "qa_depth": "standard", "use_llm": True, "max_rounds": 1,
        "report_issues": [dx._issue_to_dict(_issue(0))], "rule_issues": [],
        "flagged": [0], "correct_cursor": 0,
        "msg": {"user_id": "u", "model_source": "user_model", "model_ref": "m",
                "job_id": str(uuid4()), "chapter_id": str(uuid4())},
        "total_in": 5, "total_out": 7, "memo": "memo",
    }
    rs.update(over)
    return rs


def test_assemble_verify_submit_shape():
    kw = dx.assemble_verify_submit(_v3_rs())
    assert kw["operation"] == "translation" and kw["model_ref"] == "vm"
    assert kw["job_meta"] == {"verifier": "llm"}


def test_assemble_corrector_submit_shape():
    kw = dx.assemble_corrector_submit(_v3_rs(), 0)
    assert kw["operation"] == "translation" and kw["job_meta"] == {"corrector_block": 0}
    # the flagged block's HIGH issue detail is in the user prompt
    assert any("PROBLEMS" in m["content"] for m in kw["input"]["messages"] if m["role"] == "user")


# ── resume() orchestration (FOR UPDATE harness) ─────────────────────────────────

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
    # pool-level execute is used by _clear_resume_state (outside the lock)
    def __init__(self, c): self._c = c
    def acquire(self): return _Acq(self._c)
    async def execute(self, sql, *a): self._c.executed.append((sql, a))


def _sqls(conn): return " || ".join(s for s, _ in conn.executed)


@pytest.mark.asyncio
async def test_resume_verify_to_corrector(monkeypatch):
    """A verify terminal with a HIGH RULE issue → fold → evaluate → submit the first
    corrector under the lock (provider_job_id advances); no finalize."""
    pj = uuid4()
    rs = _v3_rs(stage=dx.VERIFY, rule_issues=[dx._issue_to_dict(_issue(0))], report_issues=[])
    conn = _Conn({"resume_state": rs, "provider_job_id": pj})
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = pj; job.status = "completed"
    monkeypatch.setattr("app.workers.v3.llm_verifier.parse_verify_job", lambda j, idx: [])
    llm = MagicMock(); llm.submit_job = AsyncMock(return_value=MagicMock(job_id=uuid4()))
    fin = AsyncMock()

    await dx.resume(pool=pool, llm_client=llm, job=job, chapter_translation_id=uuid4(), finalize_cb=fin)

    llm.submit_job.assert_awaited_once()                        # corrector submitted
    assert "pipeline_stage='v3_verify'" in _sqls(conn)          # in-flight persisted
    assert "translation_quality_issues" in _sqls(conn)          # round issues persisted
    fin.assert_not_awaited()                                    # not finalized


@pytest.mark.asyncio
async def test_resume_verify_to_finalize_when_clean(monkeypatch):
    """No HIGH issues → evaluate → FINALIZE: rollup written, finalize_cb called outside
    the lock, resume_state cleared."""
    pj = uuid4()
    rs = _v3_rs(stage=dx.VERIFY, rule_issues=[], report_issues=[])
    conn = _Conn({"resume_state": rs, "provider_job_id": pj})
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = pj; job.status = "completed"
    monkeypatch.setattr("app.workers.v3.llm_verifier.parse_verify_job", lambda j, idx: [])
    llm = MagicMock(); llm.submit_job = AsyncMock()
    fin = AsyncMock()

    await dx.resume(pool=pool, llm_client=llm, job=job, chapter_translation_id=uuid4(), finalize_cb=fin)

    llm.submit_job.assert_not_awaited()                         # no corrector
    assert "quality_score" in _sqls(conn)                       # rollup written under lock
    fin.assert_awaited_once()                                   # finalized outside lock
    assert "resume_state=NULL" in _sqls(conn)                   # cleared


@pytest.mark.asyncio
async def test_resume_skips_when_provider_job_superseded(monkeypatch):
    """A redelivered/foreign terminal whose job != the row's provider_job_id is a no-op."""
    rs = _v3_rs()
    conn = _Conn({"resume_state": rs, "provider_job_id": uuid4()})  # different
    pool = _Pool(conn)
    job = MagicMock(); job.job_id = uuid4(); job.status = "completed"
    llm = MagicMock(); llm.submit_job = AsyncMock()
    fin = AsyncMock()

    await dx.resume(pool=pool, llm_client=llm, job=job, chapter_translation_id=uuid4(), finalize_cb=fin)

    llm.submit_job.assert_not_awaited()
    fin.assert_not_awaited()
    assert conn.executed == []


@pytest.mark.asyncio
async def test_transition_from_block_submits_verify(monkeypatch):
    """On v3 block completion (use_llm), the transition seeds v3_verify + submits the
    first LLM-verify UNDER the block lock and returns None (stay in v3_verify)."""
    monkeypatch.setattr(dx, "_seed_v3", lambda brs, rb: _v3_rs(use_llm=True))
    monkeypatch.setattr(dx, "_rule_report", lambda rs, d: IssueReport([]))
    conn = _Conn(None)
    llm = MagicMock(); llm.submit_job = AsyncMock(return_value=MagicMock(job_id=uuid4()))

    payload = await dx.transition_from_block(conn, llm, uuid4(), {"v3": {}}, [{"type": "p"}])

    assert payload is None                                       # in flight → no finalize
    llm.submit_job.assert_awaited_once()                         # verify submitted
    assert "pipeline_stage='v3_verify'" in _sqls(conn)


@pytest.mark.asyncio
async def test_transition_finalizes_rule_only_no_high(monkeypatch):
    """rule_only + no HIGH rule issues ⇒ no LLM work: the transition records the rollup
    and returns a finalize payload so the block caller finalizes the block result."""
    monkeypatch.setattr(dx, "_seed_v3", lambda brs, rb: _v3_rs(use_llm=False, qa_depth="rule_only"))
    monkeypatch.setattr(dx, "_rule_report", lambda rs, d: IssueReport([]))  # no HIGH
    conn = _Conn(None)
    llm = MagicMock(); llm.submit_job = AsyncMock()

    payload = await dx.transition_from_block(conn, llm, uuid4(), {"v3": {}}, [{"type": "p"}])

    assert payload is not None and payload[1] == 5 and payload[2] == 7   # block tokens
    llm.submit_job.assert_not_awaited()                         # no LLM step
    assert "quality_score" in _sqls(conn)                       # rollup recorded
