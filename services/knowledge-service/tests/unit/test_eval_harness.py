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
