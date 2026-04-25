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
    "ChapterAttribution",
    "CategoryAttribution",
    "AggregateScore",
    "load_chapter_fixture",
    "iter_chapter_fixtures",
    "score_chapter",
    "score_chapter_with_attribution",
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
    # C-EVAL-FIX-FORM Fix #4 — annotation gap accounting. A relation
    # FP is reclassified as fp_annotation_gap (excluded from FP for
    # lenient precision) when the LLM extracted a relation that is
    # plausibly correct but missing from the conservative fixture.
    # Criterion: subject + object both canonicalize to fixture
    # entities, predicate is canonical, polarity affirm, no trap.
    fp_annotation_gap: int = 0
    # Lenient precision counts annotation gaps as not-FP. Strict
    # precision (`precision` field above) keeps current semantics
    # for hard-gate compatibility.
    precision_lenient: float = 0.0


@dataclass
class AggregateScore:
    per_chapter: list[ChapterScore] = field(default_factory=list)
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    avg_fp_trap_rate: float = 0.0
    avg_precision_lenient: float = 0.0


@dataclass
class CategoryAttribution:
    """Per-item TP/FP/FN attribution for one extraction category.

    Each list element is a JSON-serializable dict carrying enough
    info (indices + content snapshots) to read the dump file in
    isolation without cross-referencing actual.json. Field shapes
    differ by category — see _build_*_attribution for the schema.
    """

    tp: list[dict] = field(default_factory=list)
    fp: list[dict] = field(default_factory=list)
    fn: list[dict] = field(default_factory=list)
    fp_trap: list[dict] = field(default_factory=list)
    # C-EVAL-FIX-FORM Fix #4 — relations that are plausibly correct
    # (both endpoints fixture entities + canonical predicate +
    # polarity affirm + not a trap) but missing from the conservative
    # fixture annotation. Counted separately from `fp` so lenient
    # precision can exclude them; included in `fp` for strict.
    fp_annotation_gap: list[dict] = field(default_factory=list)


@dataclass
class ChapterAttribution:
    """Diagnostic attribution dump for one chapter — companion to ChapterScore."""

    chapter: str
    entities: CategoryAttribution = field(default_factory=CategoryAttribution)
    relations: CategoryAttribution = field(default_factory=CategoryAttribution)
    events: CategoryAttribution = field(default_factory=CategoryAttribution)


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


# C-EVAL-FIX-FORM Fix #3 — conservative predicate synonym map for the
# eval harness. ONLY truly equivalent verb pairs are aliased here;
# semantically distinct ones (instructs vs helps, sibling_of vs
# stepsibling_of) are NOT merged. This is harness-side leniency — the
# production canonicalizer in app/extraction/llm_relation_extractor.py
# is unchanged.
_PREDICATE_SYNONYMS: dict[str, str] = {
    # Spatial — all flatten to canonical resides_at
    "lives_at": "resides_at",
    "lives_in": "resides_at",
    "resides_in": "resides_at",
    "dwells_in": "resides_at",
    "dwells_at": "resides_at",
    # Marriage — verb form vs state form
    "marries": "married_to",
    "is_married_to": "married_to",
    # Imprisonment — passive synonyms
    "imprisoned": "imprisoned_by",
    "jailed_by": "imprisoned_by",
}


def _canon_name(s: str) -> str:
    return canonicalize_entity_name(s)


def _canon_pred(s: str) -> str:
    """Canonicalize predicate via production normalizer + harness synonyms.

    Production normalization (lowercase + snake_case) runs first so
    we don't have to enumerate casing variants. Then the synonym map
    folds equivalent verbs onto a single canonical form so the
    fixture and LLM can disagree on surface form (lives_at vs
    resides_at) without scoring as FP+FN.
    """
    base = _normalize_predicate(s)
    return _PREDICATE_SYNONYMS.get(base, base)


# C-EVAL-FIX-FORM Fix #2 — event participants tolerance threshold.
# Strict set-equality penalizes events where LLM extracted the right
# concept but missed 1 minor participant. Default Jaccard 0.6 allows
# 1-off flexibility on 3+ participant events while still rejecting
# wholly-different-actor matches. Override via env var on test side.
DEFAULT_PARTICIPANTS_JACCARD = 0.6


# C-EVAL-FIX-FORM Fix #4 — canonical predicate vocabulary mirroring
# the relation_extraction.md prompt's suggested-set (post C-PRED-ALIGN
# expansion). A relation FP qualifies for annotation-gap reclassif-
# ication only when its predicate is in this set — predicates outside
# the set are treated as LLM error / hallucination and stay as FP.
_CANONICAL_PREDICATES: frozenset[str] = frozenset({
    # Kinship
    "child_of", "stepchild_of", "sibling_of", "stepsibling_of", "married_to",
    # Mentorship
    "mentor_of", "disciple_of", "instructs",
    # Authority/affiliation
    "commands", "serves", "imprisoned_by", "works_for", "member_of",
    # Spatial
    "located_in", "located_on", "lives_in", "lives_with", "resides_at",
    "sits_by",
    # Action/plot
    "helps", "follows", "courts", "rents", "owns", "born_from",
    # Social/state
    "knows", "trusts", "enemy_of",
})


def _participants_jaccard(actual: set[str], expected: set[str]) -> float:
    """Symmetric Jaccard on canonicalized participant sets.

    Penalizes BOTH extra and missing participants, unlike a one-sided
    subset metric — this prevents an LLM from gaming high recall by
    flooding events with unrelated participant names.
    """
    if not actual and not expected:
        return 1.0
    union = actual | expected
    intersect = actual & expected
    return len(intersect) / len(union) if union else 0.0


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
    participants_jaccard_threshold: float = DEFAULT_PARTICIPANTS_JACCARD,
) -> ChapterScore:
    """Macro scores for one chapter.

    Unified TP / FP / FN across all three extraction kinds: treats
    each extraction as one "item" so the chapter-level rates don't
    get skewed by the ratio between entities / relations / events.
    """
    score, _attribution = score_chapter_with_attribution(
        fixture, actual,
        event_overlap_threshold=event_overlap_threshold,
        participants_jaccard_threshold=participants_jaccard_threshold,
    )
    return score


def score_chapter_with_attribution(
    fixture: ChapterFixture,
    actual: ActualExtraction,
    *,
    event_overlap_threshold: float = DEFAULT_EVENT_OVERLAP_THRESHOLD,
    participants_jaccard_threshold: float = DEFAULT_PARTICIPANTS_JACCARD,
) -> tuple[ChapterScore, ChapterAttribution]:
    """Identical match logic to ``score_chapter`` but also returns
    per-item TP/FP/FN attribution suitable for diagnostic dump.

    The attribution payload is intentionally JSON-friendly — every
    list element is a plain dict so callers can serialize directly
    via ``json.dumps`` without custom encoders.
    """
    attribution = ChapterAttribution(chapter=fixture.name)

    # Entities — match on canonical name AND kind (lowercased).
    matched_expected_ents: set[int] = set()
    for act_idx, (act_name, act_kind) in enumerate(actual.entities):
        hit = False
        for i, exp in enumerate(fixture.entities):
            if i in matched_expected_ents:
                continue
            if (
                _entity_matches_expected(act_name, exp)
                and act_kind.lower() == exp.kind.lower()
            ):
                matched_expected_ents.add(i)
                attribution.entities.tp.append({
                    "actual_idx": act_idx,
                    "expected_idx": i,
                    "actual_name": act_name,
                    "actual_kind": act_kind,
                    "expected_name": exp.name,
                    "expected_kind": exp.kind,
                    "matched_via": (
                        "canonical_name" if _canon_name(act_name) == _canon_name(exp.name)
                        else "alias"
                    ),
                })
                hit = True
                break
        if not hit:
            attribution.entities.fp.append({
                "actual_idx": act_idx,
                "actual_name": act_name,
                "actual_kind": act_kind,
            })
    for i, exp in enumerate(fixture.entities):
        if i not in matched_expected_ents:
            attribution.entities.fn.append({
                "expected_idx": i,
                "expected_name": exp.name,
                "expected_kind": exp.kind,
                "expected_aliases": list(exp.aliases),
            })
    ent_tp = len(attribution.entities.tp)
    ent_fp = len(attribution.entities.fp)
    ent_fn = len(attribution.entities.fn)

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

    # C-EVAL-FIX-FORM Fix #4 — for annotation-gap classification we
    # need to know whether an arbitrary endpoint canonicalizes to ANY
    # fixture entity (or its aliases). _rel_endpoint_matches() only
    # answers "match THIS expected endpoint" — too narrow.
    all_fixture_canons: set[str] = set()
    for canons in alias_lookup.values():
        all_fixture_canons |= canons

    def _endpoint_in_fixture(endpoint: str) -> bool:
        return _canon_name(endpoint) in all_fixture_canons

    # Trap relation set for annotation-gap exclusion check.
    trap_relation_keys: set[tuple[str, str, str]] = set()
    for trap in fixture.traps:
        if trap.kind == "relation" and trap.subject and trap.predicate and trap.object:
            trap_relation_keys.add((
                _canon_name(trap.subject),
                _canon_pred(trap.predicate),
                _canon_name(trap.object),
            ))

    matched_expected_rels: set[int] = set()
    for act_idx, (act_subj, act_pred, act_obj, act_polarity) in enumerate(actual.relations):
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
                attribution.relations.tp.append({
                    "actual_idx": act_idx,
                    "expected_idx": i,
                    "actual": [act_subj, act_pred, act_obj, act_polarity],
                    "expected": [exp.subject, exp.predicate, exp.object, exp.polarity],
                })
                hit = True
                break
        if not hit:
            # C-EVAL-FIX-FORM Fix #4 — classify FP into either
            # "annotation_gap" (LLM correct, fixture incomplete) or
            # "real" FP. Annotation-gap criterion (all four):
            #   1. Both endpoints canonicalize to a fixture entity
            #   2. Predicate (post-synonym-canon) is in the
            #      canonical 28-vocab
            #   3. Polarity is "affirm" (no auto-accept on negation)
            #   4. NOT in trap_relation_keys (don't whitewash traps)
            canon_pred = _canon_pred(act_pred)
            is_trap_match = (
                _canon_name(act_subj),
                canon_pred,
                _canon_name(act_obj),
            ) in trap_relation_keys
            is_gap = (
                _endpoint_in_fixture(act_subj)
                and _endpoint_in_fixture(act_obj)
                and canon_pred in _CANONICAL_PREDICATES
                and act_polarity == "affirm"
                and not is_trap_match
            )
            if is_gap:
                attribution.relations.fp_annotation_gap.append({
                    "actual_idx": act_idx,
                    "actual": [act_subj, act_pred, act_obj, act_polarity],
                    "reason": "Both endpoints in fixture entity list, predicate canonical, polarity affirm — likely correct but missing from conservative annotation",
                })
            else:
                attribution.relations.fp.append({
                    "actual_idx": act_idx,
                    "actual": [act_subj, act_pred, act_obj, act_polarity],
                })
    for i, exp in enumerate(fixture.relations):
        if i not in matched_expected_rels:
            attribution.relations.fn.append({
                "expected_idx": i,
                "expected": [exp.subject, exp.predicate, exp.object, exp.polarity],
            })
    rel_tp = len(attribution.relations.tp)
    rel_fp = len(attribution.relations.fp)
    rel_fp_annotation_gap = len(attribution.relations.fp_annotation_gap)
    rel_fn = len(attribution.relations.fn)

    # Events — symmetric Jaccard on canonicalized participants
    # (>= participants_jaccard_threshold) + token-overlap on summary
    # >= event_overlap_threshold. C-EVAL-FIX-FORM Fix #2 — replaces
    # prior strict set equality which penalized "off by one minor
    # participant" matches even when summary clearly identified the
    # same event.
    matched_expected_evts: set[int] = set()
    for act_idx, (act_summary, act_participants) in enumerate(actual.events):
        a_part_canons = {_canon_name(p) for p in act_participants}
        hit = False
        for i, exp in enumerate(fixture.events):
            if i in matched_expected_evts:
                continue
            e_part_canons = {_canon_name(p) for p in exp.participants}
            overlap = _event_overlap(act_summary, exp.summary)
            participants_jaccard = _participants_jaccard(a_part_canons, e_part_canons)
            if (
                participants_jaccard >= participants_jaccard_threshold
                and overlap >= event_overlap_threshold
            ):
                matched_expected_evts.add(i)
                attribution.events.tp.append({
                    "actual_idx": act_idx,
                    "expected_idx": i,
                    "actual_summary": act_summary,
                    "actual_participants": list(act_participants),
                    "expected_summary": exp.summary,
                    "expected_participants": list(exp.participants),
                    "overlap_score": round(overlap, 3),
                    "participants_jaccard": round(participants_jaccard, 3),
                })
                hit = True
                break
        if not hit:
            attribution.events.fp.append({
                "actual_idx": act_idx,
                "actual_summary": act_summary,
                "actual_participants": list(act_participants),
            })
    for i, exp in enumerate(fixture.events):
        if i not in matched_expected_evts:
            attribution.events.fn.append({
                "expected_idx": i,
                "expected_summary": exp.summary,
                "expected_participants": list(exp.participants),
            })
    evt_tp = len(attribution.events.tp)
    evt_fp = len(attribution.events.fp)
    evt_fn = len(attribution.events.fn)

    # Traps — actual extractions matching a trap entry.
    fp_trap = 0
    for trap_idx, trap in enumerate(fixture.traps):
        if trap.kind == "entity" and trap.name:
            tname = _canon_name(trap.name)
            for a_idx, (a_name, a_kind) in enumerate(actual.entities):
                if _canon_name(a_name) == tname:
                    fp_trap += 1
                    attribution.entities.fp_trap.append({
                        "actual_idx": a_idx,
                        "actual_name": a_name,
                        "actual_kind": a_kind,
                        "trap_idx": trap_idx,
                        "trap_name": trap.name,
                        "trap_reason": trap.reason,
                    })
                    break
        elif trap.kind == "relation" and trap.subject and trap.predicate and trap.object:
            for a_idx, (a_s, a_p, a_o, _a_pol) in enumerate(actual.relations):
                if (
                    _canon_name(a_s) == _canon_name(trap.subject)
                    and _canon_pred(a_p) == _canon_pred(trap.predicate)
                    and _canon_name(a_o) == _canon_name(trap.object)
                ):
                    fp_trap += 1
                    attribution.relations.fp_trap.append({
                        "actual_idx": a_idx,
                        "actual": [a_s, a_p, a_o, _a_pol],
                        "trap_idx": trap_idx,
                        "trap": [trap.subject, trap.predicate, trap.object],
                        "trap_reason": trap.reason,
                    })
                    break
        elif trap.kind == "event" and trap.summary:
            for a_idx, (a_sum, a_parts) in enumerate(actual.events):
                overlap_ok = (
                    _event_overlap(a_sum, trap.summary) >= event_overlap_threshold
                )
                # If trap specifies participants, require set match too
                # (symmetric with event TP matching). If no participants
                # on the trap, summary overlap alone triggers the hit.
                hit_trap = False
                if trap.participants:
                    trap_parts = {_canon_name(p) for p in trap.participants}
                    actual_parts = {_canon_name(p) for p in a_parts}
                    if overlap_ok and actual_parts == trap_parts:
                        hit_trap = True
                elif overlap_ok:
                    hit_trap = True
                if hit_trap:
                    fp_trap += 1
                    attribution.events.fp_trap.append({
                        "actual_idx": a_idx,
                        "actual_summary": a_sum,
                        "actual_participants": list(a_parts),
                        "trap_idx": trap_idx,
                        "trap_summary": trap.summary,
                        "trap_participants": list(trap.participants),
                        "trap_reason": trap.reason,
                    })
                    break

    tp = ent_tp + rel_tp + evt_tp
    fp = ent_fp + rel_fp + evt_fp
    fn = ent_fn + rel_fn + evt_fn
    fp_annotation_gap = rel_fp_annotation_gap
    # Strict precision denominator includes annotation gaps as FP
    # (current/CI behavior). Trap hits also counted — extracting a
    # trap is a "real" FP, just specially labeled.
    denom_p_strict = tp + fp + fp_annotation_gap + fp_trap
    denom_r = tp + fn
    precision = tp / denom_p_strict if denom_p_strict else 0.0
    recall = tp / denom_r if denom_r else 0.0
    # C-EVAL-FIX-FORM Fix #4 — lenient precision EXCLUDES annotation
    # gaps from the FP denominator. Informational only; not used by
    # hard-gate assertion.
    denom_p_lenient = tp + fp + fp_trap
    precision_lenient = tp / denom_p_lenient if denom_p_lenient else 0.0
    trap_total = len(fixture.traps)
    fp_trap_rate = fp_trap / trap_total if trap_total else 0.0

    score = ChapterScore(
        chapter=fixture.name,
        tp=tp,
        fp=fp,
        fn=fn,
        fp_trap=fp_trap,
        trap_total=trap_total,
        precision=precision,
        recall=recall,
        fp_trap_rate=fp_trap_rate,
        fp_annotation_gap=fp_annotation_gap,
        precision_lenient=precision_lenient,
    )
    return score, attribution


def aggregate_scores(scores: list[ChapterScore]) -> AggregateScore:
    """Macro-mean across chapters — one big chapter doesn't dominate."""
    if not scores:
        return AggregateScore()
    return AggregateScore(
        per_chapter=list(scores),
        avg_precision=mean(s.precision for s in scores),
        avg_recall=mean(s.recall for s in scores),
        avg_fp_trap_rate=mean(s.fp_trap_rate for s in scores),
        avg_precision_lenient=mean(s.precision_lenient for s in scores),
    )
