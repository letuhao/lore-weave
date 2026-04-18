"""K18.3 — :Passage repository.

`:Passage` nodes hold raw chunked text (chapter chunks, L1 summary
chunks, long-bio chunks) with a per-dimension embedding vector. The
K18.3 L3 semantic selector queries them via `find_passages_by_vector`.

**Ingestion is deferred to a later commit.** This module only provides
the storage + query primitives; the producer side (fetch chapter text
from book-service, chunk, embed, upsert) lands separately. Without an
ingestion pipeline the graph has zero Passage nodes and L3 returns an
empty list — the rest of Mode 3 still works.

Multi-tenant safety: every function takes `user_id` and every Cypher
statement filters `WHERE p.user_id = $user_id`. The vector-search
path uses the same oversample-and-filter pattern as
`find_entities_by_vector` because Neo4j vector indexes are global.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write

__all__ = [
    "Passage",
    "PassageSearchHit",
    "SUPPORTED_PASSAGE_DIMS",
    "passage_canonical_id",
    "upsert_passage",
    "delete_passages_for_source",
    "find_passages_by_vector",
]

logger = logging.getLogger(__name__)

# Mirror the entity-vector index dims (KSA §3.4.B). New dims added
# here must also get a matching CREATE VECTOR INDEX in neo4j_schema.cypher.
SUPPORTED_PASSAGE_DIMS: tuple[int, ...] = (384, 1024, 1536, 3072)


class Passage(BaseModel):
    """Pydantic projection of a `:Passage` node.

    The embedding vector itself is NOT projected — it's potentially
    large (up to 3072 floats) and callers that need the vector have
    already embedded their own query to search with. Downstream
    consumers (the L3 selector) only use metadata + text for MMR
    and hub-penalty scoring.
    """

    id: str
    user_id: str
    project_id: str | None = None
    source_type: str
    source_id: str
    chunk_index: int
    text: str
    embedding_model: str | None = None
    is_hub: bool = False
    chapter_index: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PassageSearchHit(BaseModel):
    """Output of `find_passages_by_vector`.

    `raw_score` is the cosine similarity returned by the Neo4j vector
    index. The selector applies its own post-ranking (hub penalty,
    recency weight, MMR) — this repo only does the index call + the
    tenant-scope filter.
    """

    passage: Passage
    raw_score: float


def passage_canonical_id(
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    chunk_index: int,
) -> str:
    """Deterministic id for a passage chunk.

    Hash inputs are stable across re-runs so repeated ingestion of
    the same chapter chunk MERGEs the same node rather than spawning
    duplicates. The text itself is NOT in the hash so an edit to
    chapter text (e.g., typo fix) updates-in-place rather than
    forking a new node.
    """
    key = (
        f"v1:{user_id}:{project_id or 'global'}:"
        f"{source_type}:{source_id}:{chunk_index}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


_UPSERT_PASSAGE_CYPHER = """
MERGE (p:Passage {id: $id})
ON CREATE SET
  p.user_id = $user_id,
  p.project_id = $project_id,
  p.source_type = $source_type,
  p.source_id = $source_id,
  p.chunk_index = $chunk_index,
  p.text = $text,
  p.embedding_model = $embedding_model,
  p.is_hub = $is_hub,
  p.chapter_index = $chapter_index,
  p.created_at = datetime(),
  p.updated_at = datetime()
ON MATCH SET
  p.text = $text,
  p.embedding_model = $embedding_model,
  p.is_hub = $is_hub,
  p.chapter_index = $chapter_index,
  p.updated_at = datetime()
WITH p
CALL {
  WITH p
  WITH p WHERE $embedding_384 IS NOT NULL
  SET p.embedding_384 = $embedding_384
  RETURN p AS _p384
}
CALL {
  WITH p
  WITH p WHERE $embedding_1024 IS NOT NULL
  SET p.embedding_1024 = $embedding_1024
  RETURN p AS _p1024
}
CALL {
  WITH p
  WITH p WHERE $embedding_1536 IS NOT NULL
  SET p.embedding_1536 = $embedding_1536
  RETURN p AS _p1536
}
CALL {
  WITH p
  WITH p WHERE $embedding_3072 IS NOT NULL
  SET p.embedding_3072 = $embedding_3072
  RETURN p AS _p3072
}
WITH p WHERE p.user_id = $user_id
RETURN p
"""


async def upsert_passage(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    chunk_index: int,
    text: str,
    embedding: list[float],
    embedding_dim: int,
    embedding_model: str | None = None,
    is_hub: bool = False,
    chapter_index: int | None = None,
) -> Passage:
    """Idempotent MERGE of a `:Passage` with its per-dim embedding.

    Re-running with the same (user_id, project_id, source_type,
    source_id, chunk_index) tuple updates text + embedding in place.
    The embedding is written to the property that matches
    `embedding_dim`; the other dim properties stay untouched so
    mixed-model tenants (different projects on different embedding
    models) can coexist.
    """
    if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
        raise ValueError(
            f"unsupported embedding_dim {embedding_dim}; "
            f"must be one of {SUPPORTED_PASSAGE_DIMS}"
        )
    if len(embedding) != embedding_dim:
        raise ValueError(
            f"embedding length {len(embedding)} does not match dim {embedding_dim}"
        )
    if chunk_index < 0:
        raise ValueError(f"chunk_index must be >= 0, got {chunk_index}")
    if not text.strip():
        raise ValueError("text must be non-empty")

    canonical_id = passage_canonical_id(
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        chunk_index=chunk_index,
    )

    # Route the embedding to the matching property; the rest stay None.
    embedding_params = {f"embedding_{d}": None for d in SUPPORTED_PASSAGE_DIMS}
    embedding_params[f"embedding_{embedding_dim}"] = embedding

    result = await run_write(
        session,
        _UPSERT_PASSAGE_CYPHER,
        user_id=user_id,
        id=canonical_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        chunk_index=chunk_index,
        text=text,
        embedding_model=embedding_model,
        is_hub=is_hub,
        chapter_index=chapter_index,
        **embedding_params,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(f"upsert_passage returned no row for id={canonical_id!r}")
    return _node_to_passage(record["p"])


_DELETE_BY_SOURCE_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.source_type = $source_type
  AND p.source_id = $source_id
WITH p, p.id AS id
DETACH DELETE p
RETURN count(id) AS deleted
"""


async def delete_passages_for_source(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
) -> int:
    """Delete all `:Passage` nodes for a given source (e.g. a chapter
    that was re-ingested with different chunking)."""
    result = await run_write(
        session,
        _DELETE_BY_SOURCE_CYPHER,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
    )
    record = await result.single()
    return int(record["deleted"]) if record else 0


_FIND_BY_VECTOR_CYPHER = """
CALL db.index.vector.queryNodes($index_name, $oversample_limit, $query_vector)
YIELD node, score
WITH node, score
WHERE node.user_id = $user_id
  AND ($project_id IS NULL OR node.project_id = $project_id)
  AND ($embedding_model IS NULL OR node.embedding_model = $embedding_model)
RETURN node AS p, score AS raw_score
ORDER BY raw_score DESC
LIMIT $limit
"""


async def find_passages_by_vector(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    query_vector: list[float],
    dim: int,
    embedding_model: str | None = None,
    limit: int = 40,
    oversample_factor: int = 10,
) -> list[PassageSearchHit]:
    """Dim-routed semantic search over `:Passage` nodes.

    Vector indexes are global in Neo4j — we oversample by 10× then
    post-filter on tenant scope. The selector (K18.3) applies its
    own MMR + hub-penalty ranking on top of `raw_score`, so this
    repo returns straight cosine similarity without any weighting.
    """
    if dim not in SUPPORTED_PASSAGE_DIMS:
        raise ValueError(
            f"unsupported vector dim {dim}; "
            f"must be one of {SUPPORTED_PASSAGE_DIMS}"
        )
    if len(query_vector) != dim:
        raise ValueError(
            f"query_vector length {len(query_vector)} does not match dim {dim}"
        )
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    if oversample_factor < 1:
        raise ValueError(f"oversample_factor must be >= 1, got {oversample_factor}")

    index_name = f"passage_embeddings_{dim}"
    result = await run_read(
        session,
        _FIND_BY_VECTOR_CYPHER,
        user_id=user_id,
        index_name=index_name,
        oversample_limit=limit * oversample_factor,
        query_vector=query_vector,
        project_id=project_id,
        embedding_model=embedding_model,
        limit=limit,
    )
    hits: list[PassageSearchHit] = []
    async for record in result:
        hits.append(
            PassageSearchHit(
                passage=_node_to_passage(record["p"]),
                raw_score=float(record["raw_score"]),
            )
        )
    return hits


def _node_to_passage(node: Any) -> Passage:
    if hasattr(node, "items"):
        data = dict(node.items())
    else:
        data = dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    # Strip embedding vectors — they're not in the Pydantic model and
    # keeping them blows the response size up for large dims.
    for k in [f"embedding_{d}" for d in SUPPORTED_PASSAGE_DIMS]:
        data.pop(k, None)
    return Passage.model_validate(data)
