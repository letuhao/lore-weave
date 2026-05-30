"""C7 — gap-detection ENGINE tests (M1b).

The engine turns per-entity dimension *coverage* (what the KG knows about each
canon LOCATION) into a typed, ranked ``Gap`` list, using the C6 model's frozen
dimension table + ranking. These tests pin the EXACT ranked output for the 4
locked 封神演义 LOCATIONs.

Golden values are NOT reverse-engineered from the engine — they are the C6
fixture's own ``_meta.expected_ranking_order`` / ``expected_scores`` (computed by
the C6 ``rank_score`` model in cycle 6, before this engine existed). The engine
must REPRODUCE them from coverage input.

Covers (per brief acceptance):
  * fixture coverage → expected ranked gaps (exact dimensions + exact order +
    exact scores).
  * a fully-described place yields NO gap.
  * a sparse place yields a gap with the right N missing dims.
  * determinism: two runs → byte-identical ranked output; input order independent.
  * Q6 graceful degradation: Null / empty-graph port → ``[]`` (never raises);
    None-deref safety on missing dimensions.
  * LLM-free / DB-write-free boundary (no banned imports, no model names).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from app.clients.knowledge import GraphStats
from app.clients.port import NullKnowledgeRead
from app.gaps.engine import (
    EntityCoverage,
    GapDetectionEngine,
    detect_gaps,
    detect_ranked_gaps,
)
from app.gaps.model import Dimension, EntityKind, Gap, GapRanking, dimensions_for

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gaps_fengshen.json"
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000007")
JWT = "test.jwt.token"


# ── fixture → coverage input (the engine's real input shape) ─────────────────


@pytest.fixture(scope="module")
def fengshen_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _coverage_from_entry(entry: dict) -> EntityCoverage:
    """Build engine input from a fixture entry using ONLY the present dims.

    The engine derives `missing` itself from the dimension table — we feed it
    only what the KG "knows" (present_dimensions), never the precomputed
    missing list, so the test exercises real gap derivation, not a copy.
    """
    return EntityCoverage(
        entity_kind=EntityKind(entry["entity_kind"]),
        canonical_name=entry["canonical_name"],
        target_ref=entry.get("target_ref"),
        mention_count=entry["mention_count"],
        present_dimensions=tuple(Dimension(d) for d in entry["present_dimensions"]),
    )


@pytest.fixture(scope="module")
def fengshen_coverages(fengshen_fixture: dict) -> list[EntityCoverage]:
    return [_coverage_from_entry(e) for e in fengshen_fixture["gaps"]]


@pytest.fixture
def engine() -> GapDetectionEngine:
    return GapDetectionEngine()


# ── core: coverage → typed gaps (derivation correctness) ─────────────────────


def test_engine_derives_missing_dimensions_from_present(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    gaps = engine.detect(fengshen_coverages)
    by_name = {g.canonical_name: g for g in gaps}

    # 玉虛宮: present inhabitants → missing the other 4.
    assert set(by_name["玉虛宮"].missing_dimensions) == {
        Dimension.HISTORY,
        Dimension.GEOGRAPHY,
        Dimension.CULTURE,
        Dimension.FEATURES,
    }
    # 蓬萊: present nothing → missing all 5.
    assert set(by_name["蓬萊"].missing_dimensions) == set(Dimension)
    # 陳塘關: present inhabitants + history → missing geography/culture/features.
    assert set(by_name["陳塘關"].missing_dimensions) == {
        Dimension.GEOGRAPHY,
        Dimension.CULTURE,
        Dimension.FEATURES,
    }


def test_engine_preserves_present_dims_and_metadata(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    gaps = {g.canonical_name: g for g in engine.detect(fengshen_coverages)}
    g = gaps["陳塘關"]
    assert set(g.present_dimensions) == {Dimension.INHABITANTS, Dimension.HISTORY}
    assert g.mention_count == 32
    assert g.target_ref == "fengshen:location:陳塘關"
    assert g.entity_kind == EntityKind.LOCATION
    # present ∪ missing partitions the whole dimension set (no dim lost).
    assert set(g.present_dimensions) | set(g.missing_dimensions) == set(Dimension)
    assert not (set(g.present_dimensions) & set(g.missing_dimensions))


def test_missing_dimensions_follow_canonical_enum_order(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    # missing_dimensions must come out in Dimension-declaration order, not
    # input/set order (determinism of the derived tuple itself).
    gaps = {g.canonical_name: g for g in engine.detect(fengshen_coverages)}
    g = gaps["玉虛宮"]
    canonical = [
        d for d in dimensions_for(EntityKind.LOCATION) if d.dimension in set(g.missing_dimensions)
    ]
    assert list(g.missing_dimensions) == [s.dimension for s in canonical]


# ── fully-described place → NO gap ───────────────────────────────────────────


def test_fully_described_place_yields_no_gap(engine: GapDetectionEngine) -> None:
    complete = EntityCoverage(
        entity_kind=EntityKind.LOCATION,
        canonical_name="完整之地",
        mention_count=10,
        present_dimensions=tuple(Dimension),  # all 5 present
    )
    sparse = EntityCoverage(
        entity_kind=EntityKind.LOCATION,
        canonical_name="蓬萊",
        mention_count=28,
        present_dimensions=(),
    )
    gaps = engine.detect([complete, sparse])
    names = {g.canonical_name for g in gaps}
    assert "完整之地" not in names  # no gap for a complete place
    assert "蓬萊" in names  # the sparse one still surfaces


def test_sparse_place_gap_has_expected_missing_count(
    engine: GapDetectionEngine,
) -> None:
    cov = EntityCoverage(
        entity_kind=EntityKind.LOCATION,
        canonical_name="半描之地",
        mention_count=5,
        present_dimensions=(Dimension.HISTORY, Dimension.GEOGRAPHY),
    )
    [gap] = engine.detect([cov])
    assert len(gap.missing_dimensions) == 3  # culture/features/inhabitants
    assert gap.missing_required_count() == 1  # only culture is required+missing


# ── pinned ranked output (golden — reproduces C6 fixture _meta) ──────────────


def test_ranked_gaps_match_pinned_fixture_order_and_scores(
    engine: GapDetectionEngine,
    fengshen_coverages: list[EntityCoverage],
    fengshen_fixture: dict,
) -> None:
    ranked = engine.detect_ranked(fengshen_coverages)
    assert all(isinstance(r, GapRanking) for r in ranked)

    order = [r.gap.canonical_name for r in ranked]
    # Golden order is the C6 fixture's own recorded order (蓬萊>玉虛宮>碧遊宮>陳塘關).
    assert order == fengshen_fixture["_meta"]["expected_ranking_order"]
    assert order == ["蓬萊", "玉虛宮", "碧遊宮／金鰲島", "陳塘關"]

    # Golden scores are the C6 fixture's recorded expected_scores.
    by_name = {r.gap.canonical_name: r.score for r in ranked}
    expected = {
        k: float(v) for k, v in fengshen_fixture["_meta"]["expected_scores"].items()
    }
    assert by_name == expected

    # ranks contiguous 1..4.
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def test_module_level_helpers_match_engine(
    fengshen_coverages: list[EntityCoverage],
) -> None:
    # The free functions are thin wrappers over the engine — same output.
    eng = GapDetectionEngine()
    assert detect_gaps(fengshen_coverages) == eng.detect(fengshen_coverages)
    assert detect_ranked_gaps(fengshen_coverages) == eng.detect_ranked(
        fengshen_coverages
    )


# ── determinism ──────────────────────────────────────────────────────────────


def test_ranked_output_is_byte_identical_across_runs(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    first = [(r.gap.canonical_name, r.score, r.rank) for r in engine.detect_ranked(
        fengshen_coverages
    )]
    second = [(r.gap.canonical_name, r.score, r.rank) for r in engine.detect_ranked(
        fengshen_coverages
    )]
    assert first == second


def test_ranking_is_independent_of_input_order(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    forward = [r.gap.canonical_name for r in engine.detect_ranked(fengshen_coverages)]
    backward = [
        r.gap.canonical_name
        for r in engine.detect_ranked(list(reversed(fengshen_coverages)))
    ]
    assert forward == backward


def test_equal_score_gaps_break_ties_by_name(engine: GapDetectionEngine) -> None:
    # Two places with identical coverage + mentions → identical score → name
    # tie-break, regardless of input order. The C6 tie-break is Python's default
    # string sort = ASCENDING UNICODE CODE POINT (NOT a CJK/locale collation):
    # for "甲地"(U+7532) vs "乙地"(U+4E59), 乙 sorts first because 0x4E59 < 0x7532.
    common = dict(
        entity_kind=EntityKind.LOCATION,
        mention_count=10,
        present_dimensions=(Dimension.CULTURE, Dimension.FEATURES, Dimension.INHABITANTS),
    )
    a = EntityCoverage(canonical_name="乙地", **common)
    b = EntityCoverage(canonical_name="甲地", **common)
    expected = sorted(["甲地", "乙地"])  # code-point order: ["乙地", "甲地"]
    order = [r.gap.canonical_name for r in engine.detect_ranked([a, b])]
    assert order == expected
    order_rev = [r.gap.canonical_name for r in engine.detect_ranked([b, a])]
    assert order_rev == expected  # input order does not change the tie-break


# ── Q6 graceful degradation ──────────────────────────────────────────────────


async def test_null_port_yields_empty_list(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    # Null port reports an empty graph → no canon mentions → no gaps. Even with
    # coverages handed in, an empty KG means there is nothing to detect against.
    port = NullKnowledgeRead()
    gaps = await engine.detect_ranked_for_project(
        port, jwt=JWT, project_id=PROJECT_ID, coverages=fengshen_coverages
    )
    assert gaps == []


async def test_empty_graph_stats_yields_empty_list(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    class EmptyStatsPort:
        async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
            return GraphStats(project_id=project_id)  # all zeros → is_empty

        async def build_context(self, **_: object) -> object:  # pragma: no cover
            raise AssertionError("engine must not call build_context")

    gaps = await engine.detect_ranked_for_project(
        EmptyStatsPort(), jwt=JWT, project_id=PROJECT_ID, coverages=fengshen_coverages
    )
    assert gaps == []


async def test_nonempty_graph_stats_runs_detection(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    class NonEmptyStatsPort:
        async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
            return GraphStats(project_id=project_id, entity_count=4, fact_count=10)

        async def build_context(self, **_: object) -> object:  # pragma: no cover
            raise AssertionError("engine must not call build_context")

    ranked = await engine.detect_ranked_for_project(
        NonEmptyStatsPort(), jwt=JWT, project_id=PROJECT_ID, coverages=fengshen_coverages
    )
    order = [r.gap.canonical_name for r in ranked]
    assert order == ["蓬萊", "玉虛宮", "碧遊宮／金鰲島", "陳塘關"]


def test_empty_coverage_list_returns_empty(engine: GapDetectionEngine) -> None:
    assert engine.detect([]) == []
    assert engine.detect_ranked([]) == []


def test_detect_never_raises_on_complete_only(engine: GapDetectionEngine) -> None:
    # A coverage with every dimension present must not raise (it is simply not a
    # gap) — guards against the Gap validator (which rejects zero-missing) leaking.
    complete = EntityCoverage(
        entity_kind=EntityKind.LOCATION,
        canonical_name="完整",
        present_dimensions=tuple(Dimension),
    )
    assert engine.detect([complete]) == []
    assert engine.detect_ranked([complete]) == []


def test_returned_gaps_are_typed_gap_instances(
    engine: GapDetectionEngine, fengshen_coverages: list[EntityCoverage]
) -> None:
    for g in engine.detect(fengshen_coverages):
        assert isinstance(g, Gap)


# ── boundary: LLM-free / DB-write-free engine ───────────────────────────────


def test_engine_module_has_no_io_or_llm_imports() -> None:
    import app.gaps.engine as engine_mod

    src = Path(engine_mod.__file__).read_text(encoding="utf-8")
    # The engine reads through the C1 port abstraction — it must NOT import a
    # concrete network/DB/LLM client directly, and must NEVER write.
    for banned in ("httpx", "asyncpg", "openai", "litellm", "requests", "neo4j"):
        assert banned not in src, f"engine.py must not import {banned} (C7 boundary)"
    for write_word in ("INSERT", "UPDATE ", "DELETE", "execute("):
        assert write_word not in src, f"engine.py must not write ({write_word})"


def test_no_hardcoded_model_names_in_engine() -> None:
    import app.gaps.engine as engine_mod

    src = Path(engine_mod.__file__).read_text(encoding="utf-8").lower()
    for banned in ("qwen", "bge-m3", "gemma", "gpt-", "text-embedding", "claude-", "llama"):
        assert banned not in src, f"no hardcoded model name allowed ({banned})"
