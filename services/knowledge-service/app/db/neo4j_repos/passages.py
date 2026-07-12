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
import re
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
    "delete_all_passages_for_project",
    "find_passages_by_vector",
    "find_passages_by_fulltext",
    "PASSAGE_CJK_FT_INDEX",
    "lucene_escape",
    "count_passages_by_source_type",
    "set_source_lang_for_source",
    "get_source_ingest_state",
    "get_chapter_index_for_source",
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
    # D-RAWSEARCH-CANON-WIRING — true once the passage's source is author-published
    # (the `chapter.published` ingest path); false for on-demand draft indexing.
    # Defaults true so legacy nodes (written before this flag, all canon) and any
    # node missing the property read as canon — no backfill needed.
    canon: bool = True
    # P3-C — chapter_blocks.block_index where this chunk's content starts, so
    # a semantic hit can jump-to-source precisely (reader scrolls to ?block=N).
    # None for chunks ingested before P3-C or from the canon/revision path.
    block_index: int | None = None
    # KG-ML M1 (DD1) — ISO-639-1 language of the source text this passage was
    # ingested from (the chapter's `original_language`, or a translation's
    # target language for dual-indexed vi passages). "unknown" for legacy nodes
    # written before this tag + backfilled by source_lang backfill. Dormant
    # until M4 reads it for language-aware ranking; "mixed" + `mixed=true` when
    # detect_primary_language is ambiguous.
    source_lang: str = "unknown"
    mixed: bool = False
    # KG-ML M1 (C10) — sha256 of the full source text at ingest time. Lets the
    # ingest path skip the (delete + re-embed + re-bill) cycle when a republish
    # carries identical text. None for legacy nodes (treated as a cache miss →
    # ingest proceeds, same as before).
    content_hash: str | None = None
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
    source_lang: str = "",
    canon: bool = True,
) -> str:
    """Deterministic id for a passage chunk.

    Hash inputs are stable across re-runs so repeated ingestion of
    the same chapter chunk MERGEs the same node rather than spawning
    duplicates. The text itself is NOT in the hash so an edit to
    chapter text (e.g., typo fix) updates-in-place rather than
    forking a new node.

    KG-ML M2 (DD1): `source_lang` participates so a chapter's translated
    (vi) passages are DISTINCT nodes from its source (zh) passages even
    though they share `source_id=chapter_id` (kept clean so a hit maps
    back to the real chapter). The segment is appended ONLY when non-empty
    so every pre-M2 passage id (chat/glossary/benchmark + untagged chapter)
    stays byte-identical — a language-tagged chapter re-ingest forks a new
    id, and the delete-then-upsert step reaps the old one (no orphan).

    D-R20 (P-3, keep-both): `canon` participates so a chapter's PUBLISHED
    (canon) passages and a NEWER DRAFT's passages are DISTINCT nodes that
    coexist side by side — indexing a draft on a published chapter no longer
    collides ids with (and clobbers) the canon set. Mirroring the source_lang
    trick, the `draft:` segment is appended ONLY for canon=False, so every
    published/canon id stays byte-identical to the pre-P-3 scheme (zero re-key
    churn). Legacy draft nodes (written pre-P-3 with no segment) are reaped by
    the canon-scoped delete-then-upsert (matched by property, not id).
    """
    lang_seg = f"{source_lang}:" if source_lang else ""
    canon_seg = "" if canon else "draft:"
    key = (
        f"v1:{user_id}:{project_id or 'global'}:"
        f"{source_type}:{source_id}:{lang_seg}{canon_seg}{chunk_index}"
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
  p.canon = $canon,
  p.block_index = $block_index,
  p.source_lang = $source_lang,
  p.mixed = $mixed,
  p.content_hash = $content_hash,
  p.{embed_prop} = $embedding,
  p.created_at = datetime(),
  p.updated_at = datetime()
ON MATCH SET
  p.text = $text,
  p.embedding_model = $embedding_model,
  p.is_hub = $is_hub,
  p.chapter_index = $chapter_index,
  p.canon = $canon,
  p.block_index = $block_index,
  p.source_lang = $source_lang,
  p.mixed = $mixed,
  p.content_hash = $content_hash,
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
    canon: bool = True,
    block_index: int | None = None,
    source_lang: str = "unknown",
    mixed: bool = False,
    content_hash: str | None = None,
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
        # KG-ML M2 — language participates so vi/zh chunks of the same chapter
        # are distinct nodes ("unknown" stays out of the id for back-compat).
        source_lang=source_lang if source_lang and source_lang != "unknown" else "",
        # D-R20 (P-3) — canon vs draft chunks of the same chapter are distinct
        # nodes so a draft index keeps the published canon set (canon id unchanged).
        canon=canon,
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
        canon=canon,
        block_index=block_index,
        source_lang=source_lang,
        mixed=mixed,
        content_hash=content_hash,
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
  AND ($source_lang IS NULL OR coalesce(p.source_lang, 'unknown') = $source_lang)
  AND ($canon IS NULL OR coalesce(p.canon, true) = $canon)
WITH p, p.id AS id
DETACH DELETE p
RETURN count(id) AS deleted
"""


_DELETE_ALL_FOR_PROJECT_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id AND p.project_id = $project_id
WITH p, p.id AS id
DETACH DELETE p
RETURN count(id) AS deleted
"""


async def delete_all_passages_for_project(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
) -> int:
    """D-R27 (erasure) — DETACH DELETE every `:Passage` node of one (user, project). Tenant-scoped
    on BOTH keys, so it can only reach the caller's own project's semantic index (the diary's chapter
    + chat passages). Returns the count deleted."""
    result = await run_write(
        session,
        _DELETE_ALL_FOR_PROJECT_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    return int(record["deleted"]) if record else 0


async def delete_passages_for_source(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    source_lang: str | None = None,
    canon: bool | None = None,
) -> int:
    """Delete `:Passage` nodes for a given source (e.g. a chapter re-ingested
    with different chunking).

    KG-ML M2 (DD1): `source_lang` scopes the delete to ONE language so
    re-ingesting a chapter's vi translation never wipes its zh source passages
    (and vice-versa). None = all languages (back-compat: the chapter-delete /
    chapter.deleted path drops every language of a removed chapter).

    D-R20 (P-3, keep-both): `canon` scopes the delete to ONE bucket. The ingester's
    pre-write reap passes `canon=False` on a DRAFT index so it never wipes the
    published canon passages (keep-both), and `canon=None` on a PUBLISH so the new
    canon supersedes any ahead-of-canon draft. None = both buckets (back-compat:
    the chapter-delete / kg_excluded retract drops every bucket of a chapter).
    Legacy null-canon nodes coalesce to canon=True so a canon-scoped reap still
    matches them.
    """
    result = await run_write(
        session,
        _DELETE_BY_SOURCE_CYPHER,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        source_lang=source_lang,
        canon=canon,
    )
    record = await result.single()
    return int(record["deleted"]) if record else 0


_SET_SOURCE_LANG_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.source_type = $source_type
  AND p.source_id = $source_id
SET p.source_lang = $source_lang,
    p.mixed = $mixed,
    p.updated_at = datetime()
RETURN count(p) AS tagged
"""


async def set_source_lang_for_source(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    source_lang: str,
    mixed: bool = False,
) -> int:
    """KG-ML M1 (DD1) — tag-only `source_lang` backfill for one source.

    Sets `source_lang`/`mixed` on every existing `:Passage` of a source
    WITHOUT re-embedding (pure property write) — used by the one-shot
    backfill that stamps legacy zh passages at embedding-model-set time.
    Returns the count of passages tagged.
    """
    result = await run_write(
        session,
        _SET_SOURCE_LANG_CYPHER,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        source_lang=source_lang,
        mixed=mixed,
    )
    record = await result.single()
    return int(record["tagged"]) if record else 0


_SET_CANON_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.source_type = $source_type
  AND p.source_id = $source_id
SET p.canon = $canon,
    p.updated_at = datetime()
RETURN count(p) AS updated
"""


async def set_canon_for_source(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    canon: bool,
) -> int:
    """WS-0.8 — flip the `canon` flag on every existing :Passage of one source, WITHOUT
    re-embedding (a pure property write).

    Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.7/§3.8.

    Needed because publishing and INDEXING are now independent. When a chapter is
    UNPUBLISHED, it stays in the knowledge graph (its index request survives — §3.8 /
    acceptance #9), but it is no longer canonical. Deleting its passages would destroy
    the user's index; leaving them `canon=True` would let unpublished prose keep
    surfacing in `surface=canon` reads. Demoting them is the only option that honours
    both invariants.

    Returns the count of passages updated.
    """
    result = await run_write(
        session,
        _SET_CANON_CYPHER,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        canon=canon,
    )
    record = await result.single()
    return int(record["updated"]) if record else 0


_GET_SOURCE_STATE_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.source_type = $source_type
  AND p.source_id = $source_id
  AND ($source_lang IS NULL OR coalesce(p.source_lang, 'unknown') = $source_lang)
  AND ($canon IS NULL OR coalesce(p.canon, true) = $canon)
  AND p.content_hash IS NOT NULL
RETURN p.content_hash AS content_hash,
       coalesce(p.canon, true) AS canon,
       p.chapter_index AS chapter_index,
       p.embedding_model AS embedding_model
LIMIT 1
"""


_GET_CHAPTER_INDEX_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.project_id = $project_id
  AND p.source_type = 'chapter'
  AND p.source_id = $chapter_id
  AND p.chapter_index IS NOT NULL
RETURN p.chapter_index AS chapter_index
LIMIT 1
"""


async def get_chapter_index_for_source(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    chapter_id: str,
) -> int | None:
    """M1b — resolve the ordinal `chapter_index` of a chapter from any of its
    ingested `:Passage` nodes (they all share `source_id=chapter_id` + the same
    `chapter_index`; see the upsert cypher). Used by the working-scope boost to
    turn the editor's open `chapter_id` (a UUID) into the integer position the
    passage ranker scores against.

    Returns None when the chapter has no ingested passages yet (never extracted /
    not published) or the id is stale/foreign — the caller then simply skips the
    boost (degrade-to-neutral, never an error). Owner + project scoped so one
    user's open chapter can't resolve against another tenant's passages.
    """
    result = await run_read(
        session,
        _GET_CHAPTER_INDEX_CYPHER,
        user_id=user_id,
        project_id=project_id,
        chapter_id=chapter_id,
    )
    record = await result.single()
    if record is None or record["chapter_index"] is None:
        return None
    return int(record["chapter_index"])


async def get_source_ingest_state(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
    source_lang: str | None = None,
    canon: bool | None = None,
) -> dict | None:
    """KG-ML M1 (C10) — read the cached ingest state for a source's passages.

    Returns `{content_hash, canon, chapter_index, embedding_model}` from any
    existing passage of this source (they share these), or None when none exist /
    legacy nodes carry no hash. The ingest path skips the re-embed ONLY when the
    fresh text hash AND `canon` AND `chapter_index` AND `embedding_model` all
    match — so a draft→publish canon flip, a chapter reorder, OR an embedding-model
    change (same text, different model/dim — the model-set path does NOT delete
    `:Passage` nodes, only graph nodes) still re-ingests correctly rather than
    being silently skipped with stale-dimension vectors.

    D-R20 (P-3, keep-both): `canon` scopes the read to ONE bucket so the canon and
    draft passage sets have INDEPENDENT skip-gates. Without it, a `LIMIT 1` read
    over a chapter that carries both buckets would nondeterministically return
    either bucket's hash — a draft re-index could false-miss against the canon
    node's hash (wasteful re-embed) once keep-both lets the two coexist. None =
    any bucket (back-compat for pre-P-3 single-bucket callers).
    """
    result = await run_read(
        session,
        _GET_SOURCE_STATE_CYPHER,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        source_lang=source_lang,
        canon=canon,
    )
    record = await result.single()
    if record is None or not record["content_hash"]:
        return None
    ci = record["chapter_index"]
    em = record["embedding_model"]
    return {
        "content_hash": str(record["content_hash"]),
        "canon": bool(record["canon"]),
        "chapter_index": int(ci) if ci is not None else None,
        "embedding_model": str(em) if em is not None else None,
    }


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
  AND ($include_drafts OR coalesce(node.canon, true) = true)
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
    include_drafts: bool = False,
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

    `include_drafts` (D-RAWSEARCH-CANON-WIRING) controls the canon gate:
    default False returns only canon passages (`coalesce(canon, true) = true`,
    so legacy null-canon nodes count as canon); True returns canon + draft
    (the owner-only `surface=all` path). The caller owns the owner check.
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
        include_drafts=include_drafts,
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


# KG-ML M6 (D12) — the CJK full-text index name (mirrors neo4j_schema.cypher).
PASSAGE_CJK_FT_INDEX = "passage_text_cjk_ft"

# Lucene query-syntax special characters. The `cjk` analyzer tokenizes the query
# text, but the surrounding Lucene query PARSER still interprets these — an
# unescaped one in a user query (e.g. a stray `?` or `:`) is a parse error or a
# wildcard, not a literal. We escape them so a raw keyword query is matched
# literally (the analyzer then bi-grams the CJK runs).
_LUCENE_SPECIALS = r'+-&|!(){}[]^"~*?:\/'
_LUCENE_ESCAPE_RE = re.compile("([" + re.escape(_LUCENE_SPECIALS) + "])")


def lucene_escape(query: str) -> str:
    """Escape Lucene query-syntax specials so a raw keyword is matched literally.

    `&&`/`||` are covered char-by-char (each `&`/`|` is escaped). Returns a
    trimmed, escaped string; empty when the input is blank."""
    return _LUCENE_ESCAPE_RE.sub(r"\\\1", str(query or "").strip())


_FIND_BY_FULLTEXT_CYPHER = """
CALL db.index.fulltext.queryNodes($index_name, $q, {limit: $oversample_limit})
YIELD node, score
WITH node, score
WHERE node.user_id = $user_id
  AND ($project_id IS NULL OR node.project_id = $project_id)
  AND ($source_type IS NULL OR node.source_type = $source_type)
  AND ($source_lang IS NULL OR coalesce(node.source_lang, 'unknown') = $source_lang)
  AND ($include_drafts OR coalesce(node.canon, true) = true)
RETURN node AS p, score AS raw_score
ORDER BY raw_score DESC
LIMIT $limit
"""


async def find_passages_by_fulltext(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    query: str,
    source_type: str | None = None,
    source_lang: str | None = None,
    limit: int = 40,
    oversample_factor: int = 10,
    include_drafts: bool = False,
) -> list[PassageSearchHit]:
    """KG-ML M6 (D12) — CJK-tokenized lexical search over `:Passage` text.

    Queries the `cjk`-analyzed full-text index (built-in bi-gram tokenizer), so a
    short Chinese/Japanese/Korean keyword (the case pg_trgm fails on) recalls the
    right passages. Full-text indexes are global → oversample then post-filter on
    tenant scope + canon, identical to `find_passages_by_vector`. `raw_score` is
    the Lucene score (the RRF fusion only uses rank, so the absolute scale doesn't
    matter). A blank query (or one that escapes to empty) returns []. Best-effort
    at the call site — the retriever treats any failure as a degraded lexical leg.
    """
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    if oversample_factor < 1:
        raise ValueError(f"oversample_factor must be >= 1, got {oversample_factor}")
    q = lucene_escape(query)
    if not q:
        return []
    result = await run_read(
        session,
        _FIND_BY_FULLTEXT_CYPHER,
        index_name=PASSAGE_CJK_FT_INDEX,
        q=q,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_lang=source_lang,
        include_drafts=include_drafts,
        oversample_limit=limit * oversample_factor,
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
