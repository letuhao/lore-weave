"""reference_source repository — LOOM T3.6 the author's per-Work reference shelf.

SECURITY (M5 isolation): every method takes `user_id` first and filters
`user_id = $1 AND project_id = $2`. References are composition-owned authoring
data; the embedding vector is stored as a plain `real[]` and the SEARCH ranks by
brute-force cosine IN APP CODE (a reference shelf is small — dozens to low-hundreds
of rows — so a kNN index is unnecessary; this avoids a pgvector dependency and the
fixed-dimension column it would force). DELETE is a hard delete (unlike canon_rule's
soft-archive — a reference has no critic-calibration history to preserve).

The `embedding` column is NEVER projected into a returned model (the vector stays on
the server); `_SELECT_COLS` is the attribution projection only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from loreweave_vecmath import cosine_similarity as _cosine

from app.db.models import ReferenceSource

# Attribution projection — the vector is deliberately excluded (stays server-side).
_SELECT_COLS = """
  id, user_id, project_id, title, author, source_url, content,
  embedding_model, embedding_dim, created_at
"""

# A Work uses ONE embedding model for all its references (set write-through on the
# first add) so the vectors share one space. Persisted in composition_work.settings.
REFERENCE_EMBED_MODEL_REF = "reference_embed_model_ref"
REFERENCE_EMBED_MODEL_SOURCE = "reference_embed_model_source"


def reference_embed_model(settings: dict[str, Any] | None) -> tuple[str, str] | None:
    """The Work's (model_source, model_ref) for reference embeddings, or None when
    unset. Defaults source to 'user_model' (the BYOK kind). Single source of truth
    for both the references router and the packer's gather_references lens."""
    s = settings or {}
    ref = s.get(REFERENCE_EMBED_MODEL_REF)
    if not ref:
        return None
    return (s.get(REFERENCE_EMBED_MODEL_SOURCE) or "user_model", str(ref))


def _row_to_ref(row: asyncpg.Record) -> ReferenceSource:
    return ReferenceSource.model_validate(dict(row))


# `_cosine` is the shared loreweave_vecmath.cosine_similarity (imported above,
# aliased to keep this module's existing call sites unchanged). D-COSINE-SDK-
# PROMOTE: this was the origin copy that motif_retrieve.py's own `_cosine`
# explicitly documented itself as a copy of — both now import the one shared
# implementation.


class ReferencesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        user_id: UUID,
        project_id: UUID,
        *,
        content: str,
        embedding: list[float],
        title: str = "",
        author: str = "",
        source_url: str = "",
        embedding_model: str = "",
        embedding_dim: int | None = None,
    ) -> ReferenceSource:
        query = f"""
        INSERT INTO reference_source
          (user_id, project_id, title, author, source_url, content,
           embedding, embedding_model, embedding_dim)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, user_id, project_id, title, author, source_url, content,
                embedding, embedding_model, embedding_dim,
            )
        return _row_to_ref(row)

    async def list(self, user_id: UUID, project_id: UUID) -> list[ReferenceSource]:
        """The Work's reference library (newest first) — the management list."""
        query = f"""
        SELECT {_SELECT_COLS} FROM reference_source
        WHERE user_id = $1 AND project_id = $2
        ORDER BY created_at DESC, id DESC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_ref(r) for r in rows]

    async def get(self, user_id: UUID, reference_id: UUID) -> ReferenceSource | None:
        query = f"SELECT {_SELECT_COLS} FROM reference_source WHERE user_id = $1 AND id = $2"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, reference_id)
        return _row_to_ref(row) if row else None

    async def delete(self, user_id: UUID, reference_id: UUID) -> bool:
        """Hard delete. Returns True if a row was removed (False if missing /
        cross-user — the router maps False → 404, no existence oracle)."""
        async with self._pool.acquire() as c:
            status = await c.execute(
                "DELETE FROM reference_source WHERE user_id = $1 AND id = $2",
                user_id, reference_id,
            )
        return status.rsplit(" ", 1)[-1] != "0"

    async def search(
        self, user_id: UUID, project_id: UUID, query_vector: list[float], *, limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Brute-force cosine top-K over the Work's references. Returns a list of
        attribution dicts each with a `score` (cosine, 0..1), highest first. Rows
        with a null/empty embedding are skipped (never a hit). Loads the vectors
        for the ranking pass, but the returned dicts carry only attribution + score
        (the vector stays on the server)."""
        sql = f"""
        SELECT {_SELECT_COLS}, embedding FROM reference_source
        WHERE user_id = $1 AND project_id = $2 AND embedding IS NOT NULL
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(sql, user_id, project_id)
        scored: list[tuple[float, asyncpg.Record]] = []
        for r in rows:
            vec = r["embedding"]
            if not vec:
                continue
            scored.append((_cosine(query_vector, list(vec)), r))
        scored.sort(key=lambda t: t[0], reverse=True)
        out: list[dict[str, Any]] = []
        for score, r in scored[: max(0, limit)]:
            ref = _row_to_ref(r)
            d = ref.model_dump(mode="json")
            d["score"] = score
            out.append(d)
        return out
