"""Schema-governed generator pipeline tests (RAID C11).

End-to-end (intra-service, LLM seam MOCKED for determinism): a grounded proposal
(C10) → prompt → mocked completion → repair → H0-tagged facts. Asserts the
acceptance triplet: (a) malformed completion is repaired-or-rejected, (b) EVERY
emitted fact is H0-tagged (origin enriched + non-empty provenance + conf<1.0 +
pending), (c) English-leakage in a Chinese dimension is caught.
"""

from __future__ import annotations

import pytest

from app.generation.generate import (
    GenerationError,
    SchemaGovernedGenerator,
    build_generation_prompt,
)
from app.db.book_profile import BookProfile
from app.generation.provenance import ENRICHED_ORIGIN
from app.retrieval.strategy import GroundedProposal, GroundingRef
from app.strategies.base import StrategyContext

KEYS = ["历史", "地理", "文化"]

# de-bias C1: the prompt is now book-aware. These tests assert the Fengshen (zh)
# behavior, so pass the Fengshen profile (the demo seed equivalent).
_ZH_PROFILE = BookProfile(
    language="zh", worldview="《封神演义》原著", voice="文言-白话皆可，须与原著语气一致"
)

_VALID_COMPLETION = (
    '{"历史": "蓬萊自上古为仙人所居，黄帝问道于此。", '
    '"地理": "地处东海之中，云雾缭绕，凡舟难近。", '
    '"文化": "岛上修真者重道法、轻俗务，岁时祭海。"}'
)


def _grounding(n: int = 2) -> list[GroundingRef]:
    return [
        GroundingRef(
            corpus_id=f"corpus-{i}",
            chunk_id=f"chunk-{i}",
            chunk_index=i,
            excerpt=f"蓬萊在渤海之东，仙人居之，第{i}段。",
            score=round(0.9 - i * 0.1, 6),
        )
        for i in range(n)
    ]


def _proposal(*, dims=None, grounding=None) -> GroundedProposal:
    return GroundedProposal(
        user_id="u1",
        project_id="p1",
        entity_kind="location",
        canonical_name="蓬萊",
        target_ref="loc:penglai",
        dimensions={k: "" for k in (dims if dims is not None else KEYS)},
        grounding=grounding if grounding is not None else _grounding(),
    )


def _ctx(model_ref="emb-or-gen-ref") -> StrategyContext:
    return StrategyContext(user_id="u1", project_id="p1", model_ref=model_ref)


def _const_complete(text: str):
    async def _fn(prompt: str, ctx: StrategyContext) -> str:
        return text
    return _fn


# ── happy path ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generates_one_fact_per_missing_dimension():
    gen = SchemaGovernedGenerator(complete=_const_complete(_VALID_COMPLETION))
    facts = await gen.generate(_proposal(), _ctx())
    assert [f.dimension for f in facts] == KEYS  # C6 order, one per dim
    assert all(f.content for f in facts)


@pytest.mark.asyncio
async def test_every_emitted_fact_is_h0_tagged():
    gen = SchemaGovernedGenerator(complete=_const_complete(_VALID_COMPLETION))
    facts = await gen.generate(_proposal(), _ctx())
    assert facts
    for f in facts:
        assert f.origin == f"{ENRICHED_ORIGIN}:retrieval"
        assert f.origin != "glossary"
        assert f.provenance  # non-empty
        assert 0.0 < f.confidence < 1.0
        assert f.pending_validation is True
        assert f.review_status == "proposed"
        assert len(f.source_refs) == 2  # carried from grounding


@pytest.mark.asyncio
async def test_fact_provenance_cites_grounding_and_model_ref():
    gen = SchemaGovernedGenerator(complete=_const_complete(_VALID_COMPLETION))
    facts = await gen.generate(_proposal(), _ctx(model_ref="my-ref"))
    prov = facts[0].provenance
    assert prov["model_ref"] == "my-ref"  # ref, never a model name
    assert prov["technique"] == "retrieval"
    assert len(prov["grounding_ref_ids"]) == 2
    assert prov["grounding_count"] == 2


@pytest.mark.asyncio
async def test_completion_with_fences_and_prose_is_repaired():
    raw = f"好的：\n```json\n{_VALID_COMPLETION}\n```\n完成。"
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx())
    assert len(facts) == 3
    assert all(0 < f.confidence < 1 for f in facts)


# ── reject paths ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unrepairable_completion_raises_generation_error():
    gen = SchemaGovernedGenerator(complete=_const_complete("抱歉，我无法完成。"))
    with pytest.raises(GenerationError):
        await gen.generate(_proposal(), _ctx())


@pytest.mark.asyncio
async def test_missing_dimension_in_completion_raises():
    raw = '{"历史": "上古仙居。", "地理": "东海之中。"}'  # 文化 missing
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    with pytest.raises(GenerationError):
        await gen.generate(_proposal(), _ctx())


@pytest.mark.asyncio
async def test_english_leakage_completion_raises():
    raw = (
        '{"历史": "Penglai is a legendary immortal isle since ancient times in '
        'the eastern sea, home to many sages.", '
        '"地理": "东海之中。", "文化": "重道法。"}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    with pytest.raises(GenerationError):
        await gen.generate(_proposal(), _ctx())


@pytest.mark.asyncio
async def test_proposal_without_grounding_refuses_to_generate():
    # No source → unprovenanced → H0 refuses (even before the LLM is called).
    gen = SchemaGovernedGenerator(complete=_const_complete(_VALID_COMPLETION))
    with pytest.raises(GenerationError):
        await gen.generate(_proposal(grounding=[]), _ctx())


@pytest.mark.asyncio
async def test_proposal_with_no_missing_dimensions_raises():
    gen = SchemaGovernedGenerator(complete=_const_complete("{}"))
    with pytest.raises(GenerationError):
        await gen.generate(_proposal(dims=[]), _ctx())


# ── prompt is schema-governed, Chinese, grounding-citing, no model name ──────


def test_prompt_names_missing_dimensions_and_place():
    prompt = build_generation_prompt(_proposal())
    assert "蓬萊" in prompt
    for k in KEYS:
        assert k in prompt


def test_prompt_embeds_grounding_excerpts():
    prop = _proposal(grounding=_grounding(2))
    prompt = build_generation_prompt(prop)
    assert "第0段" in prompt and "第1段" in prompt


def test_prompt_is_chinese_and_requests_json():
    prompt = build_generation_prompt(_proposal(), _ZH_PROFILE)
    assert "JSON" in prompt
    # asserts Chinese instruction present (high CJK content)
    from app.generation.repair import cjk_ratio

    # strip the place name + JSON skeleton; instruction body is Chinese-dominant
    assert cjk_ratio(prompt) > 0.4


def test_prompt_contains_no_model_name():
    prompt = build_generation_prompt(_proposal())
    lowered = prompt.lower()
    for banned in ("qwen", "gpt", "bge", "llama", "gemma", "claude"):
        assert banned not in lowered


# ── determinism: same proposal + same completion → same facts ────────────────


@pytest.mark.asyncio
async def test_generation_is_deterministic_modulo_timestamp():
    gen = SchemaGovernedGenerator(complete=_const_complete(_VALID_COMPLETION))
    a = await gen.generate(_proposal(), _ctx())
    b = await gen.generate(_proposal(), _ctx())
    assert [f.content for f in a] == [f.content for f in b]
    assert [f.origin for f in a] == [f.origin for f in b]
    assert [f.dimension for f in a] == [f.dimension for f in b]
