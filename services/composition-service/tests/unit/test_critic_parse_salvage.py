"""QC-5 C35 — a verdict must not be discarded over one missing comma.

Measured LIVE (C34) against a rebuilt image on lw-iso: on the real 4757-char chapter-10 draft
the shipped critic returned `canon=None raw=0` on **3 of 3** runs. `llm_jobs` ruled out
truncation — `finish_reason=stop`, 2257-2273 tokens each time — and the raw reply was
JSON-shaped and invalid by one character, a `craft_notes` entry with two adjacent values and no
comma between them. The whole object was then refused, discarding the `violations` array ABOVE
it, which had already found and attributed a real rule.

The salvage is narrow on purpose and these tests are what keep it narrow: it repairs the ONE
shape that was observed, it runs only after strict parse and balanced extraction have failed,
and it accepts the result only if the repair actually parses.
"""

from __future__ import annotations

import json

from app.engine.critic import parse_critique_json

#: The shape the live judge emitted, reduced to its essentials. The violation is BEFORE the
#: malformed note, which is the whole point: it was well-formed and thrown away regardless.
LIVE_SHAPE = """{
    "coherence": 5,
    "voice_match": 4,
    "pacing": 3,
    "canon_consistency": 4,
    "violations": [
        {"rule_id": "[R1]", "violated": true, "span": "a span", "why": "a reason"}
    ],
    "craft_notes": [
        {
            "note": "The introduction feels abrupt and does not fit the narrative flow."
            "span": "a quoted fragment"
        }
    ]
}"""


def test_the_live_malformed_reply_is_SALVAGED_with_its_violation_intact():
    out = parse_critique_json(LIVE_SHAPE)
    assert out is not None, "the reply the live critic actually emitted must not be discarded"
    assert out["canon_consistency"] == 4
    assert len(out["violations"]) == 1, (
        "the violations array was well-formed and sat ABOVE the malformed note — losing it to "
        "a comma in craft_notes is the defect, not the note itself"
    )
    assert out["violations"][0]["rule_id"] == "[R1]"


def test_VALID_json_is_untouched():
    """The control arm. A salvage that rewrote well-formed replies would be changing verdicts,
    not rescuing them."""
    good = json.dumps({"coherence": 3, "violations": [], "craft_notes": []})
    assert parse_critique_json(good) == json.loads(good)


def test_genuinely_unparsable_text_still_returns_None():
    """The second control, and the one that matters most: the salvage must not invent an object.
    A parser that guesses its way to a verdict is worse than one that reports none, because
    `critic_unparsable` is a state a consumer can act on and a fabricated score is not."""
    assert parse_critique_json("I read the chapter and it seemed fine to me, honestly.") is None
    assert parse_critique_json("") is None
    assert parse_critique_json("{ this is not json at all ") is None


def test_a_repair_that_does_not_yield_valid_json_is_REFUSED():
    """The comma is inserted, the result still does not parse, so the answer is None — not a
    half-read object. This is the branch that keeps the salvage honest."""
    # 🔴 The first version of this test passed for the WRONG REASON, and a bite is what found
    # it: the input had no closing brace, so the balanced-object scan never completed and the
    # salvage was never reached at all. Deleting the parse check left the test green — a
    # criterion that cannot fail. This input BALANCES, so the salvage does run: the comma is
    # inserted and `nope` is still not valid JSON.
    broken = '{"a": "x"\n    "b": 2, "c": nope}'
    assert parse_critique_json(broken) is None


def test_it_does_not_fire_on_a_reply_that_needs_no_repair():
    """Fenced JSON already round-trips through the strict path; reaching the salvage at all
    would mean the earlier stages had regressed."""
    fenced = '```json\n{"coherence": 4, "violations": []}\n```'
    assert parse_critique_json(fenced) == {"coherence": 4, "violations": []}
