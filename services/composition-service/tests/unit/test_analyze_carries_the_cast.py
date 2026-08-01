"""The cast must cross the analyze→materialize boundary EXPLICITLY, and nothing may be translated.

Both bugs were found by the third corpus (mainland Chinese, `corpus-cn-webnovel.md`) and both are
structural rather than model failures — which is why these tests assert the CONTRACT, not an output.

1. `ANALYZE_SCHEMA` carried no `characters` field at all. `materialize` therefore had to reconstruct
   the cast from `consistency_anchors`, so a character survived only if they happened to have an
   anchor line. Measured: 3 of 4 came through, and the one lost was 无名者 — "the nameless one" —
   whose entire point is that the document describes him by absence. He had no anchor, so he had no
   way across.

2. The language rule was a LIST OF FIELDS ("keep the source's language for event titles and anchor
   text"), which reads as permission to translate everything else. Measured on the same document:
   `document_summary` came back entirely in English and a mechanic came back as
   `死物道 (Dead Matter Path)`.
"""

from __future__ import annotations

import pathlib

from app.engine.plan_forge import prompts
from app.engine.plan_forge.schemas import ANALYZE_SCHEMA, SPEC_SCHEMA


def test_analyze_can_emit_a_cast_at_all():
    """The grammar must permit the field the prompt asks for, or the model is told to emit something
    the decoder forbids."""
    props = ANALYZE_SCHEMA["properties"]
    assert "characters" in props, "analyze has no cast field — the cast crosses by accident"
    item = props["characters"]["items"]
    assert item["required"] == ["name"], "a name is the one thing a character must have"
    assert set(item["properties"]) >= {"name", "role", "notes"}


def test_analyze_ASKS_for_every_named_person_including_the_barely_described():
    p = prompts.ANALYZE_SYSTEM
    assert "- characters:" in p, "the schema allows a cast the prompt never requests"
    assert "barely described" in p, (
        "the instruction must cover the case that lost 无名者 — a person the source names but "
        "deliberately does not characterise"
    )


def test_materialize_is_told_to_USE_that_cast_not_re_derive_it():
    p = prompts.MATERIALIZE_SYSTEM
    assert "CAST COVERAGE" in p
    assert "consistency_anchors" in p, "the anchors re-derivation must be explicitly forbidden"
    assert "layers" in SPEC_SCHEMA["properties"]


def test_the_language_rule_is_GLOBAL_in_BOTH_prompts():
    """A per-field list is what produced the leak. State it once, over everything."""
    for name, p in (("ANALYZE", prompts.ANALYZE_SYSTEM), ("MATERIALIZE", prompts.MATERIALIZE_SYSTEM)):
        assert "LANGUAGE" in p, f"{name} has no global language rule"
        low = p.lower()
        assert "every human-readable string" in low, f"{name}'s rule is not stated over everything"
        # …and the machine keys are carved out, or the model will "translate" an id
        assert "`id`" in p and "`code`" in p, f"{name} does not exempt the machine keys"


def test_no_prompt_names_one_LANGUAGE_as_the_expected_one():
    """`(natural language, may be Vietnamese)` is fixture residue from the POC's one novel, and it
    biases the read on every document that is not that one."""
    for name, p in (("ANALYZE", prompts.ANALYZE_SYSTEM), ("MATERIALIZE", prompts.MATERIALIZE_SYSTEM)):
        for lang in ("Vietnamese", "tiếng Việt", "Chinese", "English document"):
            assert lang not in p, f"{name} still expects {lang!r} in particular"


def test_the_glossing_failure_mode_is_named_in_the_CODE_not_the_prompt():
    """The leak was a parenthetical GLOSS, not a translation — a shape a reviewer skims past, so it
    is recorded. But in the module, not in the prompt: a system prompt is instructions, and my first
    draft put the whole rationale (including the words "a Chinese document") inside it. The
    fixture-residue test above caught that, which is the test working on its author."""
    src = pathlib.Path(prompts.__file__).read_text(encoding="utf-8")
    assert "parenthetical GLOSS" in src or "parenthetical" in src
    assert "no translations, no parenthetical" in prompts.MATERIALIZE_SYSTEM.lower()


def test_no_prompt_carries_a_LITERAL_a_model_can_copy_out_as_data():
    """A regression I introduced in the same edit that fixed the cast, caught by re-running the other
    corpora rather than assuming a prompt change is local.

    My rule said `keep bracket forms like 【…】 without the brackets`, and the grimdark corpus came
    back with a character literally NAMED `【…】`. The POC already measured that a worked example in a
    prompt hurts (recall to zero in a controlled arm); this is the same failure in miniature — an
    example glyph is data the model can lift.
    """
    for name, p in (("ANALYZE", prompts.ANALYZE_SYSTEM), ("MATERIALIZE", prompts.MATERIALIZE_SYSTEM)):
        for glyph in ("【…】", "【", "】", "«", "»"):
            assert glyph not in p, f"{name} carries {glyph!r} — a model can emit it as a name"
