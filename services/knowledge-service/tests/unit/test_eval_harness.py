"""K17.10 — Unit tests for the golden-set eval harness.

Deterministic coverage of load/match/score. These tests do NOT run
the LLM pipeline — they exercise the scoring logic on synthetic
``ActualExtraction`` inputs.

The LLM-driven end-to-end eval lives in
``tests/quality/test_extraction_eval.py`` and is opt-in via the
``--run-quality`` pytest flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.quality.eval_harness import (
    ActualExtraction,
    ChapterFixture,
    ExpectedEntity,
    ExpectedEvent,
    ExpectedRelation,
    ExpectedTrap,
    aggregate_scores,
    iter_chapter_fixtures,
    load_chapter_fixture,
    score_chapter,
)


# ── Fixture factories ───────────────────────────────────────────────


def _fixture(
    *,
    entities=None,
    relations=None,
    events=None,
    traps=None,
) -> ChapterFixture:
    return ChapterFixture(
        name="test",
        text="irrelevant for scoring tests",
        entities=entities or [],
        relations=relations or [],
        events=events or [],
        traps=traps or [],
        source={},
    )


# ── Entity matching ─────────────────────────────────────────────────


def test_entity_exact_match_case_insensitive():
    fix = _fixture(entities=[ExpectedEntity(name="Alice", kind="person")])
    actual = ActualExtraction(
        entities=[("alice", "person")], relations=[], events=[]
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1
    assert score.fp == 0
    assert score.fn == 0
    assert score.precision == 1.0
    assert score.recall == 1.0


def test_entity_alias_match():
    fix = _fixture(
        entities=[
            ExpectedEntity(
                name="White Rabbit", kind="person", aliases=("Rabbit", "the Rabbit")
            )
        ]
    )
    actual = ActualExtraction(
        entities=[("the Rabbit", "person")], relations=[], events=[]
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1
    assert score.fn == 0


def test_entity_honorific_stripped_via_canonicalizer():
    # canonicalize_entity_name strips honorifics (dr, mr, ms, mrs...).
    fix = _fixture(entities=[ExpectedEntity(name="Watson", kind="person")])
    actual = ActualExtraction(
        entities=[("Dr. Watson", "person")], relations=[], events=[]
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1


def test_entity_false_positive_counted():
    fix = _fixture(entities=[ExpectedEntity(name="Alice", kind="person")])
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Queen", "person")],
        relations=[],
        events=[],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1
    assert score.fp == 1
    assert score.precision == 0.5


def test_entity_false_negative_counted():
    fix = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(name="Rabbit", kind="person"),
        ]
    )
    actual = ActualExtraction(
        entities=[("Alice", "person")], relations=[], events=[]
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1
    assert score.fn == 1
    assert score.recall == 0.5


def test_entity_double_actual_does_not_double_match():
    """Two extracted copies of the same entity should count as 1 TP + 1 FP."""
    fix = _fixture(entities=[ExpectedEntity(name="Alice", kind="person")])
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("alice", "person")],
        relations=[],
        events=[],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1
    assert score.fp == 1


def test_entity_kind_mismatch_is_fp():
    """R1 fix #1: correct name but wrong kind should be FP, not TP."""
    fix = _fixture(entities=[ExpectedEntity(name="Alice", kind="person")])
    actual = ActualExtraction(
        entities=[("Alice", "location")], relations=[], events=[]
    )
    score = score_chapter(fix, actual)
    assert score.tp == 0
    assert score.fp == 1
    assert score.fn == 1


# ── Relation matching ───────────────────────────────────────────────


def test_relation_triple_equality_after_normalization():
    fix = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(
                name="White Rabbit", kind="person", aliases=("Rabbit",)
            ),
        ],
        relations=[
            ExpectedRelation(
                subject="Alice", predicate="follows", object="White Rabbit"
            )
        ],
    )
    # Actual uses alias + different casing + hyphenated predicate
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Rabbit", "person")],
        relations=[("alice", "Follows", "Rabbit", "affirm")],
        events=[],
    )
    score = score_chapter(fix, actual)
    # 2 entities + 1 relation = 3 TP
    assert score.tp == 3


def test_relation_predicate_mismatch_is_fp():
    fix = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(name="Rabbit", kind="person"),
        ],
        relations=[
            ExpectedRelation(subject="Alice", predicate="follows", object="Rabbit")
        ],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Rabbit", "person")],
        relations=[("Alice", "ignores", "Rabbit", "affirm")],
        events=[],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 2  # both entities
    assert score.fp == 1  # wrong predicate
    assert score.fn == 1  # expected relation missing


def test_relation_negate_polarity_does_not_match_affirm():
    """R1 fix #2: a negated relation must not match an affirm expected."""
    fix = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(name="Rabbit", kind="person"),
        ],
        relations=[
            ExpectedRelation(subject="Alice", predicate="follows", object="Rabbit")
        ],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Rabbit", "person")],
        relations=[("Alice", "follows", "Rabbit", "negate")],
        events=[],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 2  # entities match
    assert score.fp == 1  # negated relation is FP
    assert score.fn == 1  # affirm relation unmatched


# ── Event matching ──────────────────────────────────────────────────


def test_event_participant_set_plus_token_overlap():
    fix = _fixture(
        events=[
            ExpectedEvent(
                summary="Alice follows the White Rabbit down a rabbit hole",
                participants=("Alice", "White Rabbit"),
            )
        ]
    )
    # LLM paraphrase with same participants — should match at 0.50 overlap
    actual = ActualExtraction(
        entities=[],
        relations=[],
        events=[
            (
                "alice chases the rabbit down the hole",
                ("Alice", "White Rabbit"),
            )
        ],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1


def test_event_wrong_participants_does_not_match():
    fix = _fixture(
        events=[
            ExpectedEvent(
                summary="Alice follows the Rabbit",
                participants=("Alice", "Rabbit"),
            )
        ]
    )
    actual = ActualExtraction(
        entities=[],
        relations=[],
        events=[
            ("Alice follows the Rabbit", ("Alice", "Queen"))
        ],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 0
    assert score.fp == 1
    assert score.fn == 1


def test_event_low_overlap_does_not_match():
    fix = _fixture(
        events=[
            ExpectedEvent(
                summary="Alice follows the Rabbit down a hole",
                participants=("Alice", "Rabbit"),
            )
        ]
    )
    # Same participants but totally different semantic content.
    actual = ActualExtraction(
        entities=[],
        relations=[],
        events=[("characters stand around idly", ("Alice", "Rabbit"))],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 0
    assert score.fp == 1


# ── Trap handling ───────────────────────────────────────────────────


def test_trap_entity_hit_counts_as_fp_trap_not_fp():
    fix = _fixture(
        entities=[ExpectedEntity(name="Alice", kind="person")],
        traps=[
            ExpectedTrap(
                kind="entity",
                name="the dream",
                reason="hypothetical only",
            )
        ],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("the dream", "concept")],
        relations=[],
        events=[],
    )
    score = score_chapter(fix, actual)
    assert score.tp == 1
    assert score.fp == 1  # "the dream" is not in expected entities → FP
    assert score.fp_trap == 1  # AND it's a trap hit
    assert score.fp_trap_rate == 1.0


def test_trap_relation_hit_counted():
    fix = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(name="Queen", kind="person"),
        ],
        traps=[
            ExpectedTrap(
                kind="relation",
                subject="Alice",
                predicate="meets",
                object="Queen",
                reason="only foreshadowed",
            )
        ],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Queen", "person")],
        relations=[("Alice", "meets", "Queen", "affirm")],
        events=[],
    )
    score = score_chapter(fix, actual)
    assert score.fp_trap == 1
    assert score.fp_trap_rate == 1.0


def test_no_trap_hit_rate_zero():
    fix = _fixture(
        entities=[ExpectedEntity(name="Alice", kind="person")],
        traps=[
            ExpectedTrap(kind="entity", name="the dream", reason="x"),
            ExpectedTrap(kind="entity", name="tomorrow", reason="y"),
        ],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person")], relations=[], events=[]
    )
    score = score_chapter(fix, actual)
    assert score.fp_trap == 0
    assert score.fp_trap_rate == 0.0


def test_trap_event_with_participants_requires_participant_match():
    """R1 fix #4: event trap with participants must check participant set."""
    fix = _fixture(
        traps=[
            ExpectedTrap(
                kind="event",
                summary="Alice meets the Duchess in the garden",
                participants=("Alice", "Duchess"),
                reason="only foreshadowed",
            )
        ],
    )
    # Same summary overlap but different participants — should NOT trigger.
    actual = ActualExtraction(
        entities=[],
        relations=[],
        events=[("Alice meets the Duchess in the garden", ("Alice", "Queen"))],
    )
    score = score_chapter(fix, actual)
    assert score.fp_trap == 0

    # Same summary overlap AND same participants — should trigger.
    actual2 = ActualExtraction(
        entities=[],
        relations=[],
        events=[("Alice meets the Duchess in the garden", ("Alice", "Duchess"))],
    )
    score2 = score_chapter(fix, actual2)
    assert score2.fp_trap == 1


def test_trap_event_without_participants_matches_on_summary_only():
    """Event trap with no participants falls back to summary-only matching."""
    fix = _fixture(
        traps=[
            ExpectedTrap(
                kind="event",
                summary="Alice meets the Duchess in the garden",
                reason="only foreshadowed",
            )
        ],
    )
    actual = ActualExtraction(
        entities=[],
        relations=[],
        events=[("Alice meets the Duchess in the garden", ("Anyone",))],
    )
    score = score_chapter(fix, actual)
    assert score.fp_trap == 1


# ── Aggregate ───────────────────────────────────────────────────────


def test_aggregate_macro_mean_not_weighted_by_size():
    """One chapter with lots of entities shouldn't drown out a chapter
    with few. Macro-mean averages per-chapter rates."""
    big = _fixture(
        entities=[ExpectedEntity(name=f"E{i}", kind="person") for i in range(10)]
    )
    big_actual = ActualExtraction(
        entities=[(f"E{i}", "person") for i in range(10)],
        relations=[],
        events=[],
    )
    small = _fixture(entities=[ExpectedEntity(name="Z", kind="person")])
    small_actual = ActualExtraction(
        entities=[("WRONG", "person")], relations=[], events=[]
    )
    scores = [
        score_chapter(big, big_actual),  # precision 1.0
        score_chapter(small, small_actual),  # precision 0.0
    ]
    agg = aggregate_scores(scores)
    assert agg.avg_precision == 0.5  # macro mean of 1.0 and 0.0
    # If it were micro-weighted the big chapter would dominate.


def test_aggregate_empty_input():
    agg = aggregate_scores([])
    assert agg.avg_precision == 0.0
    assert agg.avg_recall == 0.0
    assert agg.avg_fp_trap_rate == 0.0
    assert agg.per_chapter == []


# ── Fixture loader ──────────────────────────────────────────────────


def test_load_chapter_fixture_parses_real_fixture(tmp_path: Path):
    """Round-trip: write a minimal expected.yaml + chapter.txt, load."""
    chapter_dir = tmp_path / "demo_ch01"
    chapter_dir.mkdir()
    (chapter_dir / "chapter.txt").write_text("A short chapter.", encoding="utf-8")
    (chapter_dir / "expected.yaml").write_text(
        """
source:
  title: Demo
  chapter: 1
entities:
  - name: Alice
    kind: person
    aliases: [Ally]
relations:
  - subject: Alice
    predicate: greets
    object: Alice
events:
  - summary: Alice greets herself
    participants: [Alice]
traps:
  - kind: entity
    name: ghost
    reason: hypothetical
""".strip(),
        encoding="utf-8",
    )

    fixture = load_chapter_fixture(chapter_dir)
    assert fixture.name == "demo_ch01"
    assert fixture.text == "A short chapter."
    assert len(fixture.entities) == 1
    assert fixture.entities[0].aliases == ("Ally",)
    assert len(fixture.relations) == 1
    assert fixture.relations[0].polarity == "affirm"  # default
    assert len(fixture.events) == 1
    assert fixture.events[0].participants == ("Alice",)
    assert len(fixture.traps) == 1
    assert fixture.traps[0].kind == "entity"


def test_iter_chapter_fixtures_sorted(tmp_path: Path):
    for name in ["c_ch", "a_ch", "b_ch"]:
        d = tmp_path / name
        d.mkdir()
        (d / "chapter.txt").write_text("x", encoding="utf-8")
        (d / "expected.yaml").write_text("{}", encoding="utf-8")
    loaded = [f.name for f in iter_chapter_fixtures(tmp_path)]
    assert loaded == ["a_ch", "b_ch", "c_ch"]


# ── C-EVAL-FIX-FORM regression coverage ─────────────────────────────


def test_predicate_synonym_lives_at_matches_resides_at():
    """Fix #3 — `lives_at` (LLM) and `resides_at` (fixture) must score TP."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="Holmes", kind="person"),
            ExpectedEntity(name="Baker Street", kind="place"),
        ],
        relations=[
            ExpectedRelation(
                subject="Holmes", predicate="resides_at", object="Baker Street",
            ),
        ],
    )
    actual = ActualExtraction(
        entities=[("Holmes", "person"), ("Baker Street", "place")],
        relations=[("Holmes", "lives_at", "Baker Street", "affirm")],
        events=[],
    )
    score = score_chapter(fixture, actual)
    assert score.tp == 3  # 2 entities + 1 relation
    assert score.fp == 0
    assert score.fp_annotation_gap == 0


def test_predicate_synonym_marries_matches_married_to():
    """Fix #3 — `marries` (LLM verb form) and `married_to` (fixture state form) must score TP."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="A", kind="person"),
            ExpectedEntity(name="B", kind="person"),
        ],
        relations=[
            ExpectedRelation(subject="A", predicate="married_to", object="B"),
        ],
    )
    actual = ActualExtraction(
        entities=[("A", "person"), ("B", "person")],
        relations=[("A", "marries", "B", "affirm")],
        events=[],
    )
    score = score_chapter(fixture, actual)
    assert score.tp == 3
    assert score.fp == 0


def test_event_participants_jaccard_tolerates_one_off():
    """Fix #2 — Event with 2/3 participant overlap (Jaccard ~0.67) above default 0.6 threshold scores TP."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="A", kind="person"),
            ExpectedEntity(name="B", kind="person"),
            ExpectedEntity(name="C", kind="person"),
        ],
        events=[
            ExpectedEvent(
                summary="A and B and C have a long discussion about the situation",
                participants=("A", "B", "C"),
            ),
        ],
    )
    actual = ActualExtraction(
        entities=[("A", "person"), ("B", "person"), ("C", "person")],
        relations=[],
        events=[
            (
                "A and B have a long discussion about the situation",
                ("A", "B"),
            ),
        ],
    )
    score = score_chapter(fixture, actual)
    # 3 entities + 1 event TP. Without Fix #2 this would be FP+FN (strict equality).
    assert score.tp == 4
    assert score.fp == 0
    assert score.fn == 0


def test_event_participants_jaccard_rejects_disjoint_sets():
    """Fix #2 — completely different participant sets must NOT match even if summary tokens overlap."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="A", kind="person"),
            ExpectedEntity(name="X", kind="person"),
        ],
        events=[
            ExpectedEvent(
                summary="A discusses the weather one quiet afternoon",
                participants=("A",),
            ),
        ],
    )
    actual = ActualExtraction(
        entities=[("A", "person"), ("X", "person")],
        relations=[],
        events=[
            ("X discusses the weather one quiet afternoon", ("X",)),
        ],
    )
    score = score_chapter(fixture, actual)
    # Different participants → Jaccard 0 → no event TP. Event is FP+FN.
    assert score.fn >= 1
    assert score.fp >= 1


def test_relation_annotation_gap_classified_when_endpoints_in_fixture():
    """Fix #4 — LLM-extracted relation with both endpoints + canonical predicate
    + affirm polarity is classified as fp_annotation_gap, not fp.

    Lenient precision excludes the gap; strict precision still includes it.
    """
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="Beth", kind="person"),
            ExpectedEntity(name="Jo", kind="person"),
            ExpectedEntity(name="Meg", kind="person"),
        ],
        relations=[
            # Fixture conservatively annotates only ONE sibling pair.
            ExpectedRelation(subject="Meg", predicate="sibling_of", object="Jo"),
        ],
    )
    actual = ActualExtraction(
        entities=[("Beth", "person"), ("Jo", "person"), ("Meg", "person")],
        relations=[
            ("Meg", "sibling_of", "Jo", "affirm"),    # TP
            ("Beth", "sibling_of", "Jo", "affirm"),   # annotation gap
            ("Beth", "sibling_of", "Meg", "affirm"),  # annotation gap
        ],
        events=[],
    )
    score = score_chapter(fixture, actual)
    # 3 entity TP + 1 relation TP = 4
    assert score.tp == 4
    assert score.fp == 0
    assert score.fp_annotation_gap == 2
    # Lenient precision: 4 / (4 + 0 + 0) = 1.0
    # Strict precision: 4 / (4 + 0 + 2 + 0) = 4/6 ≈ 0.67
    assert score.precision_lenient == pytest.approx(1.0)
    assert score.precision == pytest.approx(4 / 6)


def test_relation_fp_when_endpoint_unknown_not_gap():
    """Fix #4 negative — endpoint outside fixture entity list keeps FP classification."""
    fixture = _fixture(
        entities=[ExpectedEntity(name="Alice", kind="person")],
        relations=[],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person")],
        relations=[("Alice", "sibling_of", "RandomStranger", "affirm")],
        events=[],
    )
    score = score_chapter(fixture, actual)
    assert score.fp_annotation_gap == 0  # Object not in fixture → not a gap
    assert score.fp == 1


def test_relation_fp_when_predicate_not_canonical_not_gap():
    """Fix #4 negative — non-canonical predicate keeps FP classification."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(name="Bob", kind="person"),
        ],
        relations=[],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Bob", "person")],
        # `gossips_about` not in canonical 28-vocab nor in synonym map
        relations=[("Alice", "gossips_about", "Bob", "affirm")],
        events=[],
    )
    score = score_chapter(fixture, actual)
    assert score.fp_annotation_gap == 0
    assert score.fp == 1


def test_relation_negate_polarity_not_gap():
    """Fix #4 negative — polarity 'negate' does NOT auto-qualify as annotation gap."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="Alice", kind="person"),
            ExpectedEntity(name="Bob", kind="person"),
        ],
        relations=[],
    )
    actual = ActualExtraction(
        entities=[("Alice", "person"), ("Bob", "person")],
        relations=[("Alice", "trusts", "Bob", "negate")],
        events=[],
    )
    score = score_chapter(fixture, actual)
    assert score.fp_annotation_gap == 0
    assert score.fp == 1


def test_relation_fp_when_trap_match_not_gap():
    """Fix #4 negative — relation that hits a trap is fp_trap, not annotation gap."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="A", kind="person"),
            ExpectedEntity(name="B", kind="person"),
        ],
        relations=[],
        traps=[
            ExpectedTrap(
                kind="relation",
                subject="A",
                predicate="enemy_of",
                object="B",
                reason="story actually shows them as friends",
            ),
        ],
    )
    actual = ActualExtraction(
        entities=[("A", "person"), ("B", "person")],
        relations=[("A", "enemy_of", "B", "affirm")],
        events=[],
    )
    score = score_chapter(fixture, actual)
    assert score.fp_annotation_gap == 0
    assert score.fp_trap == 1


def test_aggregate_includes_avg_precision_lenient():
    """Aggregate exposes avg_precision_lenient alongside strict avg_precision."""
    fixture = _fixture(
        entities=[
            ExpectedEntity(name="A", kind="person"),
            ExpectedEntity(name="B", kind="person"),
        ],
        relations=[],
    )
    actual = ActualExtraction(
        entities=[("A", "person"), ("B", "person")],
        relations=[("A", "knows", "B", "affirm")],  # annotation gap
        events=[],
    )
    score = score_chapter(fixture, actual)
    agg = aggregate_scores([score])
    assert agg.avg_precision == score.precision
    assert agg.avg_precision_lenient == score.precision_lenient
    assert agg.avg_precision_lenient > agg.avg_precision  # gap excluded
