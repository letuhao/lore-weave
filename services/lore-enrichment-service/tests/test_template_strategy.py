"""C9 — TemplateStrategy (technique (a): scaffolding) tests.

Pins the first concrete enrichment technique: a typed :class:`Gap` → an EMPTY,
H0-stamped proposal SKELETON with one slot per MISSING dimension, **keyed by the
dimension's source-faithful Chinese label**, values EMPTY (not English stubs).

Adversary focus (brief 09):
  1. H0 leak — assert the NEGATIVE: a scaffold is NEVER source_type='glossary' /
     confidence>=1.0; it is born origin='enrichment', technique='template',
     review_status='proposed', pending_validation=True, 0 < confidence < 1.0.
  2. No hardcoded model/technique drift — no LLM call; dimension keys derive from
     the C6 table, not copy-pasted literals.
  3. Chinese-output — core dimension keys are the Chinese labels (历史/地理/文化);
     placeholders are EMPTY, never English content.
  4. Scope-field loss — Q3 user_id/project_id survive gap → proposal.
  5. Registry/feature-flag — selectable via the C8 registry under 'template'
     (P1 active by default); disabling the flag makes it unselectable.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from app.gaps.model import Dimension, EntityKind, Gap, dimensions_for
from app.strategies.base import StrategyContext, Technique, Tier
from app.strategies.feature_flags import load_feature_flags
from app.strategies.registry import InactiveStrategyError, StrategyRegistry
from app.strategies.template import (
    SCAFFOLD_CONFIDENCE,
    SCAFFOLD_PLACEHOLDER,
    ScaffoldedProposal,
    TemplateStrategy,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "gaps_fengshen.json"

# Chinese labels for the three CORE (required) location dimensions — used ONLY as
# the test's independent expectation (the impl derives them from C6, never from
# this list). features/inhabitants are intentionally English per the locked C6
# dimension set, so they are NOT in this Chinese-key set.
_CHINESE_CORE_KEYS = {"历史", "地理", "文化"}


# ── fixtures ──────────────────────────────────────────────────────────────────
def _load_gaps() -> dict[str, Gap]:
    """Hydrate the C6 golden fixtures into typed Gaps, keyed by canonical name."""
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    gaps: dict[str, Gap] = {}
    for entry in data["gaps"]:
        gap = Gap(
            entity_kind=EntityKind(entry["entity_kind"]),
            canonical_name=entry["canonical_name"],
            target_ref=entry.get("target_ref"),
            mention_count=entry.get("mention_count", 0),
            present_dimensions=tuple(
                Dimension(d) for d in entry.get("present_dimensions", [])
            ),
            missing_dimensions=tuple(
                Dimension(d) for d in entry.get("missing_dimensions", [])
            ),
        )
        gaps[gap.canonical_name] = gap
    return gaps


@pytest.fixture(scope="module")
def gaps() -> dict[str, Gap]:
    return _load_gaps()


@pytest.fixture()
def context() -> StrategyContext:
    return StrategyContext(user_id="user-7", project_id="proj-42")


def _run(strategy: TemplateStrategy, batch, ctx) -> list[ScaffoldedProposal]:
    return asyncio.run(strategy.run(batch, ctx))


# ── identity / registry ───────────────────────────────────────────────────────
def test_strategy_identity_is_template_p1() -> None:
    s = TemplateStrategy()
    assert s.technique is Technique.TEMPLATE
    assert s.key == "template"
    assert s.tier is Tier.P1


def test_resolves_through_registry_by_template_key() -> None:
    reg = StrategyRegistry()
    reg.register(TemplateStrategy())
    # P1 active by default → selectable by enum and by string key
    assert isinstance(reg.select(Technique.TEMPLATE), TemplateStrategy)
    assert isinstance(reg.select("template"), TemplateStrategy)
    assert reg.is_active("template")
    assert any(isinstance(s, TemplateStrategy) for s in reg.list_active())


def test_disabled_flag_makes_template_unselectable() -> None:
    flags = load_feature_flags(env={"ENRICH_STRATEGY_TEMPLATE_ENABLED": "0"})
    reg = StrategyRegistry(flags=flags)
    reg.register(TemplateStrategy())
    with pytest.raises(InactiveStrategyError):
        reg.select("template")
    assert not reg.is_active("template")
    assert reg.list_active() == []


# ── scaffold shape: one slot per MISSING dimension, Chinese core keys ─────────
def test_scaffold_has_one_slot_per_missing_dimension(gaps, context) -> None:
    # 玉虛宮: present=[inhabitants] → missing=[history, geography, culture, features]
    gap = gaps["玉虛宮"]
    [proposal] = _run(TemplateStrategy(), [gap], context)

    # exactly one slot per missing dimension
    assert len(proposal.dimensions) == len(gap.missing_dimensions)

    # keys are the C6 labels for the missing dims, in C6 declaration order
    expected_keys = [
        spec.label
        for spec in dimensions_for(gap.entity_kind)
        if spec.dimension in set(gap.missing_dimensions)
    ]
    assert list(proposal.dimensions.keys()) == expected_keys
    # the three core dims are Chinese; 玉虛宮 is missing all three core + features
    assert _CHINESE_CORE_KEYS <= set(proposal.dimensions.keys())
    # a PRESENT dimension is NOT scaffolded (inhabitants is present here)
    assert "inhabitants" not in proposal.dimensions


def test_present_dimension_excluded_from_scaffold(gaps, context) -> None:
    # 陳塘關: present=[inhabitants, history] → those two must be absent from slots
    gap = gaps["陳塘關"]
    [proposal] = _run(TemplateStrategy(), [gap], context)
    assert "历史" not in proposal.dimensions  # history is PRESENT → not scaffolded
    assert "inhabitants" not in proposal.dimensions
    # geography/culture/features are the missing ones
    assert set(proposal.dimensions.keys()) == {"地理", "文化", "features"}


def test_fully_missing_place_scaffolds_all_five(gaps, context) -> None:
    # 蓬萊: missing ALL five → all five slots present, three Chinese + two English
    gap = gaps["蓬萊"]
    [proposal] = _run(TemplateStrategy(), [gap], context)
    assert set(proposal.dimensions.keys()) == {
        "历史", "地理", "文化", "features", "inhabitants",
    }


# ── Chinese-output + EMPTY placeholders (NOT English stubs) ───────────────────
def test_all_placeholders_are_empty_not_stubs(gaps, context) -> None:
    proposals = _run(TemplateStrategy(), list(gaps.values()), context)
    for proposal in proposals:
        assert proposal.is_empty_scaffold()
        for value in proposal.dimensions.values():
            assert value == SCAFFOLD_PLACEHOLDER
            assert value == ""  # empty — no generated content, no English stub


def test_core_dimension_keys_are_chinese(gaps, context) -> None:
    # every scaffolded CORE dimension key is the source-faithful Chinese label,
    # never an English identifier like 'history'/'geography'/'culture'.
    [proposal] = _run(TemplateStrategy(), [gaps["蓬萊"]], context)
    for english in ("history", "geography", "culture"):
        assert english not in proposal.dimensions
    assert _CHINESE_CORE_KEYS <= set(proposal.dimensions.keys())


# ── H0: assert the NEGATIVE (never canon) ─────────────────────────────────────
def test_every_proposal_carries_h0_markers(gaps, context) -> None:
    proposals = _run(TemplateStrategy(), list(gaps.values()), context)
    assert proposals  # non-empty
    for p in proposals:
        assert p.origin == "enrichment"
        assert p.origin != "glossary"          # never authored-canon origin
        assert p.technique == "template"
        assert p.review_status == "proposed"
        assert p.pending_validation is True
        assert 0.0 < p.confidence < 1.0        # H0: never canon (1.0)
        assert p.confidence == SCAFFOLD_CONFIDENCE


def test_confidence_cannot_be_set_to_canon() -> None:
    # a caller cannot construct a canon-looking scaffold: confidence >= 1.0 is
    # rejected by the model (mirrors the C2 schema CHECK < 1.0).
    with pytest.raises(Exception):
        ScaffoldedProposal(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="X", dimensions={"历史": ""}, confidence=1.0,
        )
    with pytest.raises(Exception):
        ScaffoldedProposal(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="X", dimensions={"历史": ""}, confidence=0.0,
        )


def test_no_source_type_glossary_field_anywhere(gaps, context) -> None:
    # the proposal model has no canon-marking field; serialized form must not
    # carry source_type='glossary' nor confidence 1.0.
    [proposal] = _run(TemplateStrategy(), [gaps["玉虛宮"]], context)
    dumped = proposal.model_dump()
    assert dumped.get("origin") == "enrichment"
    assert "glossary" not in json.dumps(dumped, ensure_ascii=False)
    assert dumped["confidence"] < 1.0


# ── Q3 scope preservation ─────────────────────────────────────────────────────
def test_scope_preserved_from_context(gaps) -> None:
    ctx = StrategyContext(user_id="author-99", project_id="reality-3")
    [proposal] = _run(TemplateStrategy(), [gaps["玉虛宮"]], ctx)
    assert proposal.user_id == "author-99"
    assert proposal.project_id == "reality-3"


def test_entity_identity_carried_from_gap(gaps, context) -> None:
    gap = gaps["玉虛宮"]
    [proposal] = _run(TemplateStrategy(), [gap], context)
    assert proposal.entity_kind == gap.entity_kind == "location"
    assert proposal.canonical_name == "玉虛宮"
    assert proposal.target_ref == gap.target_ref


# ── provenance records the source gap + technique (for later cycles) ──────────
def test_provenance_records_technique_and_source_gap(gaps, context) -> None:
    gap = gaps["玉虛宮"]
    [proposal] = _run(TemplateStrategy(), [gap], context)
    prov = proposal.provenance_json
    assert prov["technique"] == "template"
    assert prov["scaffold"] is True
    src = prov["source_gap"]
    assert src["canonical_name"] == "玉虛宮"
    assert src["entity_kind"] == "location"
    assert set(src["missing_dimensions"]) == set(gap.missing_dimensions)


# ── determinism + batch order ─────────────────────────────────────────────────
def test_deterministic_same_gap_same_proposal(gaps, context) -> None:
    gap = gaps["玉虛宮"]
    [a] = _run(TemplateStrategy(), [gap], context)
    [b] = _run(TemplateStrategy(), [gap], context)
    assert a.model_dump() == b.model_dump()


def test_run_preserves_batch_order_one_per_gap(gaps, context) -> None:
    batch = [gaps["蓬萊"], gaps["玉虛宮"], gaps["陳塘關"]]
    proposals = _run(TemplateStrategy(), batch, context)
    assert len(proposals) == len(batch)
    assert [p.canonical_name for p in proposals] == [g.canonical_name for g in batch]


def test_empty_batch_yields_no_proposals(context) -> None:
    assert _run(TemplateStrategy(), [], context) == []


# ── cost: scaffolding is free (no LLM/eval), units count gaps ─────────────────
def test_estimate_cost_is_zero_and_counts_gaps(gaps) -> None:
    batch = list(gaps.values())
    est = TemplateStrategy().estimate_cost(batch)
    assert est.technique is Technique.TEMPLATE
    assert est.gap_count == len(batch)
    assert est.units == float(len(batch))
    assert est.cost == 0.0  # pure scaffolding has no provider cost


# ── scope/boundary: no LLM/embed/model-name in the module source ──────────────
def test_module_has_no_llm_or_model_names() -> None:
    # Guard against scope creep: NO LLM/HTTP/embedding client imported or used,
    # NO hardcoded model name. Inspect the EXECUTABLE lines only (a docstring may
    # legitimately say "NO embedding call"); a comment/docstring is not a call.
    src = inspect.getsource(__import__("app.strategies.template", fromlist=["x"]))
    code_lines = [
        ln for ln in src.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines).lower()
    # model-name / client literals must never appear as code at all
    for banned in ("qwen", "bge-m3", "gemma", "gpt-4", "claude-", "llama"):
        assert banned not in code, f"hardcoded model name {banned!r} in template.py"
    # no LLM/HTTP/graph client import
    for client in ("httpx", "openai", "litellm", "requests", "neo4j", "sentence_transformers"):
        assert f"import {client}" not in code, f"scope creep import {client!r}"
        assert f"from {client}" not in code, f"scope creep import {client!r}"
