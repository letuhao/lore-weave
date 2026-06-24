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
    BackfillResult,
    IngestResult,
    backfill_published_passages,
    chunk_text,
    delete_chapter_passages,
    ingest_chapter_passages,
)


USER_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOK_ID = UUID("33333333-3333-3333-3333-333333333333")
CHAPTER_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture(autouse=True)
def _stub_source_lang_helpers(monkeypatch):
    """KG-ML M1 — stub the new Neo4j helpers (`get_source_ingest_state`,
    `set_source_lang_for_source`) so existing ingest tests that pass a MagicMock
    session don't hit the real run_read/run_write. Default = skip-gate cache miss
    (None) so ingestion proceeds as before. Tests that exercise the skip-gate
    override `get_source_ingest_state` explicitly (later setattr wins)."""
    monkeypatch.setattr(
        "app.extraction.passage_ingester.get_source_ingest_state",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.extraction.passage_ingester.set_source_lang_for_source",
        AsyncMock(return_value=0),
    )


# ── chunker ────────────────────────────────────────────────────────


def test_chunk_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_tiny_paragraph_dropped():
    """Below MIN_CHUNK_CHARS — dropped to avoid noise embeddings."""
    tiny = "hi."
    assert chunk_text(tiny) == []


def test_chunk_single_paragraph_fits_in_one_chunk():
    """Paragraph under target produces exactly one chunk. (chunk, block_pos)."""
    text = "This is a single paragraph. " * 10
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0][0].startswith("This is")
    assert chunks[0][1] == 0  # first (and only) block


def test_chunk_multiple_paragraphs_packed():
    """Small paragraphs combine into a single chunk when they fit."""
    text = "Para one sentence. " * 5 + "\n\n" + "Para two sentence. " * 5
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert "Para one" in chunks[0][0]
    assert "Para two" in chunks[0][0]
    assert chunks[0][1] == 0  # starts at the first paragraph/block


def test_chunk_tracks_block_pos_across_paragraphs():
    """P3-C: a chunk's block_pos is the index (among non-empty paragraphs)
    where its NEW content starts — used to map to the real block_index."""
    # 3 large paragraphs, each its own chunk → block_pos 0,1,2.
    big = "x" * (TARGET_CHARS - 20) + ". "
    text = (big + "\n\n") * 3
    chunks = chunk_text(text)
    positions = [p for _, p in chunks]
    assert positions == sorted(positions)  # monotonic, in reading order
    assert positions[0] == 0
    assert max(positions) >= 2  # reached the third block


def test_chunk_oversized_text_splits_with_overlap():
    """Text larger than target_chars produces multiple chunks; each
    chunk inherits a tail-overlap prefix from the previous chunk."""
    # 4000-char paragraph of simple sentences.
    sentence = "Arthur rode toward the castle at dawn. "
    text = sentence * 100  # ~4000 chars
    chunks = chunk_text(text, target_chars=500, overlap_chars=100)
    assert len(chunks) >= 2
    # Each chunk is ≲ target + overlap (single-sentence slack).
    for c, _ in chunks:
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
    for c, _ in chunks[1:]:
        first_word_match = _re.match(r"\s*([A-Za-z]+)", c)
        if first_word_match is None:
            continue  # chunk starts with punct/newline — still a boundary
        first_word = first_word_match.group(1)
        assert first_word in words_in_text, (
            f"chunk starts with mid-word fragment {first_word!r}"
        )


# ── ingester ────────────────────────────────────────────────────────


def _mk_book_client(
    text: str | None = "chapter text " * 100,
    revision_text: str | None = "chapter text " * 100,
    block_indices: list[int] | None = None,
) -> MagicMock:
    client = MagicMock()
    client.get_chapter_text = AsyncMock(return_value=text)
    # P3-C draft path: ingester calls get_chapter_text_and_blocks.
    client.get_chapter_text_and_blocks = AsyncMock(
        return_value=(text, block_indices or []),
    )
    client.get_chapter_revision_text = AsyncMock(return_value=revision_text)
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
        # D-RAWSEARCH-CANON-WIRING: default ingest stamps canon=True.
        assert call.kwargs["canon"] is True


@pytest.mark.asyncio
async def test_ingest_threads_canon_false_for_draft_indexing(monkeypatch):
    """D-RAWSEARCH-CANON-WIRING: the on-demand draft path passes canon=False
    through to every upsert_passage so surface=all can distinguish drafts."""
    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300)

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )

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
        canon=False,
    )
    assert result.chunks_created > 0
    assert upsert.await_count == result.chunks_created
    for call in upsert.await_args_list:
        assert call.kwargs["canon"] is False


@pytest.mark.asyncio
async def test_ingest_maps_block_index_from_block_indices(monkeypatch):
    """P3-C: the draft path maps a chunk's block_pos → block_indices[pos] and
    forwards it to upsert_passage (proves precise-scroll wiring end-to-end)."""
    # One paragraph (no blank line) → every chunk has block_pos 0 → maps to
    # block_indices[0]=5 (non-zero proves it uses the array, not the position).
    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300,
                           block_indices=[5])
    emb = _mk_embedding_client(n_vectors=1, dim=1024)

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
    emb.embed = fake_embed
    upsert = AsyncMock()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source",
        AsyncMock(return_value=0),
    )

    await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert upsert.await_count >= 1
    for call in upsert.await_args_list:
        assert call.kwargs["block_index"] == 5


@pytest.mark.asyncio
async def test_ingest_disables_block_map_on_misalignment(monkeypatch):
    """P3-C/MED-2: if paragraph count ≠ len(block_indices) (empty/media block,
    internal newlines) the mapping is unreliable → emit block_index=None
    (graceful) rather than a WRONG block."""
    # 2 non-empty paragraphs but only 1 block_index → misaligned → disabled.
    text = ("word " * 60) + "\n\n" + ("word " * 60)
    book = _mk_book_client(text=text, block_indices=[5])
    emb = _mk_embedding_client()

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
    emb.embed = fake_embed
    upsert = AsyncMock()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source",
        AsyncMock(return_value=0),
    )

    await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert upsert.await_count >= 1
    for call in upsert.await_args_list:
        assert call.kwargs["block_index"] is None  # mapping disabled, not wrong


# ── KG-ML M1: source_lang, cost metering, skip-gate ─────────────────


def test_resolve_source_lang_prefers_declared():
    """Declared chapter original_language wins; no text detection needed."""
    from app.extraction.passage_ingester import resolve_source_lang

    lang, mixed = resolve_source_lang("ZH", "any text")
    assert lang == "zh"
    assert mixed is False


def test_resolve_source_lang_falls_back_to_detection(monkeypatch):
    """Absent/unknown declared lang → detect from text."""
    from app.extraction import passage_ingester as pi

    monkeypatch.setattr(pi, "detect_primary_language", lambda _t: "vi")
    assert pi.resolve_source_lang(None, "xin chào") == ("vi", False)
    assert pi.resolve_source_lang("unknown", "xin chào") == ("vi", False)
    assert pi.resolve_source_lang("", "xin chào") == ("vi", False)


def test_resolve_source_lang_mixed_sets_flag(monkeypatch):
    """Ambiguous detection → source_lang 'mixed' + mixed=True."""
    from app.extraction import passage_ingester as pi

    monkeypatch.setattr(pi, "detect_primary_language", lambda _t: "mixed")
    assert pi.resolve_source_lang(None, "hello 你好") == ("mixed", True)


@pytest.mark.asyncio
async def test_ingest_stamps_declared_source_lang(monkeypatch):
    """Declared source_lang is forwarded to every upsert_passage + result."""
    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300)

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
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
        source_lang="zh",
    )
    assert result.source_lang == "zh"
    assert upsert.await_count == result.chunks_created
    for call in upsert.await_args_list:
        assert call.kwargs["source_lang"] == "zh"
        assert call.kwargs["mixed"] is False
        assert call.kwargs["content_hash"]  # a hash was stamped


@pytest.mark.asyncio
async def test_ingest_meters_embedding_cost_when_pool_given(monkeypatch):
    """C10: pool + prompt_tokens>0 → record_spending(cost) called once."""
    import app.extraction.passage_ingester as pi
    from decimal import Decimal

    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300)

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024,
            model="bge-m3", prompt_tokens=500,
        )
    emb = MagicMock()
    emb.embed = fake_embed
    monkeypatch.setattr(pi, "upsert_passage", AsyncMock())
    monkeypatch.setattr(pi, "delete_passages_for_source", AsyncMock(return_value=0))
    monkeypatch.setattr(pi, "cost_per_token", lambda _m: Decimal("0.0001"))
    rec = AsyncMock()
    monkeypatch.setattr(pi, "record_spending", rec)

    pool = MagicMock()
    await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
        pool=pool,
    )
    rec.assert_awaited_once()
    args = rec.await_args.args
    assert args[0] is pool and args[1] == USER_ID and args[2] == PROJECT_ID
    assert args[3] == Decimal("0.0001") * Decimal(500)


@pytest.mark.asyncio
async def test_ingest_no_metering_without_pool(monkeypatch):
    """No pool → record_spending never called (tests/benchmark paths)."""
    import app.extraction.passage_ingester as pi

    book = _mk_book_client(text="Arthur rode toward Camelot. " * 300)

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024,
            model="bge-m3", prompt_tokens=500,
        )
    emb = MagicMock()
    emb.embed = fake_embed
    monkeypatch.setattr(pi, "upsert_passage", AsyncMock())
    monkeypatch.setattr(pi, "delete_passages_for_source", AsyncMock(return_value=0))
    rec = AsyncMock()
    monkeypatch.setattr(pi, "record_spending", rec)

    await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    rec.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_skip_gate_unchanged_text(monkeypatch):
    """C10: existing content_hash == fresh text hash → skip embed/delete/upsert,
    re-tag source_lang, return skipped_unchanged=True (bills zero)."""
    import hashlib
    import app.extraction.passage_ingester as pi

    text = "Arthur rode toward Camelot. " * 300
    book = _mk_book_client(text=text)
    matching_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # State matches on hash + canon(True default) + chapter_index(1) + model → skip.
    monkeypatch.setattr(
        pi, "get_source_ingest_state",
        AsyncMock(return_value={
            "content_hash": matching_hash, "canon": True, "chapter_index": 1,
            "embedding_model": "bge-m3",
        }),
    )
    tag = AsyncMock(return_value=3)
    monkeypatch.setattr(pi, "set_source_lang_for_source", tag)
    upsert = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(pi, "upsert_passage", upsert)
    monkeypatch.setattr(pi, "delete_passages_for_source", delete)
    emb = MagicMock()
    emb.embed = AsyncMock()

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
        source_lang="zh",
    )
    assert result.skipped_unchanged is True
    emb.embed.assert_not_called()
    delete.assert_not_called()
    upsert.assert_not_called()
    tag.assert_awaited_once()  # re-tagged source_lang without re-embed


@pytest.mark.asyncio
async def test_skip_gate_does_not_skip_on_canon_flip(monkeypatch):
    """C10 correctness: identical text but canon flips (draft→publish) → must NOT
    skip; full re-ingest so published content reaches canon search."""
    import hashlib
    import app.extraction.passage_ingester as pi

    text = "Arthur rode toward Camelot. " * 300
    book = _mk_book_client(text=text)
    matching_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Existing passages are draft (canon=False); incoming publish is canon=True.
    monkeypatch.setattr(
        pi, "get_source_ingest_state",
        AsyncMock(return_value={
            "content_hash": matching_hash, "canon": False, "chapter_index": 1,
            "embedding_model": "bge-m3",
        }),
    )
    monkeypatch.setattr(pi, "set_source_lang_for_source", AsyncMock(return_value=0))
    upsert = AsyncMock()
    monkeypatch.setattr(pi, "upsert_passage", upsert)
    monkeypatch.setattr(pi, "delete_passages_for_source", AsyncMock(return_value=0))

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
    emb = MagicMock()
    emb.embed = fake_embed

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
        canon=True,  # publish path
    )
    assert result.skipped_unchanged is False
    assert result.chunks_created > 0
    for call in upsert.await_args_list:
        assert call.kwargs["canon"] is True  # re-ingested as canon


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state_override",
    [
        {"chapter_index": 2},          # reorder: same text, different sort_order
        {"embedding_model": "old-model"},  # model change: same text, new model/dim
    ],
)
async def test_skip_gate_does_not_skip_on_metadata_drift(monkeypatch, state_override):
    """C10 correctness: identical text but a metadata change (chapter reorder OR
    embedding-model change — the model-set path does NOT delete passages) MUST
    re-ingest, not skip. Guards the HIGH stale-dimension regression + reorder."""
    import hashlib
    import app.extraction.passage_ingester as pi

    text = "Arthur rode toward Camelot. " * 300
    book = _mk_book_client(text=text)
    matching_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    state = {
        "content_hash": matching_hash, "canon": True, "chapter_index": 1,
        "embedding_model": "bge-m3",
    }
    state.update(state_override)
    monkeypatch.setattr(pi, "get_source_ingest_state", AsyncMock(return_value=state))
    monkeypatch.setattr(pi, "set_source_lang_for_source", AsyncMock(return_value=0))
    upsert = AsyncMock()
    monkeypatch.setattr(pi, "upsert_passage", upsert)
    monkeypatch.setattr(pi, "delete_passages_for_source", AsyncMock(return_value=0))

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
    emb = MagicMock()
    emb.embed = fake_embed

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024, canon=True,
    )
    assert result.skipped_unchanged is False
    assert result.chunks_created > 0


def test_resolve_source_lang_strips_region_subtag(monkeypatch):
    """#5: BCP-47 region / locale variants normalize to the ISO-639-1 primary
    subtag so M4's reader_pref==source_lang comparison doesn't miss."""
    from app.extraction.passage_ingester import resolve_source_lang

    assert resolve_source_lang("zh-CN", "x") == ("zh", False)
    assert resolve_source_lang("en_US", "x") == ("en", False)
    assert resolve_source_lang("ZH-Hant", "x") == ("zh", False)


# ── KG-ML M2: language-scoped identity + vi dual-index ──────────────


def test_canonical_id_distinct_per_language():
    """M2 (DD1): vi and zh chunks of the SAME chapter (same source_id) get
    DISTINCT ids so dual-indexing never overwrites the source passages; an
    empty/'unknown' lang keeps the pre-M2 id byte-identical (back-compat)."""
    from app.db.neo4j_repos.passages import passage_canonical_id

    base = dict(user_id="u", project_id="p", source_type="chapter",
                source_id="ch1", chunk_index=0)
    zh = passage_canonical_id(**base, source_lang="zh")
    vi = passage_canonical_id(**base, source_lang="vi")
    none = passage_canonical_id(**base)
    assert zh != vi  # distinct nodes per language
    # back-compat: no lang == "" == "unknown" handled by caller; bare call stable
    assert passage_canonical_id(**base, source_lang="") == none
    # KG-ML M7 (D-KG-ML-MULTI-TRANSLATION-LANG cleared) — 2+ translation
    # languages of ONE chapter coexist: source zh + vi + en translations are
    # THREE distinct nodes (same source_id), none colliding with each other or
    # the back-compat untagged id.
    en = passage_canonical_id(**base, source_lang="en")
    assert len({zh, vi, en, none}) == 4


@pytest.mark.asyncio
async def test_ingest_text_override_bypasses_book_fetch(monkeypatch):
    """M2: text_override (a translation's text) skips the book-service fetch and
    drives the same chunk→embed→upsert path with source_lang stamped."""
    import app.extraction.passage_ingester as pi

    book = _mk_book_client(text="SHOULD NOT BE USED")
    book.get_chapter_text_and_blocks = AsyncMock(
        side_effect=AssertionError("book fetch must not run for text_override"),
    )

    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
    emb = MagicMock()
    emb.embed = fake_embed
    upsert = AsyncMock()
    delete = AsyncMock(return_value=0)
    monkeypatch.setattr(pi, "upsert_passage", upsert)
    monkeypatch.setattr(pi, "delete_passages_for_source", delete)

    vi_text = "Bá tước Dracula bước vào lâu đài. " * 200
    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=1,
        embedding_model="bge-m3", embedding_dim=1024,
        source_lang="vi", text_override=vi_text, canon=True,
    )
    assert result.chunks_created > 0
    assert result.source_lang == "vi"
    # the delete was language-scoped to vi (never wipes zh source passages)
    assert delete.await_args.kwargs["source_lang"] == "vi"
    for call in upsert.await_args_list:
        assert call.kwargs["source_lang"] == "vi"


@pytest.mark.asyncio
async def test_backfill_source_lang_tags_per_chapter(monkeypatch):
    """KG-ML M1: backfill_source_lang reads each chapter's declared
    original_language and tags its passages (no re-embed)."""
    from app.extraction.passage_ingester import backfill_source_lang

    book = MagicMock()
    book.list_chapters = AsyncMock(return_value=[
        {"chapter_id": str(CHAPTER_ID), "original_language": "zh"},
        {"chapter_id": "55555555-5555-5555-5555-555555555555",
         "original_language": ""},  # no declared lang → skipped
    ])
    tag = AsyncMock(return_value=4)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.set_source_lang_for_source", tag,
    )

    res = await backfill_source_lang(
        MagicMock(), book, user_id=USER_ID, book_id=BOOK_ID,
    )
    assert res.chapters_tagged == 1
    assert res.chapters_skipped == 1
    assert res.passages_tagged == 4
    tag.assert_awaited_once()
    assert tag.await_args.kwargs["source_lang"] == "zh"


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


# ── CM3c: pinned-revision fetch + delete_stale_on_missing ────────────


@pytest.mark.asyncio
async def test_ingest_fetches_pinned_revision_when_revision_id_set(monkeypatch):
    """CM3c: revision_id set → fetch the PINNED revision text (not the live
    draft via get_chapter_text)."""
    rev = uuid4()
    book = _mk_book_client()
    emb = _mk_embedding_client(n_vectors=1, dim=1024)
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", AsyncMock())
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source",
        AsyncMock(return_value=0),
    )

    await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=None,
        embedding_model="bge-m3", embedding_dim=1024,
        revision_id=rev,
    )
    book.get_chapter_revision_text.assert_awaited_once_with(
        BOOK_ID, CHAPTER_ID, str(rev),
    )
    book.get_chapter_text.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_keeps_passages_when_revision_missing_and_flag_false(monkeypatch):
    """CM3c (R3-WARN#1): a transient pinned-revision fetch returning None with
    delete_stale_on_missing=False must NOT delete existing passages (else L3
    passages vanish while the graph half holds canon)."""
    rev = uuid4()
    book = _mk_book_client(revision_text=None)
    emb = _mk_embedding_client()
    delete = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", delete,
    )

    result = await ingest_chapter_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID,
        book_id=BOOK_ID, chapter_id=CHAPTER_ID, chapter_index=None,
        embedding_model="bge-m3", embedding_dim=1024,
        revision_id=rev, delete_stale_on_missing=False,
    )
    assert result.chunks_created == 0
    delete.assert_not_awaited()  # passages preserved
    emb.embed.assert_not_called()


# ── D-KG-PASSAGE-BACKFILL — published-chapter passage backfill ───────────────


def _book_with_published(chapters, text="Arthur rode toward Camelot. " * 20):
    """book_client whose list_chapters returns `chapters` and whose per-chapter live
    text yields one chunk (so each published chapter ingests one passage)."""
    book = _mk_book_client(text=text)
    book.list_chapters = AsyncMock(return_value=chapters)
    return book


def _dyn_embed():
    """Embedding stub that returns exactly len(texts) vectors (so any chunk count
    matches and ingest upserts every chunk)."""
    async def fake_embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[[0.1] * 1024 for _ in texts], dimension=1024, model="bge-m3",
        )
    emb = MagicMock()
    emb.embed = fake_embed
    return emb


@pytest.mark.asyncio
async def test_backfill_ingests_every_published_chapter_as_canon(monkeypatch):
    """The backfill enumerates PUBLISHED chapters and ingests each as canon=True —
    the fix for chapters published before the project/embedding existed."""
    chapters = [
        {"chapter_id": str(uuid4()), "sort_order": 1, "editorial_status": "published"},
        {"chapter_id": str(uuid4()), "sort_order": 2, "editorial_status": "published"},
    ]
    book = _book_with_published(chapters)
    emb = _dyn_embed()
    upsert = AsyncMock()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", upsert)
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source",
        AsyncMock(return_value=0),
    )

    res = await backfill_published_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    # Scopes to PUBLISHED chapters only.
    book.list_chapters.assert_awaited_once_with(BOOK_ID, editorial_status="published")
    assert res.chapters_indexed == 2
    assert res.passages_created == 2  # one chunk per chapter
    assert upsert.await_count == 2
    # Published passages are canon.
    for call in upsert.await_args_list:
        assert call.kwargs["canon"] is True


@pytest.mark.asyncio
async def test_backfill_no_published_chapters_is_noop(monkeypatch):
    """Empty (or None) published list → no ingest, no embed calls."""
    book = _book_with_published([])
    emb = _dyn_embed()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", AsyncMock())
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source", AsyncMock(),
    )
    res = await backfill_published_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert res == BackfillResult(0, 0, 0)

    # list_chapters returning None (book-service down) is also a clean no-op.
    book.list_chapters = AsyncMock(return_value=None)
    res2 = await backfill_published_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert res2 == BackfillResult(0, 0, 0)


@pytest.mark.asyncio
async def test_backfill_skips_malformed_chapter_but_processes_rest(monkeypatch):
    """A chapter row missing chapter_id is skipped; the valid ones still ingest
    (best-effort — one bad item never aborts the backfill)."""
    good = str(uuid4())
    chapters = [
        {"sort_order": 1, "editorial_status": "published"},          # no chapter_id
        {"chapter_id": good, "sort_order": 2, "editorial_status": "published"},
    ]
    book = _book_with_published(chapters)
    emb = _dyn_embed()
    monkeypatch.setattr("app.extraction.passage_ingester.upsert_passage", AsyncMock())
    monkeypatch.setattr(
        "app.extraction.passage_ingester.delete_passages_for_source",
        AsyncMock(return_value=0),
    )
    res = await backfill_published_passages(
        MagicMock(), book, emb,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=BOOK_ID,
        embedding_model="bge-m3", embedding_dim=1024,
    )
    assert res.chapters_indexed == 1
    assert res.chapters_skipped == 1
