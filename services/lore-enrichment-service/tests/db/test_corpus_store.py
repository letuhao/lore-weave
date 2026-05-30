"""C10 — SourceCorpusStore ingest idempotency + similarity search against a
REAL Postgres (source_corpus + source_corpus_chunk).

Asserts the C10 acceptance gates that require the DB (embedding is a
deterministic in-test stub here — the REAL cross-service embed/retrieve
round-trip is the live-smoke in verify-cycle-10.sh):
  1. Ingest persists chunks; re-ingest of identical text is IDEMPOTENT — same
     chunk count, zero new inserts, zero re-embeds (no duplicates, no drift).
  2. Each vector is tagged with the resolving model_ref + dimension (drift guard).
  3. Similarity search returns the seeded chunk as top-1 for its own text query.
  4. Search is project-scoped (Q3) — another project sees nothing.

Skips when no real DB is reachable (conftest._dsn); verify-cycle-10.sh supplies
the compose Postgres so this runs for real in the CI gate.
"""

from __future__ import annotations

import uuid

import pytest

from app.retrieval.store import SourceCorpusStore
from app.strategies.licensing import (
    SourceLicense,
    UnlicensedSourceError,
    check_admissible,
)

pytestmark = pytest.mark.asyncio

_TEXT = (
    "蓬萊山在海中，上有仙人，宫室皆以金玉為之。"
    "崑崙之丘，是實惟帝之下都，神陸吾司之。"
    "西王母其狀如人，豹尾虎齒而善嘯。"
)


def _make_embed_fn(vocab: list[str]):
    """Deterministic token-presence embedder (no network). Same text → same
    vector, so similarity ordering is reproducible in the DB test."""

    def _vec(text: str) -> list[float]:
        present = set(text)
        return [1.0 if ch in present else 0.0 for ch in vocab]

    async def embed_fn(texts):
        return [_vec(t) for t in texts]

    return embed_fn, _vec


async def test_ingest_is_idempotent_and_tags_model_ref(pool):
    store = SourceCorpusStore(pool)
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    vocab = sorted(set(_TEXT))
    embed_fn, _ = _make_embed_fn(vocab)

    first = await store.ingest_corpus(
        user_id=user_id, project_id=project_id, name="山海经-test",
        kind="shanhaijing", text=_TEXT, embed_fn=embed_fn, model_ref="mref-aaa",
        target_chars=40, license="public-domain",
    )
    assert first.chunks_total >= 2
    assert first.chunks_inserted == first.chunks_total
    assert first.chunks_embedded == first.chunks_total

    # re-ingest identical text → idempotent: zero new chunks, zero re-embeds.
    second = await store.ingest_corpus(
        user_id=user_id, project_id=project_id, name="山海经-test",
        kind="shanhaijing", text=_TEXT, embed_fn=embed_fn, model_ref="mref-aaa",
        target_chars=40, license="public-domain",
    )
    assert second.corpus_id == first.corpus_id  # same corpus, not forked
    assert second.chunks_total == first.chunks_total
    assert second.chunks_inserted == 0
    assert second.chunks_embedded == 0

    # every stored vector tagged with the resolving model_ref + dimension.
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT embedding_model_ref, embedding_dim FROM source_corpus_chunk "
            "WHERE corpus_id = $1",
            first.corpus_id,
        )
    assert rows
    assert all(r["embedding_model_ref"] == "mref-aaa" for r in rows)
    assert all(r["embedding_dim"] == len(vocab) for r in rows)


async def test_similarity_search_returns_seeded_chunk_top1(pool):
    store = SourceCorpusStore(pool)
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    vocab = sorted(set(_TEXT))
    embed_fn, vec = _make_embed_fn(vocab)

    result = await store.ingest_corpus(
        user_id=user_id, project_id=project_id, name="山海经-test",
        kind="shanhaijing", text=_TEXT, embed_fn=embed_fn, model_ref="mref-bbb",
        target_chars=30, license="public-domain",
    )
    assert result.chunks_total >= 2

    # query with the 蓬萊 sentence's own text → that chunk must rank top-1.
    query_vector = vec("蓬萊山在海中，上有仙人")
    hits = await store.search(project_id=project_id, query_vector=query_vector, k=3)
    assert hits
    assert "蓬萊" in hits[0].content
    # scores are descending
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


async def test_untagged_ingest_fails_closed_and_is_not_recookable(pool):
    """C17 WARN-1: an ingest with NO license arg fails CLOSED.

    The corpus is stamped 'unknown' (the inadmissible default), so the re-cook
    licensing gate REFUSES it — an operator who forgets to tag a copyrighted/news
    source can never silently re-cook it. Tagging it 'public-domain' explicitly
    makes the SAME corpus admissible (the fix is fail-closed-by-default, not a
    blanket block)."""
    store = SourceCorpusStore(pool)
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
    embed_fn, _ = _make_embed_fn(sorted(set(_TEXT)))

    # ── ingest WITHOUT a license arg → stamped 'unknown' (fail-closed) ──────────
    untagged = await store.ingest_corpus(
        user_id=user_id, project_id=project_id, name="未标注-news",
        kind="history", text=_TEXT, embed_fn=embed_fn, model_ref="m",
        target_chars=40,
    )
    raw = await store.get_corpus_license(corpus_id=untagged.corpus_id)
    assert raw == "unknown"  # NOT 'public-domain' (the old admit-by-omission default)
    # the re-cook licensing gate REFUSES it (resolved from the DB value)
    lic = SourceLicense.from_raw(
        corpus_id=str(untagged.corpus_id), name="未标注-news", license=raw
    )
    assert lic.admissible is False
    with pytest.raises(UnlicensedSourceError):
        check_admissible(lic, stage="corpus-admission")

    # ── the SAME content tagged public-domain → admissible (fix is fail-closed) ─
    tagged = await store.ingest_corpus(
        user_id=user_id, project_id=project_id, name="封神演义-pd",
        kind="fengshen", text=_TEXT, embed_fn=embed_fn, model_ref="m",
        target_chars=40, license="public-domain",
    )
    raw_pd = await store.get_corpus_license(corpus_id=tagged.corpus_id)
    assert raw_pd == "public-domain"
    pd = SourceLicense.from_raw(
        corpus_id=str(tagged.corpus_id), name="封神演义-pd", license=raw_pd
    )
    assert pd.admissible is True
    check_admissible(pd, stage="corpus-admission")  # no raise


async def test_search_is_project_scoped(pool):
    store = SourceCorpusStore(pool)
    user_id = uuid.uuid4()
    project_a, project_b = uuid.uuid4(), uuid.uuid4()
    vocab = sorted(set(_TEXT))
    embed_fn, vec = _make_embed_fn(vocab)

    await store.ingest_corpus(
        user_id=user_id, project_id=project_a, name="山海经-A",
        kind="shanhaijing", text=_TEXT, embed_fn=embed_fn, model_ref="m",
        target_chars=30, license="public-domain",
    )
    # project_b ingested nothing → search returns empty (scope isolation, Q3).
    hits_b = await store.search(
        project_id=project_b, query_vector=vec("蓬萊山在海中"), k=5
    )
    assert hits_b == []
    # project_a does see its chunks.
    hits_a = await store.search(
        project_id=project_a, query_vector=vec("蓬萊山在海中"), k=5
    )
    assert hits_a
