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
    InsufficientGroundingError,
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


_EN_PROFILE = BookProfile(language="en", worldview="A windswept coast of storm-mages")


def _ctx(model_ref="emb-or-gen-ref", profile=None) -> StrategyContext:
    kw = {"user_id": "u1", "project_id": "p1", "model_ref": model_ref}
    if profile is not None:
        kw["profile"] = profile
    return StrategyContext(**kw)


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
async def test_missing_dimension_is_ungrounded_not_fatal():
    # slice B: a dimension absent from the output is now treated as UNGROUNDED
    # (the excerpts didn't cover it) — the grounded dims still produce facts; the
    # whole gap is no longer failed. (Old behavior raised on any missing key.)
    raw = '{"历史": "上古仙居。", "地理": "东海之中。"}'  # 文化 absent → ungrounded
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx())
    assert [f.dimension for f in facts] == ["历史", "地理"]  # 文化 dropped, not fatal
    assert facts[0].provenance["ungrounded_dimensions"] == ["文化"]
    assert facts[0].provenance["grounding_strength"] == round(2 / 3, 4)


@pytest.mark.asyncio
async def test_english_leakage_dimension_is_dropped_for_a_zh_book():
    # slice B: in a ZH book, an English-leakage (low-CJK) value is UNGROUNDED —
    # dropped, never minted (H0-safe) — the Chinese dims still produce facts.
    raw = (
        '{"历史": "Penglai is a legendary immortal isle since ancient times in '
        'the eastern sea, home to many sages.", '
        '"地理": "东海之中。", "文化": "重道法。"}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx(profile=_ZH_PROFILE))
    assert [f.dimension for f in facts] == ["地理", "文化"]  # English 历史 dropped
    assert all(f.content for f in facts)


@pytest.mark.asyncio
async def test_en_book_keeps_english_content():
    # de-bias (LE-PROD-2 P2, live-found): for a NON-zh book the CJK gate must be
    # OFF — English content is faithful and MUST be kept. Otherwise every English
    # book's retrieval marks all dims ungrounded → 0 proposals (the live bug).
    raw = (
        '{"历史": "An ancient storm-mage isle, home to sea-wardens since the old pacts.", '
        '"地理": "A salt-bitten coast of black cliffs and perpetual gales.", '
        '"文化": "The fisher-folk keep the weather-pacts and revere the Tempest Court."}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx(profile=_EN_PROFILE))
    # all three English dims KEPT (none dropped by a CJK gate).
    assert [f.dimension for f in facts] == KEYS
    assert all(f.content for f in facts)


@pytest.mark.asyncio
async def test_refusal_prose_with_grounded_true_is_treated_ungrounded():
    # P4a safety net: a non-compliant model marks grounded=true but writes a refusal
    # as the content — it must NOT mint a junk "未提及" fact. Here 历史 is a refusal
    # (dropped); the genuine 地理/文化 stay.
    raw = (
        '{"历史": {"grounded": true, "content": "检索片段未提及此地历史，无可补全。"}, '
        '"地理": {"grounded": true, "content": "东海之中，云雾缭绕。"}, '
        '"文化": {"grounded": true, "content": "岛上仙家崇尚清修。"}}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx(profile=_ZH_PROFILE))
    assert [f.dimension for f in facts] == ["地理", "文化"]  # refusal 历史 dropped
    assert facts[0].provenance["ungrounded_dimensions"] == ["历史"]


@pytest.mark.asyncio
async def test_all_ungrounded_raises_insufficient_grounding():
    # slice B: the model marks EVERY dimension grounded=false (the "未提及" case) →
    # no usable grounding → InsufficientGroundingError (the runner skips with an
    # actionable reason instead of surfacing an empty proposal).
    raw = (
        '{"历史": {"grounded": false, "content": ""}, '
        '"地理": {"grounded": false, "content": ""}, '
        '"文化": {"grounded": false, "content": ""}}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    with pytest.raises(InsufficientGroundingError):
        await gen.generate(_proposal(), _ctx())


@pytest.mark.asyncio
async def test_grounded_flag_as_string_false_is_honored():
    # review-impl #3: a model that quotes the bool ("grounded": "false") must be
    # read as UNGROUNDED, not truthy-by-accident. Here 历史 is string-"false" → drop;
    # 地理/文化 string-"true" → kept.
    raw = (
        '{"历史": {"grounded": "false", "content": "蓬萊上古仙居。"}, '
        '"地理": {"grounded": "true", "content": "东海之中。"}, '
        '"文化": {"grounded": "true", "content": "重道法。"}}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx())
    assert [f.dimension for f in facts] == ["地理", "文化"]  # string-"false" 历史 dropped


@pytest.mark.asyncio
async def test_grounded_flag_partial_keeps_only_grounded_dims():
    # slice B: the grounded-flag shape — 历史 grounded, 地理/文化 not → 1 fact, and
    # the provenance records the ungrounded dims + the grounding-strength fraction.
    raw = (
        '{"历史": {"grounded": true, "content": "蓬萊自上古为仙人所居。"}, '
        '"地理": {"grounded": false, "content": ""}, '
        '"文化": {"grounded": false, "content": ""}}'
    )
    gen = SchemaGovernedGenerator(complete=_const_complete(raw))
    facts = await gen.generate(_proposal(), _ctx())
    assert [f.dimension for f in facts] == ["历史"]
    assert facts[0].provenance["ungrounded_dimensions"] == ["地理", "文化"]
    assert facts[0].provenance["grounding_strength"] == round(1 / 3, 4)


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


def test_prompt_demands_synthesis_not_verbatim_copy():
    """C (D-JOURNEY-ENRICH-VERBATIM) — the prompt must tell the model to SYNTHESIZE
    in its own words, not copy the excerpts verbatim. Without this the model copies
    the source (the safe grounded path) and our anti-plagiarism gate auto-rejects it
    — a self-defeating loop. Both language templates carry the instruction."""
    en = build_generation_prompt(_proposal())  # neutral/English template
    el = en.lower()
    assert "verbatim" in el and ("synthesize" in el or "own words" in el)
    zh = build_generation_prompt(_proposal(), _ZH_PROFILE)
    assert "逐字" in zh and "改写" in zh  # don't-copy-verbatim + paraphrase


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
