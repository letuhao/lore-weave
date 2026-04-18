"""K17.10 — Golden-set extraction quality eval harness.

Pure logic. Loads annotated fixtures, scores a real extraction
output against expected, and reports macro-averaged precision /
recall / FP-trap-rate.

Split from the pytest entry (`test_extraction_eval.py`) so the
matching+scoring logic is testable without LLM calls. See
`tests/unit/test_eval_harness.py` for deterministic unit coverage
of this module.

Reference: KSA §9.9, K17.10 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

import yaml

from app.db.neo4j_repos.canonical import canonicalize_entity_name

# K17.5 predicate normalizer — intentional private-API import so the
# eval uses the EXACT normalization the extractor applies. Duplicating
# this would cause silent quality-eval drift if K17.5 changes.
from app.extraction.llm_relation_extractor import _normalize_predicate

__all__ = [
    "ExpectedEntity",
    "ExpectedRelation",
    "ExpectedEvent",
    "ExpectedTrap",
    "ChapterFixture",
    "ActualExtraction",
    "ChapterScore",
    "AggregateScore",
    "load_chapter_fixture",
    "iter_chapter_fixtures",
    "score_chapter",
    "aggregate_scores",
    "DEFAULT_EVENT_OVERLAP_THRESHOLD",
]


# ── Schema ──────────────────────────────────────────────────────────

# Event summary matching: LLMs paraphrase heavily. 0.50 token overlap
# keeps "Alice follows the White Rabbit into a hole" matched against
# "Alice chases the Rabbit down a rabbit hole" while rejecting "Alice
# wakes up under a tree" (unrelated).
DEFAULT_EVENT_OVERLAP_THRESHOLD = 0.50


@dataclass(frozen=True)
class ExpectedEntity:
    name: str
    kind: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExpectedRelation:
    subject: str
    predicate: str
    object: str
    polarity: str = "affirm"  # "affirm" | "negate" — matches LLM extractor output


@dataclass(frozen=True)
class ExpectedEvent:
    summary: str
    participants: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedTrap:
    kind: str  # "entity" | "relation" | "event"
    name: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    summary: str | None = None
    participants: tuple[str, ...] = ()  # event traps: match participants too
    reason: str = ""


@dataclass
class ChapterFixture:
    name: str  # directory name, e.g. "alice_ch01"
    text: str
    entities: list[ExpectedEntity]
    relations: list[ExpectedRelation]
    events: list[ExpectedEvent]
    traps: list[ExpectedTrap]
    source: dict[str, Any]


@dataclass
class ActualExtraction:
    """Extractor output flattened for scoring.

    Strings only — canonicalization happens in the matchers.
    """

    entities: list[tuple[str, str]]  # (name, kind)
    relations: list[tuple[str, str, str, str]]  # (subj, pred, obj, polarity)
    events: list[tuple[str, tuple[str, ...]]]  # (summary, participants)


@dataclass
class ChapterScore:
    chapter: str
    tp: int
    fp: int
    fn: int
    fp_trap: int
    trap_total: int
    precision: float
    recall: float
    fp_trap_rate: float


@dataclass
class AggregateScore:
    per_chapter: list[ChapterScore] = field(default_factory=list)
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_fp_trap_rate: float = 0.0


# ── Fixture loading ─────────────────────────────────────────────────


def load_chapter_fixture(chapter_dir: Path) -> ChapterFixture:
    """Load a single `{chapter_dir}/chapter.txt` + `expected.yaml`."""
    text = (chapter_dir / "chapter.txt").read_text(encoding="utf-8")
    expected_raw = yaml.safe_load(
        (chapter_dir / "expected.yaml").read_text(encoding="utf-8")
    )

    entities = [
        ExpectedEntity(
            name=e["name"],
            kind=e["kind"],
            aliases=tuple(e.get("aliases", []) or []),
        )
        for e in (expected_raw.get("entities") or [])
    ]
    relations = [
        ExpectedRelation(
            subject=r["subject"],
            predicate=r["predicate"],
            object=r["object"],
            polarity=r.get("polarity", "affirm"),
        )
        for r in (expected_raw.get("relations") or [])
    ]
    events = [
        ExpectedEvent(
            summary=ev["summary"],
            participants=tuple(ev.get("participants", []) or []),
        )
        for ev in (expected_raw.get("events") or [])
    ]
    traps = [
        ExpectedTrap(
            kind=t["kind"],
            name=t.get("name"),
            subject=t.get("subject"),
            predicate=t.get("predicate"),
            object=t.get("object"),
            summary=t.get("summary"),
            participants=tuple(t.get("participants", []) or []),
            reason=t.get("reason", ""),
        )
        for t in (expected_raw.get("traps") or [])
    ]
    return ChapterFixture(
        name=chapter_dir.name,
        text=text,
        entities=entities,
        relations=relations,
        events=events,
        traps=traps,
        source=expected_raw.get("source") or {},
    )


def iter_chapter_fixtures(golden_root: Path) -> Iterable[ChapterFixture]:
    """Yield every chapter fixture under `golden_root`, sorted by name."""
    for chapter_dir in sorted(p for p in golden_root.iterdir() if p.is_dir()):
        yield load_chapter_fixture(chapter_dir)


# ── Matching ────────────────────────────────────────────────────────


def _canon_name(s: str) -> str:
    return canonicalize_entity_name(s)


def _canon_pred(s: str) -> str:
    return _normalize_predicate(s)


def _entity_canons(e: ExpectedEntity) -> set[str]:
    return {_canon_name(e.name)} | {_canon_name(a) for a in e.aliases}


def _entity_matches_expected(
    actual_name: str, expected: ExpectedEntity
) -> bool:
    return _canon_name(actual_name) in _entity_canons(expected)


def _event_overlap(actual_summary: str, expected_summary: str) -> float:
    """Jaccard-lite token overlap: |intersection| / |expected tokens|.

    Asymmetric on purpose — we care that the expected summary's ideas
    appear in the actual, not vice versa. Actual summaries from LLMs
    sometimes add inferred context that shouldn't hurt the match.
    """
    a_tokens = {t for t in actual_summary.lower().split() if len(t) > 2}
    e_tokens = {t for t in expected_summary.lower().split() if len(t) > 2}
    if not e_tokens:
        return 0.0
    return len(a_tokens & e_tokens) / len(e_tokens)


# ── Scoring ─────────────────────────────────────────────────────────


def score_chapter(
    fixture: ChapterFixture,
    actual: ActualExtraction,
    *,
    event_overlap_threshold: float = DEFAULT_EVENT_OVERLAP_THRESHOLD,
) -> ChapterScore:
    """Macro scores for one chapter.

    Unified TP / FP / FN across all three extraction kinds: treats
    each extraction as one "item" so the chapter-level rates don't
    get skewed by the ratio between entities / relations / events.
    """
    # Entities — match on canonical name AND kind (lowercased).
    matched_expected_ents: set[int] = set()
    ent_tp = 0
    ent_fp = 0
    for act_name, act_kind in actual.entities:
        hit = False
        for i, exp in enumerate(fixture.entities):
            if i in matched_expected_ents:
                continue
            if (
                _entity_matches_expected(act_name, exp)
                and act_kind.lower() == exp.kind.lower()
            ):
                matched_expected_ents.add(i)
                ent_tp += 1
                hit = True
                break
        if not hit:
            ent_fp += 1
    ent_fn = len(fixture.entities) - len(matched_expected_ents)

    # Relations — exact triple equality on canonical form. Subject/
    # object match either the expected entity's canonical name or any
    # of its aliases' canonical forms.
    alias_lookup: dict[str, set[str]] = {
        _canon_name(e.name): _entity_canons(e) for e in fixture.entities
    }

    def _rel_endpoint_matches(actual_endpoint: str, expected_endpoint: str) -> bool:
        a = _canon_name(actual_endpoint)
        e = _canon_name(expected_endpoint)
        if a == e:
            return True
        # Alias hop — actual side
        for canons in alias_lookup.values():
            if a in canons and e in canons:
                return True
        return False

    matched_expected_rels: set[int] = set()
    rel_tp = 0
    rel_fp = 0
    for act_subj, act_pred, act_obj, act_polarity in actual.relations:
        hit = False
        for i, exp in enumerate(fixture.relations):
            if i in matched_expected_rels:
                continue
            if (
                _rel_endpoint_matches(act_subj, exp.subject)
                and _canon_pred(act_pred) == _canon_pred(exp.predicate)
                and _rel_endpoint_matches(act_obj, exp.object)
                and act_polarity == exp.polarity
            ):
                matched_expected_rels.add(i)
                rel_tp += 1
                hit = True
                break
        if not hit:
            rel_fp += 1
    rel_fn = len(fixture.relations) - len(matched_expected_rels)

    # Events — strict participant-set equality (not subset/superset)
    # on canonical form + token-overlap on summary above threshold.
    # An extra or missing participant makes the event FP+FN, not TP.
    matched_expected_evts: set[int] = set()
    evt_tp = 0
    evt_fp = 0
    for act_summary, act_participants in actual.events:
        a_part_canons = {_canon_name(p) for p in act_participants}
        hit = False
        for i, exp in enumerate(fixture.events):
            if i in matched_expected_evts:
                continue
            e_part_canons = {_canon_name(p) for p in exp.participants}
            if (
                a_part_canons == e_part_canons
                and _event_overlap(act_summary, exp.summary)
                >= event_overlap_threshold
            ):
                matched_expected_evts.add(i)
                evt_tp += 1
                hit = True
                break
        if not hit:
            evt_fp += 1
    evt_fn = len(fixture.events) - len(matched_expected_evts)

    # Traps — actual extractions matching a trap entry.
    fp_trap = 0
    for trap in fixture.traps:
        if trap.kind == "entity" and trap.name:
            tname = _canon_name(trap.name)
            if any(_canon_name(n) == tname for n, _ in actual.entities):
                fp_trap += 1
        elif trap.kind == "relation" and trap.subject and trap.predicate and trap.object:
            for a_s, a_p, a_o, _a_pol in actual.relations:
                if (
                    _canon_name(a_s) == _canon_name(trap.subject)
                    and _canon_pred(a_p) == _canon_pred(trap.predicate)
                    and _canon_name(a_o) == _canon_name(trap.object)
                ):
                    fp_trap += 1
                    break
        elif trap.kind == "event" and trap.summary:
            for a_sum, a_parts in actual.events:
                overlap_ok = (
                    _event_overlap(a_sum, trap.summary) >= event_overlap_threshold
                )
                # If trap specifies participants, require set match too
                # (symmetric with event TP matching). If no participants
                # on the trap, summary overlap alone triggers the hit.
                if trap.participants:
                    trap_parts = {_canon_name(p) for p in trap.participants}
                    actual_parts = {_canon_name(p) for p in a_parts}
                    if overlap_ok and actual_parts == trap_parts:
                        fp_trap += 1
                        break
                elif overlap_ok:
                    fp_trap += 1
                    break

    tp = ent_tp + rel_tp + evt_tp
    fp = ent_fp + rel_fp + evt_fp
    fn = ent_fn + rel_fn + evt_fn
    # Precision denominator includes trap hits — extracting a trap is
    # a "real" false positive, just a specially labeled one, and we
    # don't want the precision metric to reward trap-hitters.
    denom_p = tp + fp + fp_trap
    denom_r = tp + fn
    precision = tp / denom_p if denom_p else 0.0
    recall = tp / denom_r if denom_r else 0.0
    trap_total = len(fixture.traps)
    fp_trap_rate = fp_trap / trap_total if trap_total else 0.0

    return ChapterScore(
        chapter=fixture.name,
        tp=tp,
        fp=fp,
        fn=fn,
        fp_trap=fp_trap,
        trap_total=trap_total,
        precision=precision,
        recall=recall,
        fp_trap_rate=fp_trap_rate,
    )


def aggregate_scores(scores: list[ChapterScore]) -> AggregateScore:
    """Macro-mean across chapters — one big chapter doesn't dominate."""
    if not scores:
        return AggregateScore()
    return AggregateScore(
        per_chapter=list(scores),
        avg_precision=mean(s.precision for s in scores),
        avg_recall=mean(s.recall for s in scores),
        avg_fp_trap_rate=mean(s.fp_trap_rate for s in scores),
    )
