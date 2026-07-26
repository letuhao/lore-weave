"""Scored fixture set for the D-KG-EXTRACTION-CANON-GATE judge accuracy eval.

Each fixture is a (chapter_text, expected_is_contradiction) pair against a
single fixed snapshot: entity "Alice" transitioned to `gone` at from_order
3_000_000. The symbolic pre-filter (`gone_entities_asserted_active`) is
designed to be over-inclusive — every fixture below intentionally contains
the literal name "Alice" so the filter always flags a candidate and the
judge is the thing actually being scored, not the filter.

`expected` encodes the PO-endorsed precedent from `entity_status.py`
("gone→active is advisory, never a standalone hard gate" — a NARRATED
revival is legitimate new canon, not a continuity error) and from the POC's
own live-smoke finding (unexplained cross-chapter revival IS the hard case
a judge must catch). Fixtures are grouped to stress both failure directions:
false positives (blocking legitimate writing) and false negatives (missing
a real continuity error) — the former is judged the costlier failure mode
in a hard-block gate, so FALSE outnumbers TRUE below on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonCheckFixture:
    fixture_id: str
    chapter_text: str
    expected_is_contradiction: bool
    note: str


ALICE_SNAPSHOT = {
    "entities": [
        {
            "entity_id": "eval-alice",
            "name": "Alice",
            "canonical_name": "alice",
            "status": "gone",
            "from_order": 3_000_000,
        }
    ]
}

FIXTURES: list[CanonCheckFixture] = [
    # ── expected: NOT a contradiction (should NOT flag) ──────────────────
    CanonCheckFixture(
        "flashback_memory",
        "He closed his eyes and remembered how Alice used to smile before the accident.",
        False,
        "past-tense memory/flashback",
    ),
    CanonCheckFixture(
        "dream_sequence",
        "In his dream, Alice was laughing again, running through the meadow they once knew.",
        False,
        "dream, explicitly framed as unreal",
    ),
    CanonCheckFixture(
        "metaphorical_ghost",
        "The house still felt haunted by Alice's ghost, though no one dared speak her name.",
        False,
        "figurative language, not a physical-presence assertion",
    ),
    CanonCheckFixture(
        "counterfactual",
        "If Alice were still alive, she would have known exactly what to do.",
        False,
        "explicit counterfactual conditional",
    ),
    CanonCheckFixture(
        "quoted_document",
        "He unfolded the letter. Alice had written in her final days: 'I forgive you all.'",
        False,
        "quoted document authored before death",
    ),
    CanonCheckFixture(
        "reported_past_memory",
        "Tom told the others that Alice had once solved a puzzle just like this one.",
        False,
        "third-person report of a past event",
    ),
    CanonCheckFixture(
        "explained_revival",
        "The necromancer's ritual was complete -- Alice's chest rose with a first ragged breath, and she opened her eyes.",
        False,
        "narrated resurrection is legitimate new canon, not a continuity error",
    ),
    CanonCheckFixture(
        "name_collision_new_person",
        "A woman named Alice Chen walked briskly into the office, clutching a folder of documents.",
        False,
        "different person introduced with a distinguishing surname",
    ),
    CanonCheckFixture(
        "twin_sibling",
        "Alice's twin sister stepped forward, her face an eerie mirror of the one they'd buried.",
        False,
        "explicitly a different person (twin)",
    ),
    CanonCheckFixture(
        "sarcastic_rhetorical",
        "'Oh sure, and next you'll tell me Alice walked out of her grave and cooked breakfast,' he scoffed.",
        False,
        "sarcasm/rhetorical hypothetical, not a narrated fact",
    ),
    # ── expected: IS a contradiction (should flag) ────────────────────────
    CanonCheckFixture(
        "direct_present_action",
        "Alice smiled and picked up her sword, ready for the fight ahead.",
        True,
        "plain present-tense physical action, no explanation",
    ),
    CanonCheckFixture(
        "dialogue_present",
        "'I'm still here,' Alice said, stepping out of the shadows to face him.",
        True,
        "dialogue + present action asserting she is alive",
    ),
    CanonCheckFixture(
        "unexplained_tavern_revival",
        "Alice walked into the tavern as if nothing had happened, ordering a drink like old times.",
        True,
        "the POC's original hard case: unexplained cross-chapter revival",
    ),
    CanonCheckFixture(
        "unexplained_door_burst",
        "Alice burst through the door, breathless, and shouted for everyone to run.",
        True,
        "plain active assertion, no explanation, no hedge",
    ),
    CanonCheckFixture(
        "active_conflict",
        "Alice argued with the guard, refusing to hand over her sword.",
        True,
        "ongoing present-tense conflict, no explanation",
    ),
    CanonCheckFixture(
        "time_skip_ongoing_life",
        "Three years later, Alice ran the bakery on Fifth Street, greeting every customer by name.",
        True,
        "unexplained ongoing life well past the gone transition",
    ),
]
