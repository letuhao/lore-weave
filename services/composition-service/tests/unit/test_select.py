"""Unit tests for the diverge→converge selection (V1 Phase A1).

Focus = the load-bearing DEGRADE paths (memory: degrade paths, not happy-path):
diverge survivor-filtering + all-fail raise; rerank single/malformed/error →
candidate[0] fallback; select_draft end-to-end winner.
"""

import json
from types import SimpleNamespace

import pytest

from loreweave_llm.errors import LLMError

from app.engine import select
from app.engine.select import Candidate
from app.packer.profile import NEUTRAL

pytestmark = pytest.mark.asyncio


class FakeLLM:
    """Routes by job_meta['extractor']: drafts pop from a list (None = dropped),
    rerank returns a canned JSON string. Raises/states are per-channel."""

    def __init__(self, *, drafts=None, rerank=None, draft_status="completed",
                 rerank_status="completed", draft_raises=False, rerank_raises=False):
        self._drafts = list(drafts if drafts is not None else [])
        self._rerank = rerank
        self._draft_status = draft_status
        self._rerank_status = rerank_status
        self._draft_raises = draft_raises
        self._rerank_raises = rerank_raises
        self.draft_calls = 0
        self.rerank_calls = 0

    async def submit_and_wait(self, **kw):
        meta = kw.get("job_meta") or {}
        if meta.get("extractor") == "rerank":
            self.rerank_calls += 1
            if self._rerank_raises:
                raise LLMError("gateway down")
            res = {"messages": [{"content": self._rerank}]} if self._rerank is not None else {}
            return SimpleNamespace(status=self._rerank_status, result=res)
        # draft channel
        self.draft_calls += 1
        if self._draft_raises:
            raise LLMError("gateway down")
        text = self._drafts.pop(0) if self._drafts else ""
        res = {"messages": [{"content": text}]} if text else {}
        return SimpleNamespace(status=self._draft_status, result=res)


def _cands(*texts):
    return [Candidate(t, None) for t in texts]


# ── diverge ──

async def test_diverge_returns_k_candidates():
    llm = FakeLLM(drafts=["draft A", "draft B", "draft C"])
    out = await select.diverge(
        llm, user_id="u", model_source="user_model", model_ref="m",
        packed_prompt="ctx", profile=NEUTRAL, operation="continue", guide="",
        k=3, prompt_est=10, max_tokens=256,
    )
    assert [c.text for c in out] == ["draft A", "draft B", "draft C"]
    assert llm.draft_calls == 3
    assert all(c.metering.measured is False for c in out)  # non-stream → char-estimated


async def test_diverge_drops_empty_and_keeps_survivors():
    # 3 requested; one returns empty (dropped) → 2 survivors
    llm = FakeLLM(drafts=["good 1", "", "good 2"])
    out = await select.diverge(
        llm, user_id="u", model_source="user_model", model_ref="m",
        packed_prompt="ctx", profile=NEUTRAL, operation="continue", guide="",
        k=3, prompt_est=10, max_tokens=256,
    )
    assert sorted(c.text for c in out) == ["good 1", "good 2"]


async def test_diverge_raises_when_all_fail():
    llm = FakeLLM(draft_raises=True)
    with pytest.raises(RuntimeError, match="no candidates"):
        await select.diverge(
            llm, user_id="u", model_source="user_model", model_ref="m",
            packed_prompt="ctx", profile=NEUTRAL, operation="continue", guide="",
            k=3, prompt_est=10, max_tokens=256,
        )


async def test_diverge_drops_non_completed():
    llm = FakeLLM(drafts=["x", "y"], draft_status="failed")
    with pytest.raises(RuntimeError, match="no candidates"):
        await select.diverge(
            llm, user_id="u", model_source="user_model", model_ref="m",
            packed_prompt="ctx", profile=NEUTRAL, operation="continue", guide="",
            k=2, prompt_est=10, max_tokens=256,
        )


# ── score (rerank) ──

async def test_score_single_candidate_no_rerank_call():
    llm = FakeLLM(rerank=json.dumps({"best": 0}))
    idx, reason, measured = await select.score(
        llm, user_id="u", model_source="user_model", model_ref="m",
        candidates=_cands("only"), profile=NEUTRAL,
    )
    assert (idx, measured) == (0, False)
    assert reason == "single_candidate"
    assert llm.rerank_calls == 0  # short-circuit, no LLM call


async def test_score_happy_picks_best():
    llm = FakeLLM(rerank=json.dumps({"best": 2, "ranking": [2, 0, 1], "reason": "C is tightest"}))
    idx, reason, measured = await select.score(
        llm, user_id="u", model_source="user_model", model_ref="m",
        candidates=_cands("a", "b", "c"), profile=NEUTRAL,
    )
    assert (idx, measured) == (2, True)
    assert reason == "C is tightest"


@pytest.mark.parametrize("best", [5, -1, True, "1", 1.5, None])
async def test_score_malformed_best_falls_back_to_zero(best):
    llm = FakeLLM(rerank=json.dumps({"best": best}) if best is not None else "{}")
    idx, _, measured = await select.score(
        llm, user_id="u", model_source="user_model", model_ref="m",
        candidates=_cands("a", "b"), profile=NEUTRAL,
    )
    assert (idx, measured) == (0, False)  # out-of-range / bool / non-int → candidate[0]


async def test_score_llm_error_falls_back_to_zero():
    llm = FakeLLM(rerank_raises=True)
    idx, reason, measured = await select.score(
        llm, user_id="u", model_source="user_model", model_ref="m",
        candidates=_cands("a", "b"), profile=NEUTRAL,
    )
    assert (idx, measured) == (0, False)
    assert reason == "rerank_unavailable"


async def test_score_non_completed_falls_back():
    llm = FakeLLM(rerank=json.dumps({"best": 1}), rerank_status="failed")
    idx, reason, measured = await select.score(
        llm, user_id="u", model_source="user_model", model_ref="m",
        candidates=_cands("a", "b"), profile=NEUTRAL,
    )
    assert (idx, measured) == (0, False)
    assert reason == "rerank_failed"


# ── select_draft end-to-end ──

async def test_select_draft_returns_reranked_winner():
    llm = FakeLLM(drafts=["a", "b", "c"], rerank=json.dumps({"best": 1, "reason": "b"}))
    sel = await select.select_draft(
        llm, llm, user_id="u",
        drafter_source="user_model", drafter_ref="d", judge_source="user_model", judge_ref="j",
        packed_prompt="ctx", profile=NEUTRAL, operation="continue", guide="",
        k=3, prompt_est=10, max_tokens=256,
    )
    assert sel.winner.text == "b"
    assert sel.winner_index == 1
    assert len(sel.candidates) == 3
    assert sel.rerank_measured is True
