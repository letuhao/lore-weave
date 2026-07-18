"""reference_source repository — LOOM T3.6 the author's per-Work reference shelf.

SCOPE RULE (package re-key, spec 25 §Repo/service layer): reads key on
`project_id` — access is decided BEFORE the repo, at the gate (E0 grant on the
row's `book_id`). Writes stamp `created_by` (a plain actor stamp — STORED,
never filtered on) and derive `book_id` from composition_work inside the
INSERT. References are composition-owned authoring data; the embedding vector
is stored as a plain `real[]` and the SEARCH ranks by brute-force cosine IN APP
CODE (a reference shelf is small — dozens to low-hundreds of rows — so a kNN
index is unnecessary; this avoids a pgvector dependency and the fixed-dimension
column it would force). DELETE is a hard delete (unlike canon_rule's
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
from app.db.repositories import ReferenceViolationError

# Attribution projection — the vector is deliberately excluded (stays server-side).
_SELECT_COLS = """
  id, created_by, project_id, title, author, source_url, content,
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


# Sentinel for update_metadata partial-update: distinguishes "field omitted" from
# "field set to '' " (title/author/source_url are NOT NULL DEFAULT '' — clearing one
# to empty is a legitimate edit, not the same as leaving it unchanged).
_UNSET: Any = object()


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
        project_id: UUID,
        *,
        created_by: UUID,
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
          (created_by, project_id, book_id, title, author, source_url, content,
           embedding, embedding_model, embedding_dim)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6, $7, $8, $9
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, created_by, project_id, title, author, source_url, content,
                embedding, embedding_model, embedding_dim,
            )
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_ref(row)

    async def list(self, project_id: UUID) -> list[ReferenceSource]:
        """The Work's reference library (newest first) — the management list."""
        query = f"""
        SELECT {_SELECT_COLS} FROM reference_source
        WHERE project_id = $1
        ORDER BY created_at DESC, id DESC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_ref(r) for r in rows]

    async def get(self, project_id: UUID, reference_id: UUID) -> ReferenceSource | None:
        query = f"SELECT {_SELECT_COLS} FROM reference_source WHERE project_id = $1 AND id = $2"
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, reference_id)
        return _row_to_ref(row) if row else None

    async def delete(self, project_id: UUID, reference_id: UUID) -> bool:
        """Hard delete, project-bound. Returns True if a row was removed (False if
        missing / another project's — the router maps False → 404, no existence
        oracle)."""
        async with self._pool.acquire() as c:
            status = await c.execute(
                "DELETE FROM reference_source WHERE project_id = $1 AND id = $2",
                project_id, reference_id,
            )
        return status.rsplit(" ", 1)[-1] != "0"

    async def update_metadata(
        self,
        project_id: UUID,
        reference_id: UUID,
        *,
        title: Any = _UNSET,
        author: Any = _UNSET,
        source_url: Any = _UNSET,
    ) -> ReferenceSource | None:
        """S-03: edit a reference's METADATA only (title/author/source_url) — NO
        embedding recompute (fixing a typo in an author's name is a cheap column
        write, not a full re-embed). Only provided fields change. Project-scoped
        (book scope is fixed at create; the row can't cross projects). Returns None
        when no row matches (id, project_id) — the router maps that to 404."""
        sets: list[str] = []
        args: list[Any] = []
        for col, val in (("title", title), ("author", author), ("source_url", source_url)):
            if val is not _UNSET:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if not sets:
            return await self.get(project_id, reference_id)  # no-op patch → current row
        args.append(reference_id)
        id_pos = len(args)
        args.append(project_id)
        pid_pos = len(args)
        query = f"""
        UPDATE reference_source SET {", ".join(sets)}
        WHERE id = ${id_pos} AND project_id = ${pid_pos}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *args)
        return _row_to_ref(row) if row else None

    async def update_content(
        self,
        project_id: UUID,
        reference_id: UUID,
        *,
        content: str,
        embedding: list[float],
        embedding_model: str,
        embedding_dim: int | None,
    ) -> ReferenceSource | None:
        """S-03: replace a reference's CONTENT and its recomputed embedding. The
        CALLER (service/router) runs the embed via provider-registry BEFORE calling
        this — the repo never embeds (provider-gateway invariant), exactly as the
        create route does. Project-scoped; None when no row matches → 404."""
        query = f"""
        UPDATE reference_source
        SET content = $1, embedding = $2, embedding_model = $3, embedding_dim = $4
        WHERE id = $5 AND project_id = $6
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, content, embedding, embedding_model, embedding_dim,
                reference_id, project_id,
            )
        return _row_to_ref(row) if row else None

    async def search(
        self, project_id: UUID, query_vector: list[float], *, limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Brute-force cosine top-K over the Work's references. Returns a list of
        attribution dicts each with a `score` (cosine, 0..1), highest first. Rows
        with a null/empty embedding are skipped (never a hit). Loads the vectors
        for the ranking pass, but the returned dicts carry only attribution + score
        (the vector stays on the server)."""
        sql = f"""
        SELECT {_SELECT_COLS}, embedding FROM reference_source
        WHERE project_id = $1 AND embedding IS NOT NULL
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(sql, project_id)
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
