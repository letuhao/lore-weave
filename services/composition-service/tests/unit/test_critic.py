"""Unit tests for judge_prose (parse tolerance, 4 dims, CC4 degrade)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from loreweave_llm.errors import LLMError

from app.engine import critic
from app.packer.profile import NEUTRAL, BookProfile


# ── tolerant parse ──

def test_parse_strips_fences():
    out = critic.parse_critique_json('```json\n{"coherence": 4}\n```')
    assert out == {"coherence": 4}

def test_parse_extracts_balanced_object_amid_prose():
    out = critic.parse_critique_json('Here is my verdict: {"pacing": 3} hope that helps')
    assert out == {"pacing": 3}

def test_parse_returns_none_on_garbage():
    assert critic.parse_critique_json("not json at all") is None
    assert critic.parse_critique_json("") is None


# ── normalize (score coercion + violation filter) ──

def test_normalize_coerces_scores_and_filters_violations():
    parsed = {
        "coherence": 4, "voice_match": "high", "pacing": 9, "canon_consistency": 3,
        "violations": [
            {"rule_id": "r1", "violated": True, "span": "x", "why": "contradicts"},
            {"violated": True},                  # no rule_id → dropped
            "not-a-dict",                        # malformed → dropped
            {"rule_id": "r2"},                   # minimal valid → kept
        ],
    }
    out = critic.normalize_critique(parsed)
    assert out["coherence"] == 4 and out["canon_consistency"] == 3
    assert out["voice_match"] is None            # non-int → None
    assert out["pacing"] is None                 # out of 0-5 range → None
    assert [v["rule_id"] for v in out["violations"]] == ["r1", "r2"]  # malformed filtered


def test_normalize_handles_none():
    out = critic.normalize_critique(None)
    assert out["coherence"] is None and out["violations"] == []


# ── de-bias prompt ──

def test_prompt_carries_source_language_no_english_default():
    sys_zh, _ = critic.build_critique_prompt("p", [], [], BookProfile(source_language="zh"))
    assert "'zh'" in sys_zh
    sys_auto, _ = critic.build_critique_prompt("p", [], [], NEUTRAL)
    assert "language with code" not in sys_auto  # auto → no forced language


# ── judge_prose (fake judge) ──

class FakeJudge:
    def __init__(self, *, content=None, status="completed", raises=False):
        self._content = content
        self._status = status
        self._raises = raises
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise LLMError("gateway down")
        result = {"messages": [{"role": "assistant", "content": self._content}]} if self._content else {}
        return SimpleNamespace(status=self._status, result=result)


async def test_judge_prose_happy_returns_four_dims_and_violations():
    content = json.dumps({"coherence": 5, "voice_match": 4, "pacing": 3, "canon_consistency": 2,
                          "violations": [{"rule_id": "r1", "violated": True, "span": "s", "why": "w"}]})
    judge = FakeJudge(content=content)
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="prose", active_rules=[{"rule_id": "r1", "text": "no magic"}],
                                   present_facts=[], profile=NEUTRAL)
    assert out["coherence"] == 5 and out["canon_consistency"] == 2
    assert out["violations"][0]["rule_id"] == "r1"
    # the critic ran with the distinct critic ref
    assert judge.calls[0]["model_ref"] == "m" and judge.calls[0]["operation"] == "chat"
    # disables hidden thinking via the WORKING knob (reasoning_effort), not just
    # the no-op chat_template_kwargs — else reasoning_tokens burn the JSON budget.
    assert judge.calls[0]["input"]["reasoning_effort"] == "none"


async def test_judge_prose_cc4_degrades_on_llm_error():
    judge = FakeJudge(raises=True)
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="p", active_rules=[], present_facts=[], profile=NEUTRAL)
    assert out["error"] == "critic_unavailable" and out["violations"] == []
    assert all(out[d] is None for d in ("coherence", "voice_match", "pacing", "canon_consistency"))


async def test_judge_prose_non_completed_status_degrades():
    judge = FakeJudge(content="{}", status="failed")
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="p", active_rules=[], present_facts=[], profile=NEUTRAL)
    assert out["error"] == "critic_failed"


async def test_judge_prose_malformed_json_yields_empty_not_crash():
    judge = FakeJudge(content="the model rambled without JSON")
    out = await critic.judge_prose(judge, user_id="u", model_source="user_model", model_ref="m",
                                   passage="p", active_rules=[], present_facts=[], profile=NEUTRAL)
    assert out["violations"] == [] and out["coherence"] is None  # degraded, not raised
