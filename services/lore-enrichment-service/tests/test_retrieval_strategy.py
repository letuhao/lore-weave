"""C10 — RetrievalStrategy (technique (b): corpus-grounded retrieval) tests.

Pins the second concrete enrichment technique: a typed :class:`Gap` → a query
embedded via knowledge-service ``/internal/embed`` (model_ref, NEVER a hardcoded
name) → top-K corpus passages retrieved by cosine similarity → an H0-stamped
:class:`GroundedProposal` whose ``cultural_grounding_ref`` cites real corpus +
chunk ids + scores.

Adversary focus (brief 10):
  1. Mock-only false-green — these UNIT tests mock the embed (the real cross-
     service embed/retrieve round-trip is the live-smoke in verify-cycle-10.sh).
     The mock here is deterministic so similarity ordering is asserted exactly.
  2. No hardcoded model name — a grep-style guard asserts no literal embed-model
     id in the strategy / store / embedding source; the model is a ``model_ref``.
  3. Idempotency / chunk drift — the chunker is deterministic; the DB idempotency
     (re-ingest → same chunk count) is exercised in the DB test + live-smoke.
  4. model_ref drift — the resolving model_ref is recorded in provenance.
  5. H0 — assert the NEGATIVE: a grounded proposal is NEVER source_type=
     'glossary' / confidence>=1.0; born origin='enrichment', technique=
     'retrieval', review_status='proposed', pending_validation, 0<confidence<1.0.
  6. CJK correctness — chunker never splits mid-character; UTF-8 round-trips.
  7. Owned-corpora only — no web-search / heavy-dep import sneaks in.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.gaps.model import Dimension, EntityKind, Gap, dimensions_for
from app.retrieval.chunker import chunk_text, sha256_text
from app.retrieval.store import (
    ScoredChunk,
    StoredChunk,
    cosine_similarity,
    top_k,
)
from app.retrieval.strategy import (
    RETRIEVAL_CONFIDENCE,
    GroundedProposal,
    GroundingRef,
    RetrievalStrategy,
)
from app.strategies.base import StrategyContext, Technique, Tier
from app.strategies.feature_flags import load_feature_flags
from app.strategies.registry import InactiveStrategyError, StrategyRegistry

_FIXTURE = Path(__file__).parent / "fixtures" / "shanhaijing_chunk.txt"
_CORPUS_TEXT = _FIXTURE.read_text(encoding="utf-8")


# ── chunker: deterministic, idempotent, CJK-safe ─────────────────────────────
def test_chunker_is_deterministic() -> None:
    a = chunk_text(_CORPUS_TEXT)
    b = chunk_text(_CORPUS_TEXT)
    assert [c.content for c in a] == [c.content for c in b]
    assert [c.sha256 for c in a] == [c.sha256 for c in b]
    assert [c.index for c in a] == list(range(len(a)))  # 0-based stable ordinal


def test_chunker_indexes_are_stable_ordinals() -> None:
    chunks = chunk_text(_CORPUS_TEXT, target_chars=40, overlap_sentences=0)
    assert len(chunks) >= 2  # the fixture has several sentences
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunker_is_cjk_byte_safe() -> None:
    # every chunk re-encodes to valid UTF-8 and contains no replacement char;
    # no 漢字 was cut mid-codepoint (we operate on str, never bytes).
    for c in chunk_text(_CORPUS_TEXT, target_chars=30):
        assert c.content == c.content.encode("utf-8").decode("utf-8")
        assert "�" not in c.content  # no mojibake replacement char
        assert c.sha256 == sha256_text(c.content)


def test_chunker_keeps_demo_place_names_intact() -> None:
    # the locked demo grounding names survive chunking unbroken.
    joined = "".join(c.content for c in chunk_text(_CORPUS_TEXT, target_chars=20))
    for name in ("崑崙", "蓬萊", "西王母"):
        assert name in joined


def test_chunker_empty_input_yields_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunker_long_sentence_not_split_midword() -> None:
    long_sentence = "崑" * 500 + "。"
    chunks = chunk_text(long_sentence, target_chars=100)
    # emitted whole (never split mid-sentence) — one chunk, intact
    assert len(chunks) == 1
    assert chunks[0].content == "崑" * 500 + "。"


# ── cosine + top_k math (pure, no DB) ─────────────────────────────────────────
def test_cosine_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_handles_degenerate_inputs() -> None:
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0  # zero vector
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0  # length mismatch (drift)


def _stored(idx: int, vec: list[float]) -> StoredChunk:
    return StoredChunk(
        chunk_id=uuid4(),
        corpus_id=uuid4(),
        chunk_index=idx,
        content=f"chunk-{idx}",
        embedding=vec,
        embedding_model_ref="ref",
    )


def test_top_k_orders_by_descending_score_and_returns_seeded_chunk() -> None:
    query = [1.0, 0.0, 0.0]
    near = _stored(0, [0.9, 0.1, 0.0])   # most similar
    mid = _stored(1, [0.5, 0.5, 0.0])
    far = _stored(2, [0.0, 0.0, 1.0])    # orthogonal
    results = top_k(query, [far, mid, near], k=3)
    assert [r.chunk_index for r in results] == [0, 1, 2]  # near, mid, far
    # the seeded chunk (its own direction) is top-1
    assert results[0].chunk_index == 0
    # descending score
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_top_k_skips_unembedded_and_respects_k() -> None:
    query = [1.0, 0.0]
    a = _stored(0, [1.0, 0.0])
    no_vec = StoredChunk(
        chunk_id=uuid4(), corpus_id=uuid4(), chunk_index=1,
        content="x", embedding=None, embedding_model_ref=None,
    )
    results = top_k(query, [a, no_vec], k=5)
    assert len(results) == 1 and results[0].chunk_index == 0


def test_top_k_zero_or_negative_k_is_empty() -> None:
    assert top_k([1.0], [_stored(0, [1.0])], k=0) == []
    assert top_k([1.0], [_stored(0, [1.0])], k=-1) == []


# ── a fake store + deterministic embed for strategy-level tests ──────────────
class _FakeStore:
    """In-memory stand-in for SourceCorpusStore.search — no DB. Embeds the
    fixture chunks with a deterministic token-overlap vector so similarity is
    reproducible and the seeded chunk is retrievable by its own text."""

    def __init__(self, chunks: list[str]) -> None:
        self._vocab = sorted({ch for text in chunks for ch in text})
        self._chunks: list[StoredChunk] = []
        self.project_id = uuid4()
        cid = uuid4()
        for i, text in enumerate(chunks):
            self._chunks.append(
                StoredChunk(
                    chunk_id=uuid4(), corpus_id=cid, chunk_index=i,
                    content=text, embedding=self.embed_text(text),
                    embedding_model_ref="model-ref-xyz",
                )
            )

    def embed_text(self, text: str) -> list[float]:
        present = set(text)
        return [1.0 if ch in present else 0.0 for ch in self._vocab]

    async def search(self, *, project_id, query_vector, k, corpus_id=None):
        return top_k(query_vector, self._chunks, k=k)


def _make_strategy(corpus_chunks: list[str]) -> tuple[RetrievalStrategy, _FakeStore]:
    store = _FakeStore(corpus_chunks)
    captured: dict[str, object] = {}

    async def embed_query(query: str, context: StrategyContext) -> list[float]:
        # records the model_ref to prove it flows from context (never hardcoded)
        captured["model_ref"] = context.model_ref
        return store.embed_text(query)

    strat = RetrievalStrategy(store=store, embed_query=embed_query, top_k=2)  # type: ignore[arg-type]
    strat._captured = captured  # type: ignore[attr-defined]
    return strat, store


def _gap(name: str) -> Gap:
    return Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name=name,
        target_ref=f"loc:{name}",
        mention_count=10,
        present_dimensions=(),
        missing_dimensions=tuple(d for d in Dimension),
    )


def _run(strat, batch, ctx) -> list[GroundedProposal]:
    return asyncio.run(strat.run(batch, ctx))


# ── identity / registry ───────────────────────────────────────────────────────
def test_strategy_identity_is_retrieval_p1() -> None:
    strat, _ = _make_strategy(["蓬萊山在海中。"])
    assert strat.technique is Technique.RETRIEVAL
    assert strat.key == "retrieval"
    assert strat.tier is Tier.P1


def test_resolves_through_registry_by_retrieval_key() -> None:
    strat, _ = _make_strategy(["蓬萊山在海中。"])
    reg = StrategyRegistry()
    reg.register(strat)
    assert reg.select("retrieval") is strat
    assert reg.is_active("retrieval")  # P1 active by default


def test_disabled_flag_makes_retrieval_unselectable() -> None:
    strat, _ = _make_strategy(["蓬萊山在海中。"])
    flags = load_feature_flags(env={"ENRICH_STRATEGY_RETRIEVAL_ENABLED": "0"})
    reg = StrategyRegistry(flags=flags)
    reg.register(strat)
    with pytest.raises(InactiveStrategyError):
        reg.select("retrieval")
    assert reg.list_active() == []


# ── retrieval populates cultural_grounding_ref with real ids + scores ────────
def test_run_populates_grounding_ref_with_corpus_and_chunk_ids() -> None:
    chunks = ["蓬萊山在海中，上有仙人。", "崑崙之丘，帝之下都。", "西王母豹尾虎齒。"]
    strat, store = _make_strategy(chunks)
    ctx = StrategyContext(user_id="u1", project_id=str(store.project_id), model_ref="mref-1")
    [proposal] = _run(strat, [_gap("蓬萊")], ctx)

    assert proposal.has_grounding()
    # top grounding must be the 蓬萊 chunk (its own text overlaps the query most)
    assert "蓬萊" in proposal.grounding[0].excerpt
    for ref in proposal.grounding:
        assert ref.corpus_id  # real corpus id
        assert ref.chunk_id   # real chunk id
        assert isinstance(ref.chunk_index, int)
        assert 0.0 <= ref.score <= 1.0
    # ordering is by descending score
    scores = [r.score for r in proposal.grounding]
    assert scores == sorted(scores, reverse=True)
    # top_k respected (strategy built with top_k=2)
    assert len(proposal.grounding) <= 2


def test_model_ref_flows_from_context_into_provenance() -> None:
    strat, store = _make_strategy(["蓬萊山在海中。"])
    ctx = StrategyContext(user_id="u1", project_id=str(store.project_id), model_ref="mref-77")
    [proposal] = _run(strat, [_gap("蓬萊")], ctx)
    # the embed callable saw the context's model_ref (not a hardcoded name)
    assert strat._captured["model_ref"] == "mref-77"  # type: ignore[attr-defined]
    # and it is recorded in provenance for drift auditing
    assert proposal.provenance_json["retrieval"]["model_ref"] == "mref-77"


def test_dimension_slots_are_empty_chinese_keys() -> None:
    strat, store = _make_strategy(["蓬萊山在海中。"])
    ctx = StrategyContext(user_id="u1", project_id=str(store.project_id), model_ref="m")
    gap = _gap("蓬萊")
    [proposal] = _run(strat, [gap], ctx)
    expected = [
        spec.label for spec in dimensions_for(gap.entity_kind)
        if spec.dimension in set(gap.missing_dimensions)
    ]
    assert list(proposal.dimensions.keys()) == expected
    assert {"历史", "地理", "文化"} <= set(proposal.dimensions.keys())
    assert all(v == "" for v in proposal.dimensions.values())  # generation is C11


def test_empty_corpus_yields_proposal_with_no_grounding() -> None:
    strat, store = _make_strategy([])  # empty corpus
    ctx = StrategyContext(user_id="u1", project_id=str(store.project_id), model_ref="m")
    [proposal] = _run(strat, [_gap("蓬萊")], ctx)
    assert proposal.grounding == []
    assert not proposal.has_grounding()
    # still a valid H0 proposal (never canon)
    assert proposal.origin == "enrichment"
    assert 0.0 < proposal.confidence < 1.0


def test_run_preserves_batch_order_one_per_gap() -> None:
    strat, store = _make_strategy(["蓬萊山在海中。", "崑崙之丘。"])
    ctx = StrategyContext(user_id="u1", project_id=str(store.project_id), model_ref="m")
    batch = [_gap("蓬萊"), _gap("崑崙"), _gap("陳塘關")]
    proposals = _run(strat, batch, ctx)
    assert [p.canonical_name for p in proposals] == [g.canonical_name for g in batch]


# ── H0: assert the NEGATIVE (never canon) ─────────────────────────────────────
def test_every_proposal_carries_h0_markers() -> None:
    strat, store = _make_strategy(["蓬萊山在海中。"])
    ctx = StrategyContext(user_id="u1", project_id=str(store.project_id), model_ref="m")
    proposals = _run(strat, [_gap("蓬萊"), _gap("崑崙")], ctx)
    assert proposals
    for p in proposals:
        assert p.origin == "enrichment" and p.origin != "glossary"
        assert p.technique == "retrieval"
        assert p.review_status == "proposed"
        assert p.pending_validation is True
        assert 0.0 < p.confidence < 1.0
        assert p.confidence == RETRIEVAL_CONFIDENCE
        dumped = json.dumps(p.model_dump(), ensure_ascii=False)
        assert "glossary" not in dumped


def test_confidence_cannot_be_set_to_canon() -> None:
    with pytest.raises(Exception):
        GroundedProposal(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="X", dimensions={"历史": ""}, confidence=1.0,
        )
    with pytest.raises(Exception):
        GroundedProposal(
            user_id="u", project_id="p", entity_kind="location",
            canonical_name="X", dimensions={"历史": ""}, confidence=0.0,
        )


def test_grounding_ref_from_scored_rounds_score() -> None:
    sc = ScoredChunk(
        chunk_id=uuid4(), corpus_id=uuid4(), chunk_index=3,
        content="蓬萊山在海中。", score=0.123456789,
    )
    ref = GroundingRef.from_scored(sc)
    assert ref.score == 0.123457  # rounded to 6 dp
    assert ref.excerpt == "蓬萊山在海中。"
    assert ref.chunk_index == 3


# ── cost: one embed per gap query ─────────────────────────────────────────────
def test_estimate_cost_counts_gap_queries() -> None:
    strat, _ = _make_strategy(["蓬萊山在海中。"])
    batch = [_gap("蓬萊"), _gap("崑崙")]
    est = strat.estimate_cost(batch)
    assert est.technique is Technique.RETRIEVAL
    assert est.gap_count == 2
    assert est.units == 2.0
    assert est.cost == 2.0  # one embed unit per query


# ── scope/boundary: no hardcoded model name, no web-search / heavy dep ────────
def test_retrieval_modules_have_no_hardcoded_model_names() -> None:
    import app.retrieval.chunker as m_chunk
    import app.retrieval.embedding as m_embed
    import app.retrieval.store as m_store
    import app.retrieval.strategy as m_strat

    for mod in (m_chunk, m_store, m_strat, m_embed):
        src = inspect.getsource(mod)
        code = "\n".join(
            ln for ln in src.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ).lower()
        # split docstrings can mention model names in prose; strip triple-quoted
        # blocks by checking only obvious assignment/call patterns for ids.
        for banned in ("bge-m3", "nomic-embed", "text-embedding-3", "text-embedding-bge"):
            assert banned not in code, f"hardcoded embed-model {banned!r} in {mod.__name__}"


def test_retrieval_modules_import_no_web_search_or_heavy_dep() -> None:
    import app.retrieval.chunker as m_chunk
    import app.retrieval.store as m_store
    import app.retrieval.strategy as m_strat

    for mod in (m_chunk, m_store, m_strat):
        code = inspect.getsource(mod).lower()
        for banned in (
            "import langchain", "from langchain",
            "import llama_index", "from llama_index",
            "import ddgs", "duckduckgo", "tavily", "serpapi", "searx",
            "import requests",  # owned-corpora only; no synchronous web client
        ):
            assert banned not in code, f"scope creep: {banned!r} in {mod.__name__}"


def test_strategy_does_not_import_http_or_llm_client_directly() -> None:
    # the strategy + store take embedding as an injected callable; only the
    # embedding seam binds the real client. Guard the boundary.
    import app.retrieval.store as m_store
    import app.retrieval.strategy as m_strat

    for mod in (m_strat, m_store):
        code = inspect.getsource(mod)
        for banned in ("import httpx", "import openai", "import litellm", "import neo4j"):
            assert banned not in code, f"{mod.__name__} must not import {banned!r}"
