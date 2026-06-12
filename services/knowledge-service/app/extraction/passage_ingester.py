"""D-K18.3-01 — passage ingestion pipeline.

Fetches chapter text from book-service, splits into overlapping
chunks, embeds them via provider-registry, and upserts them as
`:Passage` nodes. Called by the K14 event consumer's `chapter.saved`
handler. On `chapter.deleted` the companion delete path drops the
chapter's passages via `delete_passages_for_source`.

**Design notes:**

- **Paragraph-first chunking.** Split on double newline, aggregate
  paragraphs into chunks of up to `TARGET_CHARS`. Paragraphs that
  exceed the target on their own are fall-back-split on single
  newline and then on sentence boundaries. Overlap is `OVERLAP_CHARS`
  so cross-paragraph references survive chunk boundaries.

- **Idempotency.** Re-ingestion of the same chapter first deletes
  all existing passages for `(source_type='chapter', source_id)`,
  then upserts the fresh chunks. Simpler than computing diffs —
  the embed call dominates cost anyway.

- **Degradation.** Every external dependency is soft-failed: book
  fetch returns None → skip; embed raises → skip; per-chunk upsert
  exception → skip that chunk, continue with the rest. Extraction
  jobs are never blocked by passage ingestion.

- **Multi-tenant safety.** Caller passes `user_id` + `project_id`;
  every repo call carries those as parameters. No global-scope
  writes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    delete_passages_for_source,
    upsert_passage,
)

logger = logging.getLogger(__name__)

__all__ = [
    "IngestResult",
    "chunk_text",
    "ingest_chapter_passages",
    "delete_chapter_passages",
    "TARGET_CHARS",
    "OVERLAP_CHARS",
    "MIN_CHUNK_CHARS",
]


# ~375 tokens at 4 chars/token. Matches typical passage-retrieval
# chunk sizes used by LangChain / LlamaIndex defaults.
TARGET_CHARS = 1500
OVERLAP_CHARS = 200
# Chunks smaller than this are dropped — too short to embed
# meaningfully, and they cause MMR redundancy noise.
MIN_CHUNK_CHARS = 100

# Paragraph + sentence splitters. Sentence regex is intentionally
# simple — not a full NLP tokenizer; good enough for English +
# mixed script with ASCII punctuation.
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。!?])\s+")


@dataclass
class IngestResult:
    """Stats returned by `ingest_chapter_passages`."""

    chunks_created: int
    chunks_skipped: int
    embed_failed: bool = False


def chunk_text(
    text: str,
    *,
    target_chars: int = TARGET_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
    min_chunk_chars: int = MIN_CHUNK_CHARS,
) -> list[tuple[str, int]]:
    """Split `text` into ≲`target_chars` chunks with `overlap_chars` overlap.

    Priority of split points:
      1. Paragraph boundaries (double newline)
      2. Sentence boundaries inside oversized paragraphs
      3. Hard character cut at target_chars (last resort)

    Returns `(chunk, block_pos)` tuples in reading order, where `block_pos`
    is the 0-based index among NON-empty paragraphs at which the chunk's NEW
    (non-overlap) content begins. P3-C: chapter text_content is blocks joined
    by "\\n\\n" in block_index order, so block_pos maps to that chapter's
    `block_indices[block_pos]` → the real chapter_blocks.block_index, for
    precise jump-to-source. Chunks shorter than `min_chunk_chars` are dropped.
    """
    if not text or not text.strip():
        return []

    # Stage 1: paragraph split → flat (sentence, block_pos) list. block_pos
    # counts NON-empty paragraphs only (== chapter_blocks position in order).
    sentences: list[tuple[str, int]] = []
    block_pos = -1
    for raw_para in _PARAGRAPH_SPLIT.split(text):
        para = raw_para.strip()
        if not para:
            continue
        block_pos += 1
        if len(para) <= target_chars:
            sentences.append((para, block_pos))
            continue
        # Oversized paragraph → split on sentences, then hard-cut on
        # target_chars boundary as a last resort (all share this block_pos).
        for sent in _SENTENCE_SPLIT.split(para):
            sent = sent.strip()
            if not sent:
                continue
            while len(sent) > target_chars:
                sentences.append((sent[:target_chars], block_pos))
                sent = sent[target_chars - overlap_chars:]
            if sent:
                sentences.append((sent, block_pos))

    # Stage 2: greedily pack sentences into chunks up to target_chars.
    chunks: list[tuple[str, int]] = []
    current: list[str] = []
    current_len = 0
    first_pos: int | None = None
    for sent, pos in sentences:
        sent_len = len(sent) + 2  # "\n\n" separator
        if current and current_len + sent_len > target_chars:
            chunks.append(("\n\n".join(current), first_pos if first_pos is not None else 0))
            # Start next chunk with an overlap prefix — take tail of
            # the current chunk up to overlap_chars, snapped to the
            # nearest preceding whitespace so we don't store a
            # mid-word slice in the `text` field.
            overlap_prefix = _tail_at_word_boundary(
                "\n\n".join(current), overlap_chars,
            )
            current = [overlap_prefix, sent] if overlap_prefix else [sent]
            current_len = sum(len(s) + 2 for s in current)
            first_pos = pos  # NEW content's block (overlap prefix excluded)
        else:
            current.append(sent)
            current_len += sent_len
            if first_pos is None:
                first_pos = pos
    if current:
        chunks.append(("\n\n".join(current), first_pos if first_pos is not None else 0))

    # Stage 3: drop tiny chunks.
    return [(c, p) for c, p in chunks if len(c) >= min_chunk_chars]


def _tail_at_word_boundary(text: str, max_chars: int) -> str:
    """Return the tail of `text` of length ≤ `max_chars`, snapped to
    the nearest preceding whitespace so the tail starts on a whole
    word. Returns empty string when `max_chars <= 0`.

    If no whitespace is found within the slice, return the slice as-is
    (CJK + other scripts without spaces land here — sub-word
    tokenization handles them at embed time).
    """
    if max_chars <= 0 or not text:
        return ""
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:]
    # Find first whitespace → start the tail AFTER it so we don't
    # include a half-word prefix.
    ws_idx = -1
    for i, ch in enumerate(tail):
        if ch.isspace():
            ws_idx = i
            break
    if ws_idx == -1:
        return tail
    return tail[ws_idx + 1:]


async def ingest_chapter_passages(
    session: CypherSession,
    book_client: BookClient,
    embedding_client: EmbeddingClient,
    *,
    user_id: UUID,
    project_id: UUID,
    book_id: UUID,
    chapter_id: UUID,
    chapter_index: int | None,
    embedding_model: str,
    embedding_dim: int,
    model_source: str = "user_model",
    revision_id: UUID | None = None,
    delete_stale_on_missing: bool = True,
) -> IngestResult:
    """Fetch, chunk, embed, and upsert passages for one chapter.

    Idempotent: existing passages for this chapter are deleted first,
    then fresh chunks are written. Designed to be called from the
    K14 `chapter.published` handler (CM3c — canon = published).

    CM3c: when ``revision_id`` is set, fetch the PINNED published revision
    text (vs the live draft) so the semantic index canonizes only
    author-published content. ``delete_stale_on_missing`` controls the
    text-is-None branch: the published path passes ``False`` so a transient
    pinned-revision-fetch failure KEEPS the existing passages (otherwise L3
    passages would vanish while the graph half still holds canon — drift).

    Returns `IngestResult` with per-chunk counts. Does NOT raise on
    any single-chunk failure — the caller treats failures as "fewer
    passages available", not "extraction blocked".
    """
    result = IngestResult(chunks_created=0, chunks_skipped=0)

    if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
        logger.warning(
            "D-K18.3-01: skipping ingestion — embedding_dim %s not in %s",
            embedding_dim, SUPPORTED_PASSAGE_DIMS,
        )
        return result

    # 1. Fetch chapter text — pinned published revision (CM3c) or live draft.
    # block_indices (draft path, P3-C) maps a chunk's paragraph position → the
    # real chapter_blocks.block_index for precise jump-to-source; empty for the
    # revision path (canon precise-scroll deferred — no canon data yet).
    block_indices: list[int] = []
    if revision_id is not None:
        text = await book_client.get_chapter_revision_text(
            book_id, chapter_id, str(revision_id),
        )
    else:
        text, block_indices = await book_client.get_chapter_text_and_blocks(
            book_id, chapter_id,
        )
    if text is None:
        if not delete_stale_on_missing:
            # CM3c (R3-WARN#1): a transient pinned-revision-fetch failure must
            # NOT wipe canon passages — keep what we have, log visibly.
            logger.warning(
                "CM3c: pinned revision text unavailable for chapter=%s "
                "revision=%s — keeping existing passages",
                chapter_id, revision_id,
            )
            return result
        logger.info(
            "D-K18.3-01: no chapter text for chapter=%s (book-service returned None)",
            chapter_id,
        )
        # Still delete any stale passages so a chapter that becomes
        # unavailable doesn't keep orphaned :Passage rows.
        await delete_passages_for_source(
            session,
            user_id=str(user_id),
            source_type="chapter",
            source_id=str(chapter_id),
        )
        return result

    # P3-C (review-impl MED-2): block_pos→block_indices mapping only holds when
    # every chapter_block is exactly one non-empty paragraph. If the non-empty
    # paragraph count of text_content ≠ len(block_indices) (empty/media block, or
    # a block with internal "\n\n"), the alignment is unreliable — disable it so
    # we emit block_index=None (graceful top-open) rather than a WRONG block.
    if block_indices:
        para_count = sum(1 for p in _PARAGRAPH_SPLIT.split(text) if p.strip())
        if para_count != len(block_indices):
            logger.info(
                "P3-C: block-index map disabled for chapter=%s "
                "(%d paragraphs vs %d blocks) — semantic hits open chapter top",
                chapter_id, para_count, len(block_indices),
            )
            block_indices = []

    # 2. Chunk.
    chunks = chunk_text(text)
    if not chunks:
        logger.info(
            "D-K18.3-01: chunker produced no chunks for chapter=%s (text len=%d)",
            chapter_id, len(text),
        )
        return result

    # 3. Embed (one batch call). chunks are (text, block_pos) tuples (P3-C).
    chunk_texts = [c for c, _ in chunks]
    try:
        embed_result = await embedding_client.embed(
            user_id=user_id,
            model_source=model_source,
            model_ref=embedding_model,
            texts=chunk_texts,
        )
    except EmbeddingError:
        logger.warning(
            "D-K18.3-01: embed failed for chapter=%s project=%s — skipping",
            chapter_id, project_id, exc_info=True,
        )
        result.embed_failed = True
        return result

    if len(embed_result.embeddings) != len(chunks):
        logger.warning(
            "D-K18.3-01: embed returned %d vectors for %d chunks — skipping",
            len(embed_result.embeddings), len(chunks),
        )
        return result

    # 4. Delete stale passages, then upsert fresh.
    await delete_passages_for_source(
        session,
        user_id=str(user_id),
        source_type="chapter",
        source_id=str(chapter_id),
    )

    for idx, ((chunk, block_pos), vector) in enumerate(
        zip(chunks, embed_result.embeddings)
    ):
        if len(vector) != embedding_dim:
            logger.warning(
                "D-K18.3-01: chunk %d dim mismatch (got %d, expected %d) — skipping",
                idx, len(vector), embedding_dim,
            )
            result.chunks_skipped += 1
            continue
        # P3-C: map paragraph position → real block_index (draft path only).
        block_index = (
            block_indices[block_pos]
            if 0 <= block_pos < len(block_indices)
            else None
        )
        try:
            await upsert_passage(
                session,
                user_id=str(user_id),
                project_id=str(project_id),
                source_type="chapter",
                source_id=str(chapter_id),
                chunk_index=idx,
                text=chunk,
                embedding=vector,
                embedding_dim=embedding_dim,
                embedding_model=embedding_model,
                is_hub=False,  # chapter chunks are not hubs
                chapter_index=chapter_index,
                block_index=block_index,
            )
            result.chunks_created += 1
        except Exception:
            logger.exception(
                "D-K18.3-01: upsert failed chapter=%s chunk=%d — skipping",
                chapter_id, idx,
            )
            result.chunks_skipped += 1

    logger.info(
        "D-K18.3-01: ingested chapter=%s project=%s chunks=%d skipped=%d",
        chapter_id, project_id,
        result.chunks_created, result.chunks_skipped,
    )
    return result


async def delete_chapter_passages(
    session: CypherSession,
    *,
    user_id: UUID,
    chapter_id: UUID,
) -> int:
    """Delete all passages for a chapter.

    Called by the K14 `chapter.deleted` handler. Returns the count
    of deleted passages.
    """
    return await delete_passages_for_source(
        session,
        user_id=str(user_id),
        source_type="chapter",
        source_id=str(chapter_id),
    )
