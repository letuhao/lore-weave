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


# ── per-rule attribution (D-QC5-PROSE-JUDGE-VERDICT-NOT-PER-RULE, 2026-08-12) ──

_RULES = [
    {"rule_id": "0331a53f-0000-0000-0000-000000000001", "text": "rule one"},
    {"rule_id": "6e153c35-0000-0000-0000-000000000002", "text": "rule two"},
]


def test_rules_are_shown_under_short_labels_not_their_uuids():
    """🔴 REGRESSION. The prompt used to render `- [<uuid>] text` and ask the judge to echo
    the uuid back per verdict. Measured on QC-5: given one rule the passage contradicts and
    one it plainly confirms, the judge marked BOTH violated and copied the same `why` to each.
    A 36-char uuid is not a label a model carries accurately through a long passage.
    """
    _, user = critic.build_critique_prompt("passage", _RULES, [], NEUTRAL)
    assert "[R1]" in user and "[R2]" in user
    for r in _RULES:
        assert r["rule_id"] not in user, (
            "a rule uuid is back in the prompt — the judge will be asked to echo it again"
        )


def test_a_label_is_mapped_back_to_its_real_rule_id():
    out = critic.map_rule_tokens(
        [{"rule_id": "R2", "violated": True, "span": "s", "why": "w"}], _RULES)
    assert [v["rule_id"] for v in out] == [_RULES[1]["rule_id"]]


def test_an_unmappable_label_is_DROPPED_rather_than_passed_through():
    """The half that makes this a fix and not a rename.

    The old shape accepted whatever string landed in `rule_id`, so a copied or invented id
    became a verdict about a real rule the judge was never asked about. A verdict nobody can
    attribute is not evidence; it is noise with a citation.
    """
    out = critic.map_rule_tokens([
        {"rule_id": "R9", "violated": True, "span": "", "why": "off the end"},
        {"rule_id": "totally-made-up", "violated": True, "span": "", "why": "invented"},
        {"rule_id": "R1", "violated": True, "span": "", "why": "real"},
    ], _RULES)
    assert [v["why"] for v in out] == ["real"]


def test_a_judge_that_echoes_the_real_id_is_still_attributable():
    """Tolerance, not laxity: some judges echo the id anyway, and that verdict CAN be
    attributed — dropping it would lose a true finding to a formatting preference."""
    out = critic.map_rule_tokens(
        [{"rule_id": _RULES[0]["rule_id"], "violated": True, "span": "", "why": "w"}], _RULES)
    assert [v["rule_id"] for v in out] == [_RULES[0]["rule_id"]]


def test_labels_are_one_based():
    assert (critic.rule_token(0), critic.rule_token(1)) == ("R1", "R2")
