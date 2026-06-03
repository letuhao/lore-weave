"""C6 — gap MODEL tests: schema, determinism, pinned fixture ordering, H0 purity.

These tests pin the EXACT scores + ordering of the 4 locked 封神演义 LOCATIONs so
the C7 engine has a golden expected-output to reproduce. They also assert the
model is PURE DATA (no I/O imports, no proposal/source_type fields) per H0.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.gaps.model import (
    DIMENSIONS_BY_KIND,
    LOCATION_DIMENSIONS,
    Dimension,
    EntityKind,
    Gap,
    rank_gaps,
    rank_score,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "gaps_fengshen.json"
)
LOCKED_PLACES = ["玉虛宮", "碧遊宮／金鰲島", "蓬萊", "陳塘關"]


# ── fixture loading ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def fengshen_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _gap_from_entry(entry: dict) -> Gap:
    return Gap(
        entity_kind=EntityKind(entry["entity_kind"]),
        canonical_name=entry["canonical_name"],
        target_ref=entry.get("target_ref"),
        mention_count=entry["mention_count"],
        present_dimensions=[Dimension(d) for d in entry["present_dimensions"]],
        missing_dimensions=[Dimension(d) for d in entry["missing_dimensions"]],
    )


@pytest.fixture(scope="module")
def fengshen_gaps(fengshen_fixture: dict) -> list[Gap]:
    return [_gap_from_entry(e) for e in fengshen_fixture["gaps"]]


# ── dimension table / spec ──────────────────────────────────────────────────


def test_location_dimension_set_is_exactly_the_locked_five() -> None:
    dims = [spec.dimension for spec in LOCATION_DIMENSIONS]
    assert dims == [
        Dimension.HISTORY,
        Dimension.GEOGRAPHY,
        Dimension.CULTURE,
        Dimension.FEATURES,
        Dimension.INHABITANTS,
    ]


def test_chinese_labels_are_source_faithful_not_romanized() -> None:
    by_dim = {s.dimension: s.label for s in LOCATION_DIMENSIONS}
    assert by_dim[Dimension.HISTORY] == "历史"
    assert by_dim[Dimension.GEOGRAPHY] == "地理"
    assert by_dim[Dimension.CULTURE] == "文化"
    # features / inhabitants are intentionally English per the locked set.
    assert by_dim[Dimension.FEATURES] == "features"
    assert by_dim[Dimension.INHABITANTS] == "inhabitants"


def test_required_vs_optional_split() -> None:
    required = {s.dimension for s in LOCATION_DIMENSIONS if s.required}
    optional = {s.dimension for s in LOCATION_DIMENSIONS if not s.required}
    assert required == {Dimension.HISTORY, Dimension.GEOGRAPHY, Dimension.CULTURE}
    assert optional == {Dimension.FEATURES, Dimension.INHABITANTS}


def test_all_builtin_kinds_modeled_and_unknown_falls_back_to_generic() -> None:
    # De-bias C1 (KB3): every built-in kind has a table; an unknown kind falls
    # back to GENERIC (never KeyError / skip).
    from app.gaps.model import GENERIC_DIMENSIONS, dimensions_for

    for kind in (EntityKind.LOCATION, EntityKind.CHARACTER, EntityKind.ITEM,
                 EntityKind.FACTION, EntityKind.EVENT):
        assert kind in DIMENSIONS_BY_KIND
        assert len(dimensions_for(kind)) >= 3
    # unknown / unmodeled kind → GENERIC, no raise
    assert dimensions_for("deity") is GENERIC_DIMENSIONS
    assert dimensions_for("location") is LOCATION_DIMENSIONS


def test_dimension_spec_is_frozen_and_weights_positive() -> None:
    spec = LOCATION_DIMENSIONS[0]
    with pytest.raises(ValidationError):
        spec.weight = 99.0  # type: ignore[misc]
    assert all(s.weight > 0 for s in LOCATION_DIMENSIONS)


def test_entity_kind_values_match_c2_schema_vocabulary() -> None:
    # C2's enrichment_proposal.entity_kind stores lowercase 'location'.
    assert EntityKind.LOCATION.value == "location"


# ── Gap schema validation ───────────────────────────────────────────────────


def test_gap_requires_at_least_one_missing_dimension() -> None:
    with pytest.raises(ValidationError):
        Gap(
            entity_kind=EntityKind.LOCATION,
            canonical_name="完整之地",
            present_dimensions=list(Dimension),
            missing_dimensions=[],
        )


def test_gap_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        Gap(
            entity_kind=EntityKind.LOCATION,
            canonical_name="",
            missing_dimensions=[Dimension.HISTORY],
        )


def test_gap_rejects_negative_mention_count() -> None:
    with pytest.raises(ValidationError):
        Gap(
            entity_kind=EntityKind.LOCATION,
            canonical_name="负数之地",
            mention_count=-1,
            missing_dimensions=[Dimension.HISTORY],
        )


def test_gap_is_frozen_immutable() -> None:
    g = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="蓬萊",
        missing_dimensions=[Dimension.HISTORY],
    )
    with pytest.raises(ValidationError):
        g.canonical_name = "别处"  # type: ignore[misc]


def test_completeness_and_missing_required_counts() -> None:
    g = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="陳塘關",
        mention_count=32,
        present_dimensions=[Dimension.INHABITANTS, Dimension.HISTORY],
        missing_dimensions=[Dimension.GEOGRAPHY, Dimension.CULTURE, Dimension.FEATURES],
    )
    assert g.completeness() == pytest.approx(0.4)  # 2 of 5 present
    assert g.missing_required_count() == 2  # geography + culture (history present)


# ── ranking: determinism ────────────────────────────────────────────────────


def test_rank_score_is_deterministic_across_repeated_calls() -> None:
    g = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="玉虛宮",
        mention_count=55,
        present_dimensions=[Dimension.INHABITANTS],
        missing_dimensions=[
            Dimension.HISTORY,
            Dimension.GEOGRAPHY,
            Dimension.CULTURE,
            Dimension.FEATURES,
        ],
    )
    scores = {rank_score(g) for _ in range(50)}
    assert len(scores) == 1  # identical float every call


def test_rank_score_independent_of_missing_dimension_order() -> None:
    # Permuting the missing-dimension order must not change the score
    # (guards against any set/dict-iteration-order dependence).
    dims = [Dimension.HISTORY, Dimension.GEOGRAPHY, Dimension.CULTURE]
    g1 = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="甲地",
        mention_count=10,
        missing_dimensions=dims,
    )
    g2 = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="甲地",
        mention_count=10,
        missing_dimensions=list(reversed(dims)),
    )
    assert rank_score(g1) == rank_score(g2)


def test_more_mentions_ranks_higher_all_else_equal() -> None:
    base = dict(
        entity_kind=EntityKind.LOCATION,
        missing_dimensions=[Dimension.HISTORY, Dimension.GEOGRAPHY],
    )
    high = Gap(canonical_name="多", mention_count=50, **base)
    low = Gap(canonical_name="少", mention_count=2, **base)
    assert rank_score(high) > rank_score(low)


def test_more_missing_required_ranks_higher_all_else_equal() -> None:
    three = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="缺三",
        mention_count=10,
        missing_dimensions=[Dimension.HISTORY, Dimension.GEOGRAPHY, Dimension.CULTURE],
    )
    one = Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name="缺一",
        mention_count=10,
        missing_dimensions=[Dimension.HISTORY],
    )
    assert rank_score(three) > rank_score(one)


# ── ranking: pinned fixture ordering + scores (golden for C7) ───────────────


def test_fixture_has_all_four_locked_places(fengshen_gaps: list[Gap]) -> None:
    names = {g.canonical_name for g in fengshen_gaps}
    assert names == set(LOCKED_PLACES)


def test_every_fixture_classifies_all_five_dimensions(
    fengshen_gaps: list[Gap],
) -> None:
    all_dims = set(Dimension)
    for g in fengshen_gaps:
        classified = set(g.present_dimensions) | set(g.missing_dimensions)
        assert classified == all_dims, f"{g.canonical_name} miss-classifies a dim"
        # present and missing must be disjoint.
        assert not (set(g.present_dimensions) & set(g.missing_dimensions))


def test_pinned_ranking_order_and_scores(
    fengshen_gaps: list[Gap], fengshen_fixture: dict
) -> None:
    ranked = rank_gaps(fengshen_gaps)
    order = [r.gap.canonical_name for r in ranked]

    # Pinned, deterministic order — this is the golden output C7 must reproduce.
    assert order == ["蓬萊", "玉虛宮", "碧遊宮／金鰲島", "陳塘關"]
    assert order == fengshen_fixture["_meta"]["expected_ranking_order"]

    # Pinned exact scores (rounded to model precision).
    expected = {
        "蓬萊": 29.384354,
        "玉虛宮": 28.0,
        "碧遊宮／金鰲島": 27.31585,
        "陳塘關": 18.686216,
    }
    by_name = {r.gap.canonical_name: r.score for r in ranked}
    assert by_name == expected
    # Fixture's recorded scores must agree with the model.
    assert {k: float(v) for k, v in fengshen_fixture["_meta"]["expected_scores"].items()} == expected

    # ranks are 1..4, contiguous, strictly increasing with position.
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def test_ranking_is_stable_across_input_order(fengshen_gaps: list[Gap]) -> None:
    forward = [r.gap.canonical_name for r in rank_gaps(fengshen_gaps)]
    backward = [r.gap.canonical_name for r in rank_gaps(list(reversed(fengshen_gaps)))]
    assert forward == backward  # input order must not affect the result


def test_score_ties_break_by_canonical_name() -> None:
    # Two identical-score gaps with different names sort by name ascending.
    common = dict(
        entity_kind=EntityKind.LOCATION,
        mention_count=10,
        missing_dimensions=[Dimension.HISTORY, Dimension.GEOGRAPHY],
    )
    a = Gap(canonical_name="乙", **common)
    b = Gap(canonical_name="甲", **common)
    assert rank_score(a) == rank_score(b)
    order = [r.gap.canonical_name for r in rank_gaps([a, b])]
    assert order == ["乙", "甲"] or order == sorted(["乙", "甲"])
    # explicit: ascending name tie-break
    assert order == sorted(["甲", "乙"])


# ── H0 purity: model describes ABSENCE only, no canon-leak fields ───────────


def test_gap_carries_no_enriched_content_or_source_type() -> None:
    # H0: a Gap must NOT expose generated content, source_type, confidence,
    # or a proposal id — it only describes what is missing.
    forbidden = {"content", "source_type", "confidence", "proposal_id", "origin"}
    assert forbidden.isdisjoint(set(Gap.model_fields))


def test_model_module_has_no_io_or_llm_imports() -> None:
    # The model must be pure data — no httpx/asyncpg/openai/embedding imports.
    import app.gaps.model as model_mod

    src = Path(model_mod.__file__).read_text(encoding="utf-8")
    for banned in ("httpx", "asyncpg", "openai", "litellm", "requests", "neo4j"):
        assert banned not in src, f"model.py must not import {banned} (C7 boundary)"


def test_no_hardcoded_model_names_in_module() -> None:
    import app.gaps.model as model_mod

    src = Path(model_mod.__file__).read_text(encoding="utf-8").lower()
    for banned in ("qwen", "bge-m3", "gemma", "gpt-", "text-embedding"):
        assert banned not in src, f"no hardcoded model name allowed ({banned})"


# ── salience factor sanity (deterministic, monotonic) ───────────────────────


def test_salience_factor_monotonic_and_bounded_below() -> None:
    from app.gaps.model import _salience_factor

    assert _salience_factor(0) == 1.0
    assert _salience_factor(1) >= 1.0
    assert _salience_factor(55) > _salience_factor(28) > _salience_factor(1)
    # pure log function — no surprises.
    assert _salience_factor(55) == 1.0 + math.log1p(55.0) / math.log1p(55.0)
