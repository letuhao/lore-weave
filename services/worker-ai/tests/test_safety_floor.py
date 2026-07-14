"""WS-5.11 — the deterministic safety FLOOR (spec 08 Gate-3, X-5).

The load-bearing test is `test_spec_example_with_no_keywords_trips`: the spec's own worked
example has NONE of the obvious keywords, so a bare keyword list would fail open exactly
where it must not. The paraphrase patterns are the floor's teeth.
"""
from __future__ import annotations

import pytest

from app.safety_floor import (
    CAT_DISTRESS, CAT_HARASSMENT_ABUSE, CAT_SELF_HARM,
    SafetyVerdict, combine_with_model, screen,
)


def test_spec_example_with_no_keywords_trips():
    # spec 08's worked example — zero obvious keywords, must still trip (via pattern).
    v = screen("I don't know how much longer I can do this.")
    assert v.tripped is True
    assert v.category == CAT_DISTRESS
    assert v.reason and v.reason.startswith("pattern:")


@pytest.mark.parametrize("text,cat", [
    ("I keep thinking about suicide lately.", CAT_SELF_HARM),
    ("honestly I want to die most mornings", CAT_SELF_HARM),
    ("everyone would be better off without me", CAT_SELF_HARM),
    ("there's no reason to go on anymore", CAT_SELF_HARM),
    ("I feel completely hopeless about all of it", CAT_DISTRESS),
    ("I'm at my breaking point with this team", CAT_DISTRESS),
    ("I just can't do this anymore", CAT_DISTRESS),
    ("my manager has been harassing me for weeks", CAT_HARASSMENT_ABUSE),
    ("he won't stop texting me after I asked", CAT_HARASSMENT_ABUSE),
    ("it makes me feel unsafe to be in the office", CAT_HARASSMENT_ABUSE),
])
def test_lexicon_and_patterns_trip(text, cat):
    v = screen(text)
    assert v.tripped is True
    assert v.category == cat


@pytest.mark.parametrize("text", [
    "Shipped the auth module and fixed two bugs today.",
    "Great standup, the team is aligned on the roadmap.",
    "I was tired but pushed through the code review.",
    "",
    "   ",
])
def test_clean_text_does_not_trip(text):
    assert screen(text).tripped is False


def test_self_harm_wins_over_distress_when_both_match():
    # 'hopeless' (distress) + 'want to die' (self-harm) → the more urgent category wins.
    v = screen("I feel hopeless and I want to die.")
    assert v.tripped is True
    assert v.category == CAT_SELF_HARM


def test_normalization_defeats_newlines_and_width_variants():
    # a phrase split across a newline still trips (whitespace collapsed)
    assert screen("I don't know how much\nlonger I can do this").tripped is True
    # NFKC-folded full-width text still trips
    assert screen("ｓｕｉｃｉｄｅ").tripped is True


def test_model_may_widen_but_never_narrow_the_floor():
    # the floor tripped → a model saying "fine" cannot un-trip it
    floor = screen("I want to die")
    assert combine_with_model(floor, model_tripped=False).tripped is True
    # the floor clean → a model MAY add a trip (widen the net)
    clean = screen("just a normal day")
    assert clean.tripped is False
    widened = combine_with_model(clean, model_tripped=True, model_category=CAT_DISTRESS)
    assert widened.tripped is True
    assert widened.reason == "model"


def test_verdict_is_frozen():
    with pytest.raises(Exception):
        screen("hi").tripped = True  # type: ignore[misc]
