"""Evaluate pipeline unit tests (M6) — the coercion guarantees.

The model emits the scorecard JSON; coercion makes it safe-when-wrong: the
per-checklist verdict is rebuilt from `charter.checklist` (model can neither drop
nor invent items), scores are clamped, and `partial` is server-decided (EC-13).
"""
from __future__ import annotations

import pytest

from app.services import evaluate as ev

_CHARTER = {
    "goal": "Senior backend interview",
    "phases": ["warmup", "technical", "behavioral", "wrap"],
    "checklist": ["system design", "conflict story"],
    "time_budget_min": 60,
    "language": "en",
}


# ── coerce_scorecard: the safe-when-wrong core ───────────────────────────────

def test_coerce_rebuilds_checklist_from_charter():
    raw = {
        "checklist": [
            {"item": "system design", "covered": True, "note": "sharding + cache"},
            {"item": "INVENTED ITEM", "covered": True},  # not in charter → dropped
        ],
    }
    card = ev.coerce_scorecard(raw, _CHARTER, partial=False)
    items = {v.item: v for v in card.checklist}
    # exactly the two charter items, no more
    assert set(items) == {"system design", "conflict story"}
    assert items["system design"].covered is True
    assert items["system design"].note == "sharding + cache"
    # the item the model never reported is present and defaults to not-covered
    assert items["conflict story"].covered is False


def test_coerce_clamps_overall_score():
    assert ev.coerce_scorecard({"overall_score": 150}, _CHARTER, partial=False).overall_score == 100
    assert ev.coerce_scorecard({"overall_score": -5}, _CHARTER, partial=False).overall_score == 0
    assert ev.coerce_scorecard({"overall_score": "abc"}, _CHARTER, partial=False).overall_score is None
    assert ev.coerce_scorecard({}, _CHARTER, partial=False).overall_score is None


def test_coerce_filters_non_string_lists():
    raw = {"strengths": ["clear", 123, "", None, "concise"], "improvements": "not a list"}
    card = ev.coerce_scorecard(raw, _CHARTER, partial=False)
    assert card.strengths == ["clear", "concise"]
    assert card.improvements == []


def test_coerce_partial_flag_is_server_set_not_model():
    # The model claims complete; the server says partial — server wins.
    raw = {"partial": False, "summary": "great"}
    card = ev.coerce_scorecard(raw, _CHARTER, partial=True)
    assert card.partial is True


def test_coerce_empty_charter_checklist_yields_no_verdicts():
    card = ev.coerce_scorecard({"overall_score": 80}, {"checklist": [], "language": "en"}, partial=False)
    assert card.checklist == []
    assert card.overall_score == 80


def test_scorecard_is_quarantine_tier_and_model_cannot_lift_it():
    # WS-5.22 / SD-7 — every score a code run produces is quarantine (shown, never trended)
    # until the numeric gate clears in a human milestone; a model claiming otherwise is ignored.
    card = ev.coerce_scorecard({"overall_score": 90, "quarantine": False}, _CHARTER, partial=False)
    assert card.quarantine is True  # server-authoritative, like `partial`


# ── is_partial (EC-13) ───────────────────────────────────────────────────────

def test_is_partial_when_clipped():
    assert ev.is_partial({"phase": "wrap"}, clipped=True) is True


def test_is_partial_when_not_wrap():
    assert ev.is_partial({"phase": "technical"}, clipped=False) is True
    assert ev.is_partial({"phase": ""}, clipped=False) is True
    assert ev.is_partial({}, clipped=False) is True


def test_not_partial_when_wrap_and_unclipped():
    assert ev.is_partial({"phase": "wrap"}, clipped=False) is False


# ── build_eval_messages: bounded + clip signal ───────────────────────────────

def test_build_messages_clips_long_transcript():
    transcript = [{"role": "user", "content": "x"} for _ in range(ev.EVAL_MAX_MESSAGES + 10)]
    msgs, clipped = ev.build_eval_messages(_CHARTER, {}, None, transcript)
    assert clipped is True
    assert len(msgs) == 2  # system + user


def test_build_messages_caps_message_size():
    transcript = [{"role": "user", "content": "y" * 50000}]
    msgs, clipped = ev.build_eval_messages(_CHARTER, {}, None, transcript)
    assert clipped is False
    # the pasted wall is truncated inside the serialized context
    assert "y" * (ev.EVAL_MAX_MSG_CHARS + 1) not in msgs[1]["content"]


def test_build_messages_short_transcript_not_clipped():
    msgs, clipped = ev.build_eval_messages(_CHARTER, {}, None, [{"role": "user", "content": "hi"}])
    assert clipped is False


def test_build_messages_includes_rubric_dimensions_when_given():
    # C3 — the SoT rubric's dimensions reach the prompt as scoring_dimensions + a keyed instruction.
    dims = [
        {"key": "star_structure", "label": "STAR structure", "anchors": {"1": "none", "5": "complete"}},
        {"key": "clarity", "label": "Clarity", "anchors": {"1": "unclear", "5": "crisp"}},
    ]
    msgs, _ = ev.build_eval_messages(_CHARTER, {}, None, [{"role": "user", "content": "hi"}], dimensions=dims)
    user = msgs[1]["content"]
    assert "scoring_dimensions" in user
    assert "star_structure" in user and "clarity" in user
    assert '"dimensions":' in user  # the model is told to return a dimensions array


def test_build_messages_omits_dimensions_when_none():
    # back-compat: no rubric dimensions → no scoring_dimensions block (legacy STAR path unchanged).
    msgs, _ = ev.build_eval_messages(_CHARTER, {}, None, [{"role": "user", "content": "hi"}])
    assert "scoring_dimensions" not in msgs[1]["content"]


# ── parse_json_object: tolerant extraction ───────────────────────────────────

def test_parse_handles_fences_and_prose():
    assert ev.parse_json_object('{"overall_score": 70}')["overall_score"] == 70
    assert ev.parse_json_object('```json\n{"overall_score": 80}\n```')["overall_score"] == 80
    assert ev.parse_json_object('Here: {"overall_score": 90} done')["overall_score"] == 90


def test_parse_handles_trailing_data():
    # Small local models often append text (or a second object) after the JSON,
    # which json.loads rejects with "Extra data". raw_decode takes the first.
    assert ev.parse_json_object('{"overall_score": 65}\nNote: well done!')["overall_score"] == 65
    assert ev.parse_json_object('{"a": {"b": 1}} {"c": 2}')["a"] == {"b": 1}
    assert ev.parse_json_object('```json\n{"overall_score": 50}\n```\ntrailing')["overall_score"] == 50


def test_parse_raises_on_no_object():
    with pytest.raises(ValueError):
        ev.parse_json_object("no json here")


# ── render_summary_text: human body ──────────────────────────────────────────

def test_render_summary_counts_covered():
    raw = {
        "overall_score": 75,
        "summary": "Solid technical depth.",
        "improvements": ["practice the STAR format"],
        "checklist": [{"item": "system design", "covered": True}],
    }
    card = ev.coerce_scorecard(raw, _CHARTER, partial=False)
    text = ev.render_summary_text(card, _CHARTER)
    assert "Overall: 75/100" in text
    assert "Checklist covered: 1/2" in text
    assert "practice the STAR format" in text
