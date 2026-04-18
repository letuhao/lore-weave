"""D-K18.3-01 — unit tests for the passage ingester + chunker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.extraction.passage_ingester import (
    MIN_CHUNK_CHARS,
    OVERLAP_CHARS,
    TARGET_CHARS,
    IngestResult,
    chunk_text,
    delete_chapter_passages,
    ingest_chapter_passages,
)


USER_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOK_ID = UUID("33333333-3333-3333-3333-333333333333")
CHAPTER_ID = UUID("44444444-4444-4444-4444-444444444444")


# ── chunker ────────────────────────────────────────────────────────


def test_chunk_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_tiny_paragraph_dropped():
    """Below MIN_CHUNK_CHARS — dropped to avoid noise embeddings."""
    tiny = "hi."
    assert chunk_text(tiny) == []


def test_chunk_single_paragraph_fits_in_one_chunk():
    """Paragraph under target produces exactly one chunk."""
    text = "This is a single paragraph. " * 10
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].startswith("This is")


def test_chunk_multiple_paragraphs_packed():
    """Small paragraphs combine into a single chunk when they fit."""
    text = "Para one sentence. " * 5 + "\n\n" + "Para two sentence. " * 5
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "Para one" in chunks[0]
    assert "Para two" in chunks[0]


def test_chunk_oversized_text_splits_with_overlap():
    """Text larger than target_chars produces multiple chunks; each
    chunk inherits a tail-overlap prefix from the previous chunk."""
    # 4000-char paragraph of simple sentences.
    sentence = "Arthur rode toward the castle at dawn. "
    text = sentence * 100  # ~4000 chars
    chunks = chunk_text(text, target_chars=500, overlap_chars=100)
    assert len(chunks) >= 2
    # Each chunk is ≲ target + overlap (single-sentence slack).
    for c in chunks:
        assert len(c) <= 500 + len(sentence) + 100


def test_chunk_drops_below_min_after_split():
    """Tiny tail of a split paragraph still respects MIN_CHUNK_CHARS."""
    text = "A" * 50  # below min_chunk_chars
    assert chunk_text(text) == []


def test_chunk_tokens_boundary_constants_sane():
    """Sanity: target > overlap > min_chunk > 0."""
    assert TARGET_CHARS > OVERLAP_CHARS > MIN_CHUNK_CHARS > 0


def test_tail_at_word_boundary_snaps_to_whitespace():
    """Directly test the overlap helper: never returns a mid-word
    prefix when whitespace is available in the slice."""
    from app.extraction.passage_ingester import _tail_at_word_boundary

    # Basic: enough room, snaps to after the last space in the slice.
    assert _tail_at_word_boundary("hello world", 7) == "world"
    # Zero/negative max → empty string.
    assert _tail_at_word_boundary("hello world", 0) == ""
    assert _tail_at_word_boundary("hello world", -5) == ""
    # max >= text length → return whole string.
    assert _tail_at_word_boundary("hello", 100) == "hello"
    # No whitespace in the slice → fall back to raw tail (CJK-friendly).
    assert _tail_at_word_boundary("HelloWorld", 5) == "World"
    # Multiple spaces — snap to FIRST whitespace inside the 8-char
    # tail " efg hij" → returns "efg hij".
    assert _tail_at_word_boundary("a bcd efg hij", 8) == "efg hij"


def test_chunk_overlap_has_no_midword_start():
    """Integration: chunks 2..N should not begin with a mid-word
    slice when the chunker has enough overlap headroom.

    We verify via a property: the first character of each non-first
    chunk (ignoring leading whitespace/punct) is the start of a word
    that exists in the original text.
    """
    import re as _re
    sentence = "Arthur swung his mighty sword at the approaching wyvern. "
    text = sentence * 40
    chunks = chunk_text(text, target_chars=500, overlap_chars=80)
    assert len(chunks) >= 2
    words_in_text = set(_re.findall(r"[A-Za-z]+", text))
    for c in chunks[1:]:
        first_word_match = _re.match(r"\s*([A-Za-z]+)", c)
        if first_word_match is None:
            continue  # chunk starts with punct/newline — still a boundary
        first_word = first_word_match.group(1)
        assert first_word in words_in_text, (
            f"chunk starts with mid-word fragment {first_word!r}"
        )


# ── ingester ────────────────────────────────────────────────────────


def _mk_book_client(text: str | None = "chapter text " * 100) -> MagicMock:
    client = MagicMock()
    client.get_chapter_text = AsyncMock(return_value=text)
    return client


def _mk_embedding_client(n_vectors: int = 1, dim: int = 1024) -> MagicMock:
    client = MagicMock()
    client.embed = AsyncMock(
        return_value=EmbeddingResult(
            embeddings=[[0.1] * dim for _ in range(n_vectors)],
            dimension=dim,
            model="bge-m3",
        )
    )
    return client


@pytest.mark.asyncio
async def test_ingest_skips_unsupported_dim(monkeypatch):
    """embedding_dim not in SUPPORTED_PASSAGE_DIMS → skip entirely."""
    book = _mk_book_client()
    emb = _mk_embedding_client()
    upsert = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", delete,
    )

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3",
        embedding_dim=768,  # not in SUPPORTED_PASSAGE_DIMS
    )
    assert result.chunks_created == 0
    book.get_chapter_text.assert_not_called()
    upsert.assert_not_called()
    delete.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_skips_when_book_returns_no_text(monkeypatch):
    """Book-service returns None → delete stale + return 0 chunks."""
    book = _mk_book_client(text=None)
    emb = _mk_embedding_client()
    delete = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", delete,
    )

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert result.chunks_created == 0
    # Still called delete_passages_for_source so stale chunks are cleaned.
    delete.assert_awaited_once()
    emb.embed.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_skips_when_embed_fails(monkeypatch):
    """Embedding error → embed_failed=True, no upserts."""
    book = _mk_book_client()
    emb = MagicMock()
    emb.embed = AsyncMock(
        side_effect=EmbeddingError("upstream 503", retryable=True),
    )
    upsert = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", delete,
    )

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert result.embed_failed is True
    assert result.chunks_created == 0
    # Delete not called — the current flow bails before delete+upsert on embed failure.
    delete.assert_not_called()
    upsert.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_happy_path_upserts_per_chunk(monkeypatch):
    """Full ingestion: chunk → embed → delete stale → upsert each."""
    # Make text large enough to produce 2+ chunks.
    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300)
    # We'll replace embed with a callable that sizes to the chunk count.
    captured_texts: list[list[str]] = []

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        captured_texts.append(texts)
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts],
            dimension=1024,
            model="bge-m3",
        )

    emb = MagicMock()
    emb.embed = fake_embed

    upsert = AsyncMock()
    delete = AsyncMock(return_value=0)
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", delete,
    )

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=7,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert result.chunks_created > 0
    assert result.chunks_skipped == 0
    # Delete-then-upsert order.
    delete.assert_awaited_once()
    assert upsert.await_count == result.chunks_created
    # Each chunk got its chapter_index forwarded.
    for call in upsert.await_args_list:
        assert call.kwargs["chapter_index"] == 7
        assert call.kwargs["embedding_dim"] == 1024
        assert call.kwargs["source_type"] == "chapter"
        assert call.kwargs["is_hub"] is False


@pytest.mark.asyncio
async def test_ingest_dim_mismatch_chunk_is_skipped(monkeypatch):
    """If one vector in the batch has the wrong length, skip that chunk only."""
    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300)

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        # Intentionally return a short vector for the first chunk.
        vecs = [[0.1] * 1024 for _ in texts]
        vecs[0] = [0.1] * 99  # wrong dim — should be skipped
        return EmbeddingResult(embeddings=vecs, dimension=1024, model="bge-m3")

    emb = MagicMock()
    emb.embed = fake_embed
    upsert = AsyncMock()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source",
        AsyncMock(return_value=0),
    )

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert result.chunks_skipped == 1
    assert result.chunks_created >= 1  # other chunks succeed


@pytest.mark.asyncio
async def test_delete_chapter_passages_delegates(monkeypatch):
    underlying = AsyncMock(return_value=5)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", underlying,
    )
    n = await delete_chapter_passages(
        MagicMock(), user_id=USER_ID, chapter_id=CHAPTER_ID,
    )
    assert n == 5
    underlying.assert_awaited_once()
    kwargs = underlying.await_args.kwargs
    assert kwargs["source_type"] == "chapter"
    assert kwargs["source_id"] == str(CHAPTER_ID)
