"""K18.3 — :Passage repository.

`:Passage` nodes hold raw chunked text (chapter chunks, L1 summary
chunks, long-bio chunks) with a per-dimension embedding vector. The
K18.3 L3 semantic selector queries them via `find_passages_by_vector`.
Ingestion lives in `app/extraction/passage_ingester.py`, driven by
the K14 event consumer (D-K18.3-01, Cycle 1a).

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
    "KNOWN_SOURCE_TYPES",
    "passage_canonical_id",
    "upsert_passage",
    "delete_passages_for_source",
    "find_passages_by_vector",
    "count_passages_by_source_type",
]

# C8 (D-K19e-γa-01) — closed set of recognised source_type values on
# :Passage nodes. Single source of truth consumed by:
#   - drawers.py router (Literal validation + response padding)
#   - count_passages_by_source_type (key padding so every type appears
#     even at 0 count)
# Add a member here first before writing a new source_type producer.
KNOWN_SOURCE_TYPES: frozenset[str] = frozenset({"chapter", "chat", "glossary"})

logger = logging.getLogger(__name__)

# Mirror the entity-vector index dims (KSA §3.4.B). New dims added
# here must also get a matching CREATE VECTOR INDEX in neo4j_schema.cypher.
SUPPORTED_PASSAGE_DIMS: tuple[int, ...] = (384, 1024, 1536, 3072)


class Passage(BaseModel):
    """Pydantic projection of a `:Passage` node.

    The embedding vector is NOT on this model — it's potentially large
    (up to 3072 floats) and would bleed into every serialisation of a
    passage node. When a caller needs vectors for a search-time decision
    (P-K18.3-02 MMR cosine), they come back on `PassageSearchHit.vector`
    instead, which is the transient per-query tuple.
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

    `vector` is the stored embedding, populated only when the caller
    asks for it via `include_vectors=True` (P-K18.3-02). It stays off
    `Passage` itself because `Passage` is the persistent projection;
    the vector is a per-search artifact, not part of the node's
    serialisation contract.
    """

    passage: Passage
    raw_score: float
    vector: list[float] | None = None


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


# The `{embed_prop}` placeholder is f-string-substituted at call time
# with the dim-specific property name (e.g. "embedding_1024"). Dim is
# validated against SUPPORTED_PASSAGE_DIMS before substitution so
# this is injection-safe — the set of possible values is closed.
#
# An earlier version used per-dim CALL subqueries with WHERE filters
# on null params; Neo4j's CROSS APPLY semantics dropped the outer
# row whenever any subquery filter evaluated false, causing the
# function to raise "returned no row" despite the matching SET
# running. Dynamic Cypher sidesteps that entirely.
_UPSERT_PASSAGE_CYPHER_TEMPLATE = """
MERGE (p:Passage {{id: $id}})
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
  p.{embed_prop} = $embedding,
  p.created_at = datetime(),
  p.updated_at = datetime()
ON MATCH SET
  p.text = $text,
  p.embedding_model = $embedding_model,
  p.is_hub = $is_hub,
  p.chapter_index = $chapter_index,
  p.{embed_prop} = $embedding,
  p.updated_at = datetime()
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

    # Dim was validated above against the closed set SUPPORTED_PASSAGE_DIMS,
    # so this f-string substitution has no injection surface.
    cypher = _UPSERT_PASSAGE_CYPHER_TEMPLATE.format(
        embed_prop=f"embedding_{embedding_dim}",
    )

    result = await run_write(
        session,
        cypher,
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
        embedding=embedding,
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


# The `{vector_projection}` placeholder is f-string-substituted at call
# time with either an empty string (default, no vector projection) or
# `, node.embedding_{dim} AS vector` (P-K18.3-02). `dim` is validated
# against SUPPORTED_PASSAGE_DIMS before substitution, same injection-safe
# closed-set pattern as `_UPSERT_PASSAGE_CYPHER_TEMPLATE`.
_FIND_BY_VECTOR_CYPHER_TEMPLATE = """
CALL db.index.vector.queryNodes($index_name, $oversample_limit, $query_vector)
YIELD node, score
WITH node, score
WHERE node.user_id = $user_id
  AND ($project_id IS NULL OR node.project_id = $project_id)
  AND ($embedding_model IS NULL OR node.embedding_model = $embedding_model)
  AND ($source_type IS NULL OR node.source_type = $source_type)
RETURN node AS p, score AS raw_score{vector_projection}
ORDER BY raw_score DESC
LIMIT $limit
"""


_COUNT_BY_SOURCE_TYPE_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.project_id = $project_id
  AND ($embedding_model IS NULL OR p.embedding_model = $embedding_model)
RETURN p.source_type AS source_type, count(*) AS n
"""


async def count_passages_by_source_type(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    embedding_model: str | None = None,
) -> dict[str, int]:
    """C8 (D-K19e-γa-01) — facet counts keyed by source_type.

    Returns a dict with EVERY key in ``KNOWN_SOURCE_TYPES`` (padded to
    0 when absent) so the FE can render a stable pill layout regardless
    of which types the project actually contains yet.

    ``embedding_model`` filter: pass the project's current model to
    count only passages the vector search would reach. Pass None to
    count everything (useful for the "not indexed yet" state where
    coverage across models is the interesting signal).

    Unknown source_type values from the DB (data drift — a new code
    path added a source_type before this constant was updated) are
    dropped from the result WITH a logged warning.
    """
    result = await run_read(
        session,
        _COUNT_BY_SOURCE_TYPE_CYPHER,
        user_id=user_id,
        project_id=project_id,
        embedding_model=embedding_model,
    )
    counts: dict[str, int] = {st: 0 for st in KNOWN_SOURCE_TYPES}
    async for rec in result:
        st = rec["source_type"]
        n = int(rec["n"])
        if st in KNOWN_SOURCE_TYPES:
            counts[st] = n
        else:
            logger.warning(
                "count_passages_by_source_type: unknown source_type=%r "
                "(count=%d) in project %s — extend KNOWN_SOURCE_TYPES",
                st, n, project_id,
            )
    return counts


async def find_passages_by_vector(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    query_vector: list[float],
    dim: int,
    embedding_model: str | None = None,
    source_type: str | None = None,
    limit: int = 40,
    oversample_factor: int = 10,
    include_vectors: bool = False,
) -> list[PassageSearchHit]:
    """Dim-routed semantic search over `:Passage` nodes.

    Vector indexes are global in Neo4j — we oversample by 10× then
    post-filter on tenant scope. The selector (K18.3) applies its
    own MMR + hub-penalty ranking on top of `raw_score`, so this
    repo returns straight cosine similarity without any weighting.

    `include_vectors=True` (P-K18.3-02) projects the stored embedding
    back onto each `PassageSearchHit.vector` so the MMR redundancy
    term can use real cosine distance between hits instead of the
    text-only Jaccard fallback. Costs one list[float] per hit in the
    response payload — default stays False so the passage selector
    (the only current caller) opts in explicitly.
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

    # dim was validated above against the closed set SUPPORTED_PASSAGE_DIMS,
    # so the f-string substitution has no injection surface.
    vector_projection = (
        f", node.embedding_{dim} AS vector" if include_vectors else ""
    )
    cypher = _FIND_BY_VECTOR_CYPHER_TEMPLATE.format(
        vector_projection=vector_projection,
    )

    index_name = f"passage_embeddings_{dim}"
    result = await run_read(
        session,
        cypher,
        user_id=user_id,
        index_name=index_name,
        oversample_limit=limit * oversample_factor,
        query_vector=query_vector,
        project_id=project_id,
        embedding_model=embedding_model,
        source_type=source_type,
        limit=limit,
    )
    hits: list[PassageSearchHit] = []
    async for record in result:
        vector_raw = record["vector"] if include_vectors else None
        vector = [float(x) for x in vector_raw] if vector_raw is not None else None
        hits.append(
            PassageSearchHit(
                passage=_node_to_passage(record["p"]),
                raw_score=float(record["raw_score"]),
                vector=vector,
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
