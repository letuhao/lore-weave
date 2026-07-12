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

import hashlib
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable
from uuid import UUID

from app.clients.book_client import BookClient
from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    delete_passages_for_source,
    get_source_ingest_state,
    set_source_lang_for_source,
    upsert_passage,
)
from app.extraction.patterns import detect_primary_language
from app.jobs.budget import record_spending
from app.pricing import cost_per_token

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

__all__ = [
    "IngestResult",
    "BackfillResult",
    "SourceLangBackfillResult",
    "chunk_text",
    "ingest_chapter_passages",
    "backfill_published_passages",
    "backfill_source_lang",
    "delete_chapter_passages",
    "resolve_source_lang",
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
    # KG-ML M1 (C10) — true when the content-hash skip-gate matched (text
    # unchanged since last ingest) so the embed + re-bill cycle was skipped.
    skipped_unchanged: bool = False
    # KG-ML M1 — the resolved source language stamped onto the passages.
    source_lang: str = "unknown"


def resolve_source_lang(
    declared: str | None, text: str
) -> tuple[str, bool]:
    """KG-ML M1 (DD1) — resolve the authoritative source language for a passage set.

    Prefers the chapter's declared `original_language`; falls back to
    `detect_primary_language(text)` when the declared value is absent/unknown.
    Returns `(source_lang, mixed)` where `mixed` is True only when detection is
    ambiguous (`detect_primary_language` returned "mixed") — in that case
    `source_lang` is stored as "mixed" and ranking treats it as matching any
    query language (M4).

    The declared value is normalized to its ISO-639-1 primary subtag (BCP-47
    region/script stripped: "zh-CN"→"zh", "en_US"→"en") so M4's
    `reader_pref == source_lang` comparison doesn't silently miss on a regional
    variant. `detect_primary_language` already returns bare ISO-639-1 codes.
    """
    declared_norm = (declared or "").strip().lower()
    if declared_norm and declared_norm != "unknown":
        # Primary subtag only — split on BCP-47 '-' or locale '_'.
        return re.split(r"[-_]", declared_norm, maxsplit=1)[0], False
    detected = detect_primary_language(text)
    if detected == "mixed":
        return "mixed", True
    return detected, False


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
    canon: bool = True,
    source_lang: str | None = None,
    text_override: str | None = None,
    pool: "asyncpg.Pool | None" = None,
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

    `canon` (D-RAWSEARCH-CANON-WIRING): stamped onto every passage. The
    `chapter.published` handler keeps the default True; the on-demand
    owner-only draft-indexing endpoint passes False so `surface=all` can
    surface drafts while `surface=canon` (default) excludes them.

    D-R20 (P-3, keep-both): the canon and draft passages of a chapter are
    DISTINCT nodes (`passage_canonical_id` gains a `draft:` segment for
    canon=False) and the pre-write reap is bucket-scoped. So indexing a NEWER
    draft on a PUBLISHED chapter now KEEPS BOTH — the published canon passages
    stay in `surface=canon`, the draft is added under `surface=all`. A later
    publish (canon=True) reaps BOTH buckets and re-writes the pinned revision as
    canon, superseding the ahead-of-canon draft.
    """
    result = IngestResult(chunks_created=0, chunks_skipped=0)

    if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
        logger.warning(
            "D-K18.3-01: skipping ingestion — embedding_dim %s not in %s",
            embedding_dim, SUPPORTED_PASSAGE_DIMS,
        )
        return result

    # 1. Resolve chapter text. KG-ML M2: `text_override` (a translation's text)
    # bypasses the book-service fetch entirely so the SAME chunk→embed→upsert
    # path (skip-gate, cost metering, language-scoped delete) serves dual-indexed
    # vi passages. Precise-scroll (block_indices) is deferred for translations
    # (no per-block map yet) → empty, hits open the chapter top.
    block_indices: list[int] = []
    if text_override is not None:
        text = text_override
    elif revision_id is not None:
        # pinned published revision (CM3c)
        text = await book_client.get_chapter_revision_text(
            book_id, chapter_id, str(revision_id),
        )
    else:
        # live draft, P3-C maps a chunk's paragraph position → the real
        # chapter_blocks.block_index for precise jump-to-source.
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
        # unavailable doesn't keep orphaned :Passage rows. D-R20 (P-3): scope to
        # the bucket being (not) written — a draft whose live text vanished reaps
        # only the draft bucket, never the published canon passages.
        await delete_passages_for_source(
            session,
            user_id=str(user_id),
            source_type="chapter",
            source_id=str(chapter_id),
            canon=None if canon else False,
        )
        return result

    # KG-ML M1 (DD1) — resolve the authoritative source language (declared
    # chapter original_language, else detect from text). Stamped onto passages.
    resolved_lang, mixed = resolve_source_lang(source_lang, text)
    result.source_lang = resolved_lang

    # KG-ML M1 (C10) — content-hash skip-gate. Skip the (delete + embed + re-bill)
    # cycle ONLY when the fresh text hash AND canon AND chapter_index all match the
    # cached state — so a no-op republish bills zero, but a draft→publish canon flip
    # or a chapter reorder (same text, changed metadata) still re-ingests correctly
    # instead of being silently skipped. Legacy passages carry no hash → cache miss
    # → ingest proceeds (and stamps a hash for next time). On skip we still cheaply
    # re-tag source_lang (declared language may have been corrected without a text edit).
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    state = await get_source_ingest_state(
        session,
        user_id=str(user_id),
        source_type="chapter",
        source_id=str(chapter_id),
        source_lang=resolved_lang,
        # D-R20 (P-3) — per-bucket skip-gate: read the SAME bucket we're about to
        # write so the canon and draft sets never cross-contaminate the hash gate.
        canon=canon,
    )
    if (
        state is not None
        and state["content_hash"] == content_hash
        and state["canon"] == canon
        and state["chapter_index"] == chapter_index
        and state["embedding_model"] == embedding_model
    ):
        await set_source_lang_for_source(
            session,
            user_id=str(user_id),
            source_type="chapter",
            source_id=str(chapter_id),
            source_lang=resolved_lang,
            mixed=mixed,
        )
        result.skipped_unchanged = True
        result.source_lang = resolved_lang
        logger.info(
            "KG-ML M1: skip-gate hit chapter=%s (text+canon+index unchanged) — no re-embed",
            chapter_id,
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

    # KG-ML M1 (C10) — record embedding spend against the project counter (the
    # same record_spending path summary-regen uses). Best-effort: a metering
    # failure must never block ingestion. Pool-less callers (tests/benchmark)
    # skip metering. Fixes the pre-existing leak (embed prompt_tokens were
    # computed-then-discarded here and in the drawers path).
    if pool is not None and embed_result.prompt_tokens > 0:
        try:
            cost = cost_per_token(embed_result.model) * Decimal(
                embed_result.prompt_tokens
            )
            if cost > 0:
                await record_spending(pool, user_id, project_id, cost)
        except Exception:  # noqa: BLE001 — metering is best-effort, never blocks
            logger.warning(
                "KG-ML M1: embed cost metering failed chapter=%s project=%s — non-fatal",
                chapter_id, project_id, exc_info=True,
            )

    # 4. Delete stale passages (THIS language only — never wipe the other
    # language's passages of the same chapter), then upsert fresh.
    #
    # D-R20 (P-3, keep-both): the reap is BUCKET-scoped. A DRAFT index (canon=False)
    # reaps ONLY the draft bucket, so the chapter's PUBLISHED canon passages survive
    # side by side (canon search still sees the published revision; surface=all sees
    # the newer draft). A PUBLISH (canon=True) reaps BOTH buckets (canon=None) —
    # publishing establishes the new canon and supersedes any ahead-of-canon draft.
    await delete_passages_for_source(
        session,
        user_id=str(user_id),
        source_type="chapter",
        source_id=str(chapter_id),
        source_lang=resolved_lang,
        canon=None if canon else False,
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
                canon=canon,
                block_index=block_index,
                source_lang=resolved_lang,
                mixed=mixed,
                content_hash=content_hash,
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


@dataclass
class BackfillResult:
    """Outcome of a published-chapter passage backfill (D-KG-PASSAGE-BACKFILL)."""

    chapters_indexed: int
    chapters_skipped: int
    passages_created: int


async def backfill_published_passages(
    session: CypherSession,
    book_client: BookClient,
    embedding_client: EmbeddingClient,
    *,
    user_id: UUID,
    project_id: UUID,
    book_id: UUID,
    embedding_model: str,
    embedding_dim: int,
    pool: "asyncpg.Pool | None" = None,
    chapter_range: tuple[int, int] | None = None,
    max_chapters: int | None = None,
) -> BackfillResult:
    """D-KG-PASSAGE-BACKFILL — ingest `:Passage` nodes for a book's already-PUBLISHED
    chapters as `canon=True`.

    Scope (D-BACKFILL-NO-SCOPE-LIMIT): ``chapter_range=(lo, hi)`` (inclusive
    ``sort_order``) bounds the backfill to a slice — used so a scoped extraction only
    ingests the chapters it extracts, never the whole book. ``max_chapters`` is a
    runaway guard for the UNSCOPED inline (embedding-PUT) path: when no range is given
    and the published-chapter count exceeds it, the backfill is SKIPPED (returns zero)
    rather than synchronously embedding an entire large book in-request. A caller that
    wants the whole book indexed starts a (scoped or unscoped) extraction job, whose
    backfill runs off the request path.

    Fixes the ordering gap: passages are normally ingested by the `chapter.published`
    event handler, but that handler SKIPS when no knowledge project / embedding model
    exists yet (handlers.py). In the natural flow a user publishes chapters BEFORE
    creating the KG project + setting the embedding model, so the publish events fire
    too early and nothing ever backfills — wiki/enrichment then have no grounding.

    Called the moment passages become ingestable (the embedding model is set on the
    project). Idempotent: `ingest_chapter_passages` deletes-then-upserts per chapter,
    so a re-run refreshes rather than duplicates. Best-effort per chapter — a single
    chapter's failure never aborts the rest (mirrors the event-handler degradation).

    Uses the live (current) chapter text (`revision_id=None`), which equals the
    published canon at setup time; a later edit+republish re-ingests at the pinned
    revision via the event path.
    """
    # WS-0.6: enumerate the chapters that are IN the knowledge graph, not the published
    # ones — a user's explicitly-indexed drafts must get :Passage nodes too, or they are
    # invisible to L3 semantic retrieval and to chat grounding.
    #
    # ⚠️ This re-keys the ENUMERATION ONLY. The `canon` flag on the ingested passages is
    # NOT re-keyed: `canon = (revision_id == published_revision_id)` stays the rule
    # (spec §3.7 / P1-8). Draft prose must not become canon=True passages — raw_search
    # documents a deliberate draft/canon split, and blindly flipping it here would be
    # the inverse bug: unreviewed draft prose surfacing as canon.
    items = await book_client.list_chapters(book_id, kg_indexed=True)
    if not items:
        return BackfillResult(0, 0, 0)

    # D-BACKFILL-NO-SCOPE-LIMIT — bound to a chapter slice when asked, else guard the
    # unscoped whole-book path against a runaway synchronous embed on a large book.
    if chapter_range is not None:
        lo, hi = chapter_range
        items = [
            it for it in items
            if isinstance(it.get("sort_order"), int) and lo <= it["sort_order"] <= hi
        ]
    elif max_chapters and len(items) > max_chapters:
        logger.warning(
            "D-KG-PASSAGE-BACKFILL: book=%s has %d published chapters > inline cap %d; "
            "SKIPPING inline backfill — start a (scoped) extraction to ingest passages",
            book_id, len(items), max_chapters,
        )
        return BackfillResult(0, 0, 0)

    indexed = skipped = created = 0
    for item in items:
        try:
            chapter_id = UUID(str(item["chapter_id"]))
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        sort_order = item.get("sort_order")
        chapter_index = sort_order if isinstance(sort_order, int) else None
        # KG-ML M1 (DD1/V2) — stamp each chapter's OWN declared original_language
        # (per-chapter, never a book-level default) so a multi-source-language
        # book is tagged correctly; falls back to text detection in the ingester.
        declared_lang = item.get("original_language")

        # ── review-impl P0 — PIN the revision and DERIVE canon ──
        #
        # This used to pass `revision_id=None, canon=True`, which was defensible when the
        # enumeration was `editorial_status=published`: "live text == canon at setup time".
        # WS-0.6b re-keyed the enumeration to kg_indexed=True, and that assumption died
        # with it. The set now contains never-published, user-indexed DRAFT chapters, so:
        #
        #   revision_id=None -> ingest_chapter_passages reads the LIVE DRAFT, including
        #                       prose typed AFTER the user's index action. The passages no
        #                       longer correspond to the revision the graph facts were
        #                       extracted from, and we pay embedding cost on text the user
        #                       never asked us to index.
        #   canon=True       -> stamps that unreviewed draft prose CANONICAL, so it is
        #                       returned by the DEFAULT `surface=canon` vector search used
        #                       for chat grounding, and cited as canon.
        #
        # Both are now derived from the row, matching handle_chapter_kg_indexed exactly
        # (spec §3.7 / P1-8: canon = (revision_id == published_revision_id)).
        rev = item.get("kg_indexed_revision_id") or item.get("published_revision_id")
        if not rev:
            logger.warning(
                "D-KG-PASSAGE-BACKFILL: chapter=%s is enumerated but has NO pinned "
                "revision — skipping rather than embedding its live draft as canon",
                chapter_id,
            )
            skipped += 1
            continue
        published_rev = item.get("published_revision_id")
        canon = bool(published_rev) and str(published_rev) == str(rev)

        try:
            res = await ingest_chapter_passages(
                session,
                book_client,
                embedding_client,
                user_id=user_id,
                project_id=project_id,
                book_id=book_id,
                chapter_id=chapter_id,
                chapter_index=chapter_index,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                revision_id=UUID(str(rev)),
                canon=canon,
                source_lang=declared_lang,
                pool=pool,
            )
            if res.chunks_created > 0:
                indexed += 1
                created += res.chunks_created
            else:
                skipped += 1
        except Exception:  # noqa: BLE001 — one chapter's failure must not abort the rest
            logger.warning(
                "D-KG-PASSAGE-BACKFILL: ingest failed for chapter=%s book=%s — non-fatal",
                chapter_id, book_id, exc_info=True,
            )
            skipped += 1
    logger.info(
        "D-KG-PASSAGE-BACKFILL: book=%s project=%s chapters_indexed=%d skipped=%d passages=%d",
        book_id, project_id, indexed, skipped, created,
    )
    return BackfillResult(indexed, skipped, created)


@dataclass
class SourceLangBackfillResult:
    """Outcome of the tag-only `source_lang` backfill (KG-ML M1)."""

    chapters_tagged: int
    chapters_skipped: int
    passages_tagged: int


async def backfill_source_lang(
    session: CypherSession,
    book_client: BookClient,
    *,
    user_id: UUID,
    book_id: UUID,
) -> SourceLangBackfillResult:
    """KG-ML M1 (DD1) — stamp `source_lang` on EXISTING passages WITHOUT re-embedding.

    For each chapter, read its declared `original_language` from book-service and
    set it on every already-ingested `:Passage` of that chapter (pure property
    write via `set_source_lang_for_source` — no embed, bills zero). This is the
    one-shot that tags legacy passages written before the `source_lang` column
    existed; run alongside the published-passage backfill at embedding-model set.

    Per-chapter (DD/V2): uses each chapter's own `original_language`, never a
    book-level default, so a multi-source-language book is tagged correctly. A
    chapter with no declared language is left "unknown" (skipped) rather than
    guessed — the live ingest path will resolve it from text on next republish.
    """
    items = await book_client.list_chapters(book_id)
    if not items:
        return SourceLangBackfillResult(0, 0, 0)

    tagged_chapters = skipped = passages = 0
    for item in items:
        try:
            chapter_id = UUID(str(item["chapter_id"]))
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        lang = (item.get("original_language") or "").strip().lower()
        if not lang:
            skipped += 1
            continue
        try:
            n = await set_source_lang_for_source(
                session,
                user_id=str(user_id),
                source_type="chapter",
                source_id=str(chapter_id),
                source_lang=lang,
                mixed=False,
            )
            if n > 0:
                tagged_chapters += 1
                passages += n
            else:
                skipped += 1
        except Exception:  # noqa: BLE001 — one chapter's failure must not abort the rest
            logger.warning(
                "KG-ML M1: source_lang backfill failed chapter=%s book=%s — non-fatal",
                chapter_id, book_id, exc_info=True,
            )
            skipped += 1
    logger.info(
        "KG-ML M1: source_lang backfill book=%s chapters_tagged=%d skipped=%d passages=%d",
        book_id, tagged_chapters, skipped, passages,
    )
    return SourceLangBackfillResult(tagged_chapters, skipped, passages)
