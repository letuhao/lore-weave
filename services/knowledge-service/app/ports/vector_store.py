"""The `VectorStore` port (plan T14).

Semantic search + embedding writes + the index lifecycle that serves them, expressed so a
caller cannot tell whether Neo4j or Postgres answered. Phase 3 replaces the Neo4j
implementation with pgvector for a reason the port has to survive: at 10k projects the
per-project index scheme reaches ~30 000 HNSW indexes and ~63 M passage vectors, and D2
wants **as-of-filtered** semantic search, which is impossible while vectors and validity
intervals live in different stores.

── WHY `upsert` TAKES A UNION AND NOT A COMMON SHAPE ────────────────────────────────────
The plan sketched `search · upsert · ensure_index · drop_index`. There are genuinely TWO
things with vectors here — `:Passage` nodes (18 fields, chunked, canon-flagged) and
`:Entity` nodes (an embedding written onto an existing node) — and a single `upsert(...)`
covering both would have to take the intersection of their parameters. That intersection
is `(id, embedding, dim, model)`, which silently drops `canon`, `chunk_index`,
`source_lang`, `content_hash` and the rest. A port that loses fields is worse than no port:
the adapter still needs them, so they come back as kwargs and the abstraction leaks on day
one. Instead `upsert` takes a typed record and the union carries every field.

── WHAT IS DELIBERATELY *NOT* HERE ──────────────────────────────────────────────────────
- **Reranking.** `find_entities_by_vector` returns `weighted_score = raw_score *
  anchor_score`. That weighting is domain policy; the port returns `raw_score` and the
  anchor value, and the caller decides. A backend that had to reproduce a scoring formula
  to be swappable would not be swappable.
- **Oversampling.** `oversample_factor` exists because Neo4j's index cannot filter by
  tenant, so the query over-fetches and filters after. That is an artefact of ONE backend —
  pgvector filters in the planner, which is the point of moving (T23). Exposing it would
  bake the current backend's weakness into the contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "EntityVectorRecord",
    "PassageVectorRecord",
    "VectorFilter",
    "VectorHit",
    "VectorRecord",
    "VectorScope",
    "VectorStore",
]

# Which family of vectors an operation addresses. Not a backend detail: an implementation
# may keep both in one table, in two, or in two databases.
VectorScope = Literal["passage", "entity"]


@dataclass(frozen=True)
class VectorFilter:
    """Scope narrowing applied BEFORE similarity, expressed in domain terms.

    `project_id=None` means "every project this user owns" — the multi-project context
    mode needs it, and it is not the same as an empty filter.

    Whether a backend can push these into the index or must apply them afterwards is its
    own business; Neo4j cannot and over-fetches, Postgres can. That difference must not
    reach this signature.
    """

    project_id: str | None = None
    embedding_model: str | None = None
    source_type: str | None = None
    include_drafts: bool = False
    include_archived: bool = False


@dataclass(frozen=True)
class VectorHit:
    """One result. `record_id` is the passage/entity id; `score` is raw cosine similarity.

    `attributes` carries the scope-specific payload the caller needs for ranking without
    a second round trip — `anchor_score` for entities, `is_hub`/`chapter_index` for
    passages. It is a plain mapping ON PURPOSE: a typed hit per scope would make every
    consumer branch on scope, and the alternative (returning the full node model) would
    put a backend's serialisation shape into the port.
    """

    record_id: str
    score: float
    scope: VectorScope
    attributes: dict = field(default_factory=dict)
    vector: list[float] | None = None


@dataclass(frozen=True)
class PassageVectorRecord:
    """A passage chunk and its embedding. Mirrors what the passage upsert already takes —
    the fields are load-bearing downstream (`canon` gates spoiler windows, `source_lang`
    routes translation, `content_hash` is the re-embed guard that stops a backfill paying
    a provider call per entity per run)."""

    user_id: str
    project_id: str | None
    source_type: str
    source_id: str
    chunk_index: int
    text: str
    embedding: list[float]
    embedding_dim: int
    embedding_model: str | None = None
    is_hub: bool = False
    chapter_index: int | None = None
    canon: bool = True
    block_index: int | None = None
    source_lang: str = "unknown"
    mixed: bool = False
    content_hash: str | None = None
    scope: VectorScope = "passage"


@dataclass(frozen=True)
class EntityVectorRecord:
    """An embedding written onto an entity that already exists. Unlike a passage this is
    never a create — the entity is authored or extracted elsewhere and only its vector is
    maintained here, which is why `upsert` reports whether the target was found."""

    user_id: str
    entity_id: str
    embedding: list[float]
    embedding_dim: int
    embedding_model: str
    embedding_version: int
    scope: VectorScope = "entity"
    # T25b (reopening T14) — the two fields that made `PgVectorStore.search(scope="entity")`
    # refuse. They are LIFECYCLE state, and a vector-only store genuinely does not hold them:
    # `project_id` scopes the search (the glossary FK is unique per (user, project), so an
    # unscoped entity search returns an arbitrary project's node — the same defect that put
    # every T27 lifecycle archive in the DLQ), and `archived` is what keeps a retired entity
    # out of retrieval.
    #
    # Carried on the RECORD rather than looked up at search time on purpose: a store that had
    # to join back to the graph to answer "is this archived" would be a store that cannot be
    # swapped, which is the entire point of the port. The writer knows both at upsert time.
    #
    # Defaults keep this additive: an existing caller that constructs the record positionally
    # or omits them still compiles, and `archived=False` is the safe reading of "not stated"
    # — a vector that forgot to say it was archived must not vanish from retrieval, it must
    # be visible and wrong in a way somebody notices.
    project_id: str | None = None
    archived: bool = False


VectorRecord = PassageVectorRecord | EntityVectorRecord


@runtime_checkable
class VectorStore(Protocol):
    """The port. Implementations: `adapters/neo4j_vector_store.py` (today),
    `adapters/pg_vector_store.py` (T23), `adapters/fake_vector_store.py` (tests)."""

    async def search(
        self,
        *,
        scope: VectorScope,
        user_id: str,
        embedding: list[float],
        dim: int,
        k: int = 10,
        filter: VectorFilter | None = None,
    ) -> list[VectorHit]:
        """Top-`k` by cosine similarity within the scope, highest first.

        `dim` is passed separately from `len(embedding)` because it selects the index
        family: a mismatch is a caller bug worth failing on, not something to infer.
        """
        ...

    async def upsert(self, record: VectorRecord) -> bool:
        """Write one record's vector. Returns False when the target did not exist (an
        entity that was deleted between embedding and write) — a miss is normal on a
        concurrent delete, so it is a return value rather than an exception."""
        ...

    async def ensure_index(
        self, *, project_id: str, embedding_model_uuid: str, embedding_dimension: int,
    ) -> dict[str, str]:
        """Idempotent create of the indexes serving one (project, model) pair. Returns
        `{level: index_name}`. Called lazily before the first write for that pair, and
        safe to call on every job start."""
        ...

    async def drop_index(self, *, name: str) -> None:
        """Idempotent drop. Implementations MUST validate the name — a backend where an
        index name is not parameterisable (Cypher) has no other injection barrier."""
        ...

    async def list_indexes(self) -> list[dict[str, str]]:
        """Every index this store owns, each with at least `name`. Feeds the prune-orphans
        admin path, which is why it must not silently include indexes the store does not
        own — the admin endpoint would then offer to drop someone else's."""
        ...
