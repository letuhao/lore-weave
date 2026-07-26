"""Source-corpus + chunk persistence and in-process similarity search (C10).

Technique-(b) retrieval over the OWNED corpora. This module:

  * INGESTS a corpus text — upserts a ``source_corpus`` row (C2) and persists
    its deterministic chunks (``chunker.chunk_text``) into ``source_corpus_chunk``
    (C10). Ingest is IDEMPOTENT: a re-run of identical text produces the SAME
    chunk set (UNIQUE(corpus_id, chunk_index) + content hash) — no duplicates,
    no silent re-embed of unchanged chunks.
  * EMBEDS chunks by calling an injected ``embed_fn`` that REUSES knowledge-
    service ``/internal/embed`` (the C1 ``KnowledgeClient.embed``) — the model is
    a provider-registry ``model_ref``, NEVER a hardcoded name. The resolving
    ``model_ref`` + dimension are stored alongside each vector so a later
    embedding-model change is DETECTABLE (incomparable vector spaces = a real
    bug class on this platform).
  * SEARCHES by cosine similarity, in-process, over a project's chunks (the
    platform does NOT enable pgvector). Pure stdlib math — no numpy, no vector
    DB, no heavy dep. Scoped per (user, project) (Q3).

H0 / scope boundary: this is a READ/owned-corpus layer. It writes ONLY to the
service's own ``source_corpus*`` tables — never to glossary / KG / Neo4j, never
``source_type='glossary'``. Grounding refs it produces feed a *proposal* only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence
from uuid import UUID

import asyncpg
from loreweave_vecmath import cosine_similarity

from app.retrieval.chunker import (
    DEFAULT_OVERLAP_SENTENCES,
    DEFAULT_TARGET_CHARS,
    Chunk,
    chunk_text,
)

__all__ = [
    "EmbedFn",
    "StoredChunk",
    "ScoredChunk",
    "IngestResult",
    "cosine_similarity",
    "top_k",
    "SourceCorpusStore",
]

#: An async embedding callable: list[str] → list[vector]. Injected so the store
#: never imports an HTTP/LLM client directly — the strategy wires the real C1
#: ``KnowledgeClient.embed`` (model_ref) in, tests pass a deterministic stub.
EmbedFn = Callable[[Sequence[str]], Awaitable[list[list[float]]]]


@dataclass(frozen=True)
class StoredChunk:
    """A persisted chunk hydrated from the DB (vector may be absent)."""

    chunk_id: UUID
    corpus_id: UUID
    chunk_index: int
    content: str
    embedding: list[float] | None
    embedding_model_ref: str | None


@dataclass(frozen=True)
class ScoredChunk:
    """A chunk paired with its similarity score against a query (search result)."""

    chunk_id: UUID
    corpus_id: UUID
    chunk_index: int
    content: str
    score: float


@dataclass(frozen=True)
class IngestResult:
    """Outcome of an ingest call: the corpus id + chunk-count bookkeeping so a
    caller (and the idempotency test) can see that a re-run added nothing."""

    corpus_id: UUID
    chunks_total: int
    chunks_inserted: int
    chunks_embedded: int


# ── pure similarity math (stdlib only — unit-testable without a DB) ───────────
# `cosine_similarity` is the shared loreweave_vecmath implementation (imported
# above); re-exported here (via __all__) for backward compatibility with the
# existing `from app.retrieval.store import cosine_similarity` call sites.


def top_k(
    query: Sequence[float],
    candidates: Sequence[StoredChunk],
    *,
    k: int,
) -> list[ScoredChunk]:
    """Rank ``candidates`` by descending cosine similarity to ``query``; return
    the top ``k``. Candidates without an embedding are skipped. Deterministic
    total order: ties break by ascending ``chunk_index`` then ``chunk_id`` so the
    result is reproducible regardless of input order. ``k <= 0`` → ``[]``."""
    if k <= 0:
        return []
    scored: list[ScoredChunk] = []
    for c in candidates:
        if not c.embedding:
            continue
        score = cosine_similarity(query, c.embedding)
        scored.append(
            ScoredChunk(
                chunk_id=c.chunk_id,
                corpus_id=c.corpus_id,
                chunk_index=c.chunk_index,
                content=c.content,
                score=score,
            )
        )
    scored.sort(key=lambda s: (-s.score, s.chunk_index, str(s.chunk_id)))
    return scored[:k]


class SourceCorpusStore:
    """Persistence + retrieval over ``source_corpus`` / ``source_corpus_chunk``.

    Constructed with an asyncpg pool. All writes are scoped to the (user,
    project) pair supplied per call (Q3). Nothing here writes outside the
    service's own tables.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── license lookup (for the C17 re-cook licensing gate) ──────────────────
    async def get_corpus_license(self, *, corpus_id: UUID) -> str | None:
        """Return the raw ``source_corpus.license`` for ``corpus_id``, or None if
        the corpus does not exist.

        Read-only single-column lookup the C17 re-cook strategy uses to resolve a
        source's license at corpus-admission / fact-emit. A None result (unknown
        corpus) is treated by the caller as an UNKNOWN license → refused
        (default-deny). Nothing here is scoped per-project: the corpus_id is a
        primary key, and the re-cook only reaches here with ids from grounding it
        already retrieved within the project scope.
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT license FROM source_corpus WHERE corpus_id = $1",
                corpus_id,
            )

    # ── corpus upsert (idempotent on (user, project, name, kind)) ────────────
    async def get_corpus(
        self, *, user_id: UUID, project_id: UUID, corpus_id: UUID
    ) -> dict | None:
        """Load one corpus scoped to (user, project), or None (→ 404). Used by the
        ingest endpoint to recover name/kind/license for the existing row."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT corpus_id, name, kind, license, provenance_json,
                          created_at
                   FROM source_corpus
                   WHERE corpus_id=$1 AND user_id=$2 AND project_id=$3""",
                corpus_id, user_id, project_id,
            )
        return dict(row) if row is not None else None

    async def list_corpora(
        self, *, user_id: UUID, project_id: UUID, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        """List the (user, project) corpora with chunk counts (the GET /sources
        read). Returns (page, total). Ordered newest-first, stable by corpus_id."""
        async with self._pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM source_corpus WHERE user_id=$1 AND project_id=$2",
                user_id, project_id,
            )
            rows = await conn.fetch(
                """SELECT c.corpus_id, c.name, c.kind, c.license, c.provenance_json,
                          c.created_at,
                          (SELECT COUNT(*) FROM source_corpus_chunk ch
                             WHERE ch.corpus_id = c.corpus_id) AS chunk_count,
                          (SELECT COUNT(*) FROM source_corpus_chunk ch
                             WHERE ch.corpus_id = c.corpus_id
                               AND ch.embedding IS NOT NULL) AS chunks_embedded
                   FROM source_corpus c
                   WHERE c.user_id=$1 AND c.project_id=$2
                   ORDER BY c.created_at DESC, c.corpus_id
                   LIMIT $3 OFFSET $4""",
                user_id, project_id, limit, offset,
            )
        return [dict(r) for r in rows], int(total or 0)

    async def mark_corpus_persistent(self, *, corpus_id: UUID) -> None:
        """Clear the ``compose_ephemeral`` tag so the reaper won't GC this corpus
        (#7 — the author chose to KEEP a compose paste/file as a curated source). Run
        AFTER an ingest when persist is requested: on a brand-new corpus the create
        already wrote ``compose_ephemeral=false``, but on an idempotent RE-ingest of
        identical text ``upsert_corpus`` returns the existing (possibly ephemeral) row
        untouched — this promotes it so "Save to sources" is honest either way.
        Idempotent."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE source_corpus
                   SET provenance_json =
                         jsonb_set(coalesce(provenance_json, '{}'::jsonb),
                                   '{compose_ephemeral}', 'false'),
                       updated_at = now()
                   WHERE corpus_id = $1""",
                corpus_id,
            )

    async def reap_ephemeral_corpora(self, *, ttl_seconds: float) -> list[UUID]:
        """Delete compose-ephemeral corpora older than ``ttl_seconds`` and return
        the deleted ids (D-COMPOSE-CONTEXT-CORPUS-SCOPE). Targets ONLY corpora
        tagged ``provenance_json->>'compose_ephemeral' = 'true'`` (the mode-C paste
        / mode-F file pastes) — NEVER the curated /sources reference library. Chunks
        + grounding refs cascade (FK ON DELETE CASCADE); a promoted proposal that
        cited one survives (its ``cultural_grounding_ref_id`` FK is ON DELETE SET
        NULL and its ``source_refs_json`` is a value snapshot, not an FK). ``ttl <=
        0`` is a no-op (disables reaping) so an accidental 0 never purges live data."""
        if ttl_seconds <= 0:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                DELETE FROM source_corpus
                WHERE provenance_json->>'compose_ephemeral' = 'true'
                  AND created_at < now() - ($1 * interval '1 second')
                RETURNING corpus_id
                """,
                ttl_seconds,
            )
        return [r["corpus_id"] for r in rows]

    async def upsert_corpus(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        name: str,
        kind: str,
        license: str = "unknown",
        provenance_json: dict | None = None,
    ) -> UUID:
        """Return the ``corpus_id`` for this (user, project, name, kind),
        creating the row if absent. Idempotent: the same logical corpus resolves
        to the same id across ingests (so re-ingest does not fork a new corpus).

        ``license`` defaults to ``"unknown"`` — an INADMISSIBLE value (C17 WARN-1).
        Re-cook's default-deny gate (``app/strategies/licensing.py``) REFUSES
        ``unknown``, so a corpus ingested WITHOUT an explicit ``license=`` fails
        CLOSED: it can never be silently re-cooked. A genuinely public-domain
        corpus MUST pass ``license="public-domain"`` explicitly. (The previous
        ``"public-domain"`` default bypassed the module-level default-deny one
        layer up — admit-by-omission — which this fail-closed default fixes.)
        """
        async with self._pool.acquire() as conn:
            existing = await conn.fetchval(
                """
                SELECT corpus_id FROM source_corpus
                WHERE user_id = $1 AND project_id = $2 AND name = $3 AND kind = $4
                """,
                user_id, project_id, name, kind,
            )
            if existing is not None:
                return existing
            return await conn.fetchval(
                """
                INSERT INTO source_corpus (project_id, user_id, name, kind, license, provenance_json)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING corpus_id
                """,
                project_id, user_id, name, kind, license,
                json.dumps(provenance_json or {}),
            )

    # ── chunk persistence (idempotent on (corpus_id, chunk_index)) ───────────
    async def _persist_chunks(
        self, *, corpus_id: UUID, project_id: UUID, chunks: Sequence[Chunk]
    ) -> int:
        """Insert chunks that do not yet exist for this corpus. ON CONFLICT
        (corpus_id, chunk_index) DO NOTHING makes a re-ingest of identical text a
        no-op (idempotent). Returns the number of rows actually inserted."""
        inserted = 0
        async with self._pool.acquire() as conn:
            for ch in chunks:
                status = await conn.execute(
                    """
                    INSERT INTO source_corpus_chunk
                      (corpus_id, project_id, chunk_index, content, content_sha256)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (corpus_id, chunk_index) DO NOTHING
                    """,
                    corpus_id, project_id, ch.index, ch.content, ch.sha256,
                )
                # asyncpg returns 'INSERT 0 1' on insert, 'INSERT 0 0' on conflict
                if status.endswith(" 1"):
                    inserted += 1
        return inserted

    async def _unembedded_chunks(self, *, corpus_id: UUID) -> list[StoredChunk]:
        """Chunks of a corpus that have no embedding yet (for incremental
        embed). Ordered by chunk_index for deterministic batching."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, corpus_id, chunk_index, content
                FROM source_corpus_chunk
                WHERE corpus_id = $1 AND embedding IS NULL
                ORDER BY chunk_index
                """,
                corpus_id,
            )
        return [
            StoredChunk(
                chunk_id=r["chunk_id"],
                corpus_id=r["corpus_id"],
                chunk_index=r["chunk_index"],
                content=r["content"],
                embedding=None,
                embedding_model_ref=None,
            )
            for r in rows
        ]

    async def _store_embedding(
        self, *, chunk_id: UUID, vector: list[float], model_ref: str
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE source_corpus_chunk
                SET embedding = $2, embedding_model_ref = $3, embedding_dim = $4,
                    updated_at = now()
                WHERE chunk_id = $1
                """,
                chunk_id, vector, model_ref, len(vector),
            )

    # ── public ingest: chunk → persist → embed (idempotent) ──────────────────
    async def ingest_corpus(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        name: str,
        kind: str,
        text: str,
        embed_fn: EmbedFn,
        model_ref: str,
        license: str = "unknown",
        provenance_json: dict | None = None,
        target_chars: int = DEFAULT_TARGET_CHARS,
        overlap_sentences: int = DEFAULT_OVERLAP_SENTENCES,
    ) -> IngestResult:
        """Ingest ``text`` as a corpus: upsert the corpus row, chunk the text,
        persist new chunks, and embed any chunk that lacks a vector via
        ``embed_fn`` (which reuses knowledge-service /internal/embed under the
        given ``model_ref`` — never a hardcoded model name).

        Idempotent end-to-end: re-ingesting the same text inserts zero new chunks
        and re-embeds zero chunks (already-embedded chunks are skipped). The
        resolving ``model_ref`` is stored with each vector (drift guard).

        ``license`` defaults to ``"unknown"`` (fail-closed, C17 WARN-1): an ingest
        that omits it produces a corpus the re-cook licensing gate REFUSES. Tag a
        genuinely public-domain / licensed source EXPLICITLY to make it re-cookable.

        ``provenance_json`` is recorded on the corpus row (only when the corpus is
        first created — a re-ingest keeps the original). Compose tags its ephemeral
        paste/file corpora here (``{"compose_ephemeral": true}``) so the reaper can
        garbage-collect them by TTL (D-COMPOSE-CONTEXT-CORPUS-SCOPE).
        """
        corpus_id = await self.upsert_corpus(
            user_id=user_id, project_id=project_id, name=name, kind=kind, license=license,
            provenance_json=provenance_json,
        )
        chunks = chunk_text(
            text, target_chars=target_chars, overlap_sentences=overlap_sentences
        )
        inserted = await self._persist_chunks(
            corpus_id=corpus_id, project_id=project_id, chunks=chunks
        )

        pending = await self._unembedded_chunks(corpus_id=corpus_id)
        embedded = 0
        if pending:
            vectors = await embed_fn([c.content for c in pending])
            if len(vectors) != len(pending):
                raise ValueError(
                    f"embed_fn returned {len(vectors)} vectors for "
                    f"{len(pending)} chunks (count mismatch)"
                )
            for chunk, vector in zip(pending, vectors):
                await self._store_embedding(
                    chunk_id=chunk.chunk_id, vector=list(vector), model_ref=model_ref
                )
                embedded += 1

        return IngestResult(
            corpus_id=corpus_id,
            chunks_total=len(chunks),
            chunks_inserted=inserted,
            chunks_embedded=embedded,
        )

    # ── search: load a project's embedded chunks + cosine top-k ──────────────
    async def load_embedded_chunks(
        self, *, project_id: UUID, corpus_id: UUID | None = None
    ) -> list[StoredChunk]:
        """Embedded chunks for a project (optionally one corpus), for search.

        Only rows WITH a vector are returned (un-embedded chunks can't be scored).
        Scoped to the project (Q3) — never crosses a USER/project boundary — PLUS
        the SHARED reference library (de-bias C2 T5): chunks whose ``project_id IS
        NULL`` are public-domain reference material readable by any project (e.g.
        the original work a fanfic re-cooks). The library is curated PD-only, so it
        crosses no private data.
        """
        async with self._pool.acquire() as conn:
            if corpus_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT chunk_id, corpus_id, chunk_index, content,
                           embedding, embedding_model_ref
                    FROM source_corpus_chunk
                    WHERE (project_id = $1 OR project_id IS NULL)
                      AND corpus_id = $2 AND embedding IS NOT NULL
                    ORDER BY corpus_id, chunk_index
                    """,
                    project_id, corpus_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT chunk_id, corpus_id, chunk_index, content,
                           embedding, embedding_model_ref
                    FROM source_corpus_chunk
                    WHERE (project_id = $1 OR project_id IS NULL)
                      AND embedding IS NOT NULL
                    ORDER BY corpus_id, chunk_index
                    """,
                    project_id,
                )
        return [
            StoredChunk(
                chunk_id=r["chunk_id"],
                corpus_id=r["corpus_id"],
                chunk_index=r["chunk_index"],
                content=r["content"],
                embedding=[float(x) for x in r["embedding"]] if r["embedding"] else None,
                embedding_model_ref=r["embedding_model_ref"],
            )
            for r in rows
        ]

    async def search(
        self,
        *,
        project_id: UUID,
        query_vector: Sequence[float],
        k: int,
        corpus_id: UUID | None = None,
    ) -> list[ScoredChunk]:
        """Top-``k`` chunks for a project by cosine similarity to
        ``query_vector``. In-process scoring over the project's embedded chunks
        (no pgvector). Empty project → ``[]`` (a valid state, not an error)."""
        candidates = await self.load_embedded_chunks(
            project_id=project_id, corpus_id=corpus_id
        )
        return top_k(query_vector, candidates, k=k)
