"""motif retrieval — the planner's select-candidates core (R1.4 / W3 implements).

The signature is FROZEN in F0 so W2 (planner) builds against it concurrently and
mocks retrieve() until W3 lands. W3's impl: SQL pre-filter (genre ∩ + status='active'
+ the read predicate + language) BEFORE loading vectors (audit data-R1), then
brute-force cosine top-K in app code (reference_source precedent), then the
match_reason breakdown. ONE platform embedding model for all vectors (B-1).

RECONCILE D4 (NULL-embedding tolerance — W3 must honor): seeds insert embedding=NULL
and the platform embed may be down at boot, so a candidate row may have a NULL
embedding. W3 SKIPs such a row (and queues a lazy back-fill keyed on
embedded_summary_hash) — it must NEVER 0.0-rank a NULL-embedding row as a real miss.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.models import MotifCandidate


class MotifRetriever:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def retrieve(
        self, caller_id: UUID, *, book_id: UUID, project_id: UUID,
        genre_tags: list[str], language: str,
        beat_role: str | None, tension: int | None,
        prev_effects: list[str] | None = None, limit: int = 10,
    ) -> list[MotifCandidate]:
        """Tier-merged, SQL-pre-filtered, cosine-ranked motif candidates for a
        chapter's beat. Returns up to `limit` MotifCandidate (motif + score +
        match_reason={tension,genre,precond,cosine}), highest score first. W3 impl."""
        raise NotImplementedError("W3 implements motif retrieval")
