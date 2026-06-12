"""Book-chapter grounding ingest (de-bias C2 T6 core, LE-PROD slice C).

Extracted from the ``POST /books/{id}/ground`` handler so the SAME ingest path is
reusable by (a) the author's chapter-SELECTION UI (the endpoint, ``chapter_ids``
supplied) and (b) a reproducible SEED that grounds a whole book (``chapter_ids=
None`` → every chapter). Production retrieval was starved because the demo book's
chapters — real prose in book-service/MinIO — were never ingested as a
``source_corpus``; this is the one place that fixes that, for any book.

Reuses the existing :meth:`SourceCorpusStore.ingest_corpus` seam (chunk + REAL
embed via provider-registry by ``model_ref`` — NO hardcoded model name) and the
SAME corpus name ``book-chapters:{book_id}``, so the seed and the UI ingest are
idempotent against each other (content-hashed chunks). License ``licensed`` (the
chapters are author-owned → re-cook-admissible), identical to the endpoint.

H0 unchanged: this only INGESTS grounding evidence — it writes no proposal, no
canon, no glossary/KG. Degrades on book/embed failure via typed errors the caller
maps to a status (the endpoint) or reports (the seed)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from app.clients.book import BookClient
from app.clients.knowledge import KnowledgeClient
from app.config import settings
from app.retrieval.store import SourceCorpusStore

logger = logging.getLogger("lore_enrichment.book_grounding")

__all__ = [
    "BookGroundingResult",
    "NoChapterTextError",
    "ingest_book_chapters",
    "book_corpus_name",
]


def book_corpus_name(book_id: UUID) -> str:
    """The deterministic corpus name for a book's chapter grounding — shared by the
    UI ingest and the seed so re-runs are idempotent (one corpus per book)."""
    return f"book-chapters:{book_id}"


class NoChapterTextError(Exception):
    """No selected/available chapter yielded text to ground on (the caller maps
    this to a 400 / a clear seed message — nothing was ingested)."""


@dataclass(frozen=True)
class BookGroundingResult:
    chapters_ingested: int
    chunks_total: int
    chunks_inserted: int
    chunks_embedded: int


async def ingest_book_chapters(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    project_id: UUID,
    book_id: UUID,
    embedding_model_ref: UUID,
    chapter_ids: list[UUID] | None = None,
    target_chars: int = 800,
) -> BookGroundingResult:
    """Ingest a book's chapters as a grounding corpus.

    ``chapter_ids`` supplied → the author's SELECTION (the UI path). ``None`` → ALL
    chapters (the seed/bulk path: list them via book-service first). Each chapter's
    draft text is read (injection-neutralized in the client), concatenated, chunked
    + embedded into the ``book-chapters:{book_id}`` corpus. Idempotent. Raises
    :class:`NoChapterTextError` when nothing has text, :class:`BookServiceError` /
    :class:`KnowledgeServiceError` on an upstream failure (caller maps/reports)."""
    book = BookClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
    )
    texts: list[str] = []
    try:
        ids = chapter_ids
        if ids is None:
            # Seed/bulk: resolve EVERY chapter id (the UI never hits this — it always
            # passes an explicit selection). 200 covers the demo; if a book ever
            # exceeds it, WARN rather than silently under-ground (no silent cap).
            _LIST_LIMIT = 200
            metas, total = await book.list_chapters(book_id=book_id, limit=_LIST_LIMIT)
            if total > len(metas):
                logger.warning(
                    "book %s has %d chapters but the seed only grounds the first %d "
                    "(raise the limit / paginate to cover the rest)",
                    book_id, total, len(metas),
                )
            ids = [m.chapter_id for m in metas]
        for chapter_id in ids:
            t = await book.get_chapter_text(book_id=book_id, chapter_id=chapter_id)
            if t.strip():
                texts.append(t)
    finally:
        await book.aclose()
    if not texts:
        raise NoChapterTextError(
            "no chapter text to ground on (empty selection or all chapters blank)"
        )

    kc = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )

    async def embed_fn(chunk_texts):
        result = await kc.embed(
            user_id=user_id, model_source="user_model",
            model_ref=str(embedding_model_ref), texts=list(chunk_texts),
        )
        return result.embeddings

    store = SourceCorpusStore(pool)
    try:
        ingest = await store.ingest_corpus(
            user_id=user_id, project_id=project_id,
            name=book_corpus_name(book_id), kind="other", license="licensed",
            text="\n\n".join(texts), embed_fn=embed_fn,
            model_ref=str(embedding_model_ref), target_chars=target_chars,
        )
    finally:
        await kc.aclose()

    return BookGroundingResult(
        chapters_ingested=len(texts),
        chunks_total=ingest.chunks_total,
        chunks_inserted=ingest.chunks_inserted,
        chunks_embedded=ingest.chunks_embedded,
    )
