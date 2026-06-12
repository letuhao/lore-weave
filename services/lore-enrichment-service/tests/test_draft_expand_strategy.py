"""Compose mode D — DraftExpandStrategy (technique (e): author-draft expansion).

Pins the 5th technique (tier P1, ungated) and its H0 + book-aware contract:
  * tier P1 / identity / cost (one LLM call, NO embed);
  * every fact origin='enriched:compose_draft' + conf<1.0 + quarantined +
    source_refs = the synthetic ``author_draft`` ref + provenance seed/expand_mode;
  * empty seed_text REFUSED (nothing authored to expand);
  * unrepairable output REFUSED;
  * canon-verify runs (profile-driven anachronism) BUT ③ regurgitation is N/A —
    the proposal grounding is EMPTY (F8), so even a verbatim-copy draft is not
    flagged as source regurgitation;
  * the prompt is book-aware (zh worldview/era vs en) and mode-aware (add_only keeps
    the draft verbatim; rewrite voice-syncs); NO hardcoded model name;
  * the synthetic ref carries the NON-UUID author_draft corpus_id (the recook
    forward guard) and is deterministic by draft hash;
  * a NEW entity (target_ref=None) expands fine (slice-1 new-target path).
"""

from __future__ import annotations

import inspect
from uuid import UUID

import pytest

from app.clients.knowledge import GraphStats
from app.db.book_profile import BookProfile
from app.gaps.model import Gap, resolve_dimensions
from app.generation.provenance import ENRICHED_ORIGIN
from app.strategies.base import CostEstimate, StrategyContext, Technique
from app.strategies.draft_expand import (
    AUTHOR_DRAFT_CORPUS_ID,
    COMPOSE_DRAFT_CONFIDENCE,
    COMPOSE_DRAFT_GAP_COST,
    EXPAND_ADD_ONLY,
    EXPAND_REWRITE,
    DraftExpandError,
    DraftExpandedProposal,
    DraftExpandStrategy,
    author_draft_source_ref,
    build_draft_prompt,
)
from app.verify.canon_verify import FENGSHEN_ANACHRONISM_MARKERS, CanonVerifier

_PROJECT = "33333333-3333-3333-3333-333333333333"
_USER = "44444444-4444-4444-4444-444444444444"

_FENGSHEN = BookProfile(
    language="zh", worldview="《封神演义》世界观", era_policy="商周·封神纪元",
    voice="文言-白话皆可，须与原著语气一致",
)
_NEUTRAL_EN = BookProfile(language="en", worldview="a hard sci-fi colony world")

_DRAFT = "碧遊宮乃通天教主道場，巍峨立於東海之濱，弟子萬千。"


# ── test doubles ──────────────────────────────────────────────────────────────
class _NonEmptyRead:
    """A read port with a non-empty graph so the C12 contradiction check runs."""

    async def get_graph_stats(self, *, jwt: str, project_id: UUID) -> GraphStats:
        return GraphStats(project_id=project_id, entity_count=5, fact_count=9)

    async def build_context(self, *, user_id, project_id=None, message=""):  # pragma: no cover
        raise NotImplementedError


def _verifier(*, canon=None):
    canon = canon or {}

    async def _lookup(entity_name: str, dimension: str):
        return canon.get((entity_name, dimension), [])

    return CanonVerifier(
        read_port=_NonEmptyRead(),
        canon_lookup=_lookup,
        anachronism_markers=FENGSHEN_ANACHRONISM_MARKERS,
    )


def _complete(text: str):
    async def _fn(prompt: str, ctx: StrategyContext) -> str:
        return text
    return _fn


def _gap(kind: str = "location", *, target_ref: str | None = "loc:biyou",
         profile: BookProfile = _FENGSHEN, name: str = "碧遊宮") -> Gap:
    """A gap whose missing dimensions are the kind's full table (nothing present)."""
    specs = resolve_dimensions(kind, language=profile.language)
    return Gap(
        entity_kind=kind,
        canonical_name=name,
        target_ref=target_ref,
        mention_count=3,
        present_dimensions=(),
        missing_dimensions=tuple(s.dimension for s in specs),
    )


def _valid_json_for(kind: str, profile: BookProfile = _FENGSHEN) -> str:
    """Build a JSON object keyed by the kind's localized dimension LABELS (what the
    strategy's repair step expects), filled with PURE-CJK prose (repair_generation
    enforces a CJK ratio for a zh book, so the value must not lean on the en label)."""
    specs = resolve_dimensions(kind, language=profile.language)
    import json
    return json.dumps({s.label: "此乃作者草稿扩写后的内容描述。" for s in specs}, ensure_ascii=False)


def _ctx(*, seed=_DRAFT, mode=EXPAND_REWRITE, profile=_FENGSHEN,
         model_ref="gen-ref-uuid") -> StrategyContext:
    return StrategyContext(
        user_id=_USER, project_id=_PROJECT, model_ref=model_ref,
        profile=profile, seed_text=seed, expand_mode=mode,
    )


def _strategy(*, complete=None, canon=None) -> DraftExpandStrategy:
    return DraftExpandStrategy(
        complete=complete or _complete(_valid_json_for("location")),
        verifier=_verifier(canon=canon),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. tier / identity / cost
# ═══════════════════════════════════════════════════════════════════════════════
def test_compose_draft_is_p1_technique():
    s = _strategy()
    assert s.technique is Technique.COMPOSE_DRAFT
    assert s.technique.tier.value == "P1"
    assert s.key == "compose_draft"


def test_cost_is_generation_only_no_embed():
    # P1, metered. One LLM completion per gap, NO embed (no retrieval) — so the
    # pre-charge is below fabrication (multi-pass + KG assembly).
    from app.jobs.cost import RETRIEVAL_GAP_COST
    from app.strategies.fabrication import FABRICATION_GAP_COST

    s = _strategy()
    est = s.estimate_cost([object(), object()])
    assert isinstance(est, CostEstimate)
    assert est.cost == COMPOSE_DRAFT_GAP_COST * 2
    assert COMPOSE_DRAFT_GAP_COST < FABRICATION_GAP_COST
    assert COMPOSE_DRAFT_GAP_COST > RETRIEVAL_GAP_COST  # generation leg, not embed-only


# ═══════════════════════════════════════════════════════════════════════════════
# 2. H0 — every fact author-seeded, quarantined, never canon
# ═══════════════════════════════════════════════════════════════════════════════
async def test_every_fact_is_h0_author_seeded():
    s = _strategy()
    results = await s.run([_gap()], _ctx(mode=EXPAND_ADD_ONLY))
    assert len(results) == 1
    res: DraftExpandedProposal = results[0]
    specs = resolve_dimensions("location", language="zh")
    assert [f.dimension for f in res.facts] == [s.label for s in specs]
    for f in res.facts:
        assert f.origin == f"{ENRICHED_ORIGIN}:compose_draft"
        assert f.origin != "glossary"
        assert f.technique == "compose_draft"
        assert 0.0 < f.confidence < 1.0
        assert f.confidence == COMPOSE_DRAFT_CONFIDENCE
        assert f.pending_validation is True
        assert f.review_status == "proposed"
        # synthetic authored provenance (F3) — one author_draft ref, no corpus.
        assert len(f.source_refs) == 1
        assert f.source_refs[0].corpus_id == AUTHOR_DRAFT_CORPUS_ID
        assert f.provenance.get("seed") == "author_draft"
        assert f.provenance.get("expand_mode") == EXPAND_ADD_ONLY


async def test_new_entity_target_ref_none_expands():
    # slice-1 new-target path: a never-seen entity (target_ref=None) expands fine;
    # the anchor is minted only at PROMOTE (writeback resolve-or-create).
    s = _strategy()
    results = await s.run([_gap(target_ref=None, name="新天地")], _ctx())
    res = results[0]
    assert res.proposal.target_ref is None
    assert res.proposal.canonical_name == "新天地"
    assert all(f.target_ref is None for f in res.facts)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. seed required / unrepairable refused
# ═══════════════════════════════════════════════════════════════════════════════
async def test_empty_seed_text_refused():
    s = _strategy()
    with pytest.raises(DraftExpandError, match="seed_text"):
        await s.run([_gap()], _ctx(seed="   "))


async def test_unrepairable_output_refused():
    s = _strategy(complete=_complete("这不是 JSON，纯属胡言乱语。"))
    with pytest.raises(DraftExpandError):
        await s.run([_gap()], _ctx())


# ═══════════════════════════════════════════════════════════════════════════════
# 4. canon-verify runs; ③ regurgitation is N/A (empty grounding, F8)
# ═══════════════════════════════════════════════════════════════════════════════
async def test_canon_verify_runs_and_quarantined():
    s = _strategy()
    res = (await s.run([_gap()], _ctx()))[0]
    assert res.verify is not None
    assert res.verify.is_quarantined is True
    assert res.proposal.has_grounding() is False  # empty grounding by design


async def test_regurgitation_not_flagged_for_draft():
    # Even if the model echoes the draft VERBATIM, ③ regurgitation compares output
    # against the provided CORPUS — D has none (empty grounding) — so it is N/A (F8).
    import json
    specs = resolve_dimensions("location", language="zh")
    echo = json.dumps({s.label: _DRAFT for s in specs}, ensure_ascii=False)
    s = _strategy(complete=_complete(echo))
    res = (await s.run([_gap()], _ctx(mode=EXPAND_ADD_ONLY)))[0]
    kinds = {f.kind.value for f in res.verify.result.flags}
    assert "regurgitation" not in kinds


# ═══════════════════════════════════════════════════════════════════════════════
# 5. prompt — book-aware + mode-aware, draft framed as quoted material
# ═══════════════════════════════════════════════════════════════════════════════
def _proposal_for(kind="location", profile=_FENGSHEN, target_ref="loc:biyou"):
    s = DraftExpandStrategy(complete=_complete(""), verifier=_verifier())
    return s._build_proposal(_gap(kind, target_ref=target_ref, profile=profile),
                             _ctx(profile=profile))


def test_prompt_zh_add_only_keeps_draft_verbatim():
    prompt = build_draft_prompt(_proposal_for(), _DRAFT, EXPAND_ADD_ONLY, _FENGSHEN)
    assert _DRAFT in prompt                 # the author's draft is included
    assert "逐字" in prompt or "保留" in prompt  # KEEP-verbatim instruction
    assert "商周" in prompt or "封神" in prompt    # book-aware era/worldview
    assert "JSON" in prompt


def test_prompt_zh_rewrite_voice_syncs():
    prompt = build_draft_prompt(_proposal_for(), _DRAFT, EXPAND_REWRITE, _FENGSHEN)
    assert "改写" in prompt
    assert _DRAFT in prompt


def test_prompt_en_for_non_zh_book():
    prompt = build_draft_prompt(
        _proposal_for(profile=_NEUTRAL_EN), "Draft text here.", EXPAND_ADD_ONLY, _NEUTRAL_EN
    )
    assert "Author's draft" in prompt
    assert "VERBATIM" in prompt
    assert "封神" not in prompt and "商周" not in prompt  # NOT hardcoded Fengshen
    assert "sci-fi colony" in prompt                       # worldview surfaced


def test_no_hardcoded_model_name_in_source():
    src = inspect.getsource(DraftExpandStrategy) + inspect.getsource(build_draft_prompt)
    for needle in ("gpt-", "claude-3", "claude-4", "qwen/", "qwen3", "bge-m3",
                   "text-embedding-", "gemma-3", "llama-"):
        assert needle.lower() not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. synthetic author_draft ref — non-UUID corpus_id (recook forward guard) + stable
# ═══════════════════════════════════════════════════════════════════════════════
def test_author_draft_ref_is_non_uuid_and_deterministic():
    import uuid as _uuid

    ref = author_draft_source_ref(_DRAFT)
    assert ref.corpus_id == AUTHOR_DRAFT_CORPUS_ID
    assert ref.score == 0.0
    # the corpus_id is deliberately NOT a UUID — the recook license resolver's
    # UUID(corpus_id) would fail LOUD if a compose_draft proposal ever reached it.
    with pytest.raises(ValueError):
        _uuid.UUID(ref.corpus_id)
    # deterministic: same draft → same ref, different draft → different chunk_id.
    assert author_draft_source_ref(_DRAFT).chunk_id == ref.chunk_id
    assert author_draft_source_ref(_DRAFT + "x").chunk_id != ref.chunk_id


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DraftExpandPipeline — JobPipeline adapter the runner drives
# ═══════════════════════════════════════════════════════════════════════════════
async def test_pipeline_run_gap_returns_compose_draft_stage():
    from app.jobs.stages import DraftExpandPipeline

    pipe = DraftExpandPipeline(strategy=_strategy())
    assert pipe.technique_value() == "compose_draft"
    stage = await pipe.run_gap(_gap(), _ctx())
    assert stage.proposal.canonical_name == "碧遊宮"
    assert [f.technique for f in stage.facts] == ["compose_draft"] * len(stage.facts)
    assert stage.verify is not None
    # source_refs projected from the synthetic author_draft ref (no corpus grounding)
    assert len(stage.source_refs) == 1
    assert stage.source_refs[0]["corpus_id"] == AUTHOR_DRAFT_CORPUS_ID


async def test_pipeline_empty_seed_raises_draft_expand_error():
    from app.jobs.stages import DraftExpandPipeline

    pipe = DraftExpandPipeline(strategy=_strategy())
    with pytest.raises(DraftExpandError):
        await pipe.run_gap(_gap(), _ctx(seed=""))


# ═══════════════════════════════════════════════════════════════════════════════
# 8. gate — compose_draft is P1 (ungated): selectable even with the gate LOCKED
# ═══════════════════════════════════════════════════════════════════════════════
async def test_compose_draft_selectable_when_gate_locked():
    # P1 + ungated: unlike fabrication/recook (P2/P3), a locked eval gate must NOT
    # block compose_draft — it expands the author's OWN draft, not corpus/canon.
    from app.strategies.factory import GateAwareStrategyFactory, LiveGateStatus

    async def _locked_reader(user_id, project_id, suite_version):
        return LiveGateStatus.locked(suite_version)

    factory = GateAwareStrategyFactory(
        gate_reader=_locked_reader, strategies=[_strategy()]
    )
    reg = await factory.build_registry(user_id=_USER, project_id=_PROJECT)
    assert reg.is_active(Technique.COMPOSE_DRAFT)
    selected = await factory.select(
        Technique.COMPOSE_DRAFT, user_id=_USER, project_id=_PROJECT
    )
    assert selected.technique is Technique.COMPOSE_DRAFT
