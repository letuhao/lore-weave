"""Neo4j implementation of the `VectorStore` port (plan T14).

Every method delegates to the existing `app/db/neo4j_repos` functions. The plan called for
the adapter to be "existing code lifted byte-for-byte"; delegation is the strictest reading
of that — copying the Cypher would create a second place to fix a tenant filter, which is
the exact failure `neo4j_repos` and its `run_read`/`run_write` guards exist to prevent.

What this file DOES own is the translation between the port's vocabulary and the repos':

  - the two search flavours collapse to one `search(scope=…)`,
  - `weighted_score` is dropped and `anchor_score` returned raw, so the caller keeps the
    ranking policy instead of inheriting this backend's formula,
  - `oversample_factor` is supplied here and never surfaces on the port, because
    over-fetch-then-filter is a workaround for Neo4j's index being unable to filter by
    tenant — pgvector filters in the planner (T23) and would have to accept a meaningless
    parameter if the port carried it.
"""

from __future__ import annotations

import logging
import time

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import find_entities_by_vector, set_entity_embedding
from app.db.neo4j_repos.passages import find_passages_by_vector, upsert_passage
from app.db.neo4j_repos.vector_indexes import (
    drop_summary_index,
    ensure_summary_indexes,
    list_summary_vector_indexes,
)
from app.ports.vector_store import (
    EntityVectorRecord,
    PassageVectorRecord,
    VectorFilter,
    VectorHit,
    VectorRecord,
    VectorScope,
)

logger = logging.getLogger(__name__)

__all__ = ["Neo4jVectorStore"]

# Neo4j's vector index cannot filter by tenant, so a search over-fetches and discards
# out-of-scope rows afterwards. 10x is what the repos already use; it lives here rather
# than on the port because it is this backend's compensation, not a domain knob.
_OVERSAMPLE_FACTOR = 10


class Neo4jVectorStore:
    """Holds a session rather than taking one per call: the port's callers should not have
    to know that this backend HAS sessions. The pgvector adapter will hold a pool the same
    way, and the fake holds a dict."""

    def __init__(self, session: CypherSession) -> None:
        self._session = session

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
        f = filter or VectorFilter()
        started = time.perf_counter()

        if scope == "passage":
            hits = await find_passages_by_vector(
                self._session,
                user_id=user_id,
                project_id=f.project_id,
                query_vector=embedding,
                dim=dim,
                embedding_model=f.embedding_model,
                source_type=f.source_type,
                limit=k,
                oversample_factor=_OVERSAMPLE_FACTOR,
                include_drafts=f.include_drafts,
            )
            out = [
                VectorHit(
                    record_id=str(h.passage.id),
                    score=float(h.raw_score),
                    scope="passage",
                    attributes={
                        "text": h.passage.text,
                        "source_type": h.passage.source_type,
                        "source_id": h.passage.source_id,
                        "chunk_index": h.passage.chunk_index,
                        "is_hub": getattr(h.passage, "is_hub", False),
                        "chapter_index": getattr(h.passage, "chapter_index", None),
                        "canon": getattr(h.passage, "canon", True),
                        "source_lang": getattr(h.passage, "source_lang", "unknown"),
                    },
                    vector=h.vector,
                )
                for h in hits
            ]
        elif scope == "entity":
            hits = await find_entities_by_vector(
                self._session,
                user_id=user_id,
                project_id=f.project_id,
                query_vector=embedding,
                dim=dim,
                embedding_model=f.embedding_model,
                limit=k,
                include_archived=f.include_archived,
                oversample_factor=_OVERSAMPLE_FACTOR,
            )
            out = [
                VectorHit(
                    record_id=str(h.entity.id),
                    score=float(h.raw_score),
                    scope="entity",
                    # anchor_score raw, NOT weighted_score. The caller multiplies if it
                    # wants two-layer retrieval; a port that returned only the product
                    # would make every backend reimplement this formula to be swappable.
                    attributes={
                        "name": h.entity.name,
                        "kind": getattr(h.entity, "kind", None),
                        "anchor_score": getattr(h.entity, "anchor_score", None),
                        "glossary_entity_id": getattr(h.entity, "glossary_entity_id", None),
                    },
                )
                for h in hits
            ]
        else:
            raise ValueError(f"unknown vector scope {scope!r}")

        logger.debug(
            "vector search: backend=neo4j scope=%s dim=%d k=%d filters=%d hits=%d elapsed_ms=%d",
            scope, dim, k,
            sum(1 for v in (f.project_id, f.embedding_model, f.source_type) if v is not None),
            len(out), int((time.perf_counter() - started) * 1000),
        )
        return out

    async def upsert(self, record: VectorRecord) -> bool:
        started = time.perf_counter()
        if isinstance(record, PassageVectorRecord):
            await upsert_passage(
                self._session,
                user_id=record.user_id,
                project_id=record.project_id,
                source_type=record.source_type,
                source_id=record.source_id,
                chunk_index=record.chunk_index,
                text=record.text,
                embedding=record.embedding,
                embedding_dim=record.embedding_dim,
                embedding_model=record.embedding_model,
                is_hub=record.is_hub,
                chapter_index=record.chapter_index,
                canon=record.canon,
                block_index=record.block_index,
                source_lang=record.source_lang,
                mixed=record.mixed,
                content_hash=record.content_hash,
            )
            written = True
        elif isinstance(record, EntityVectorRecord):
            # Returns False when the entity is gone — deleted between embedding and write.
            written = await set_entity_embedding(
                self._session,
                user_id=record.user_id,
                entity_id=record.entity_id,
                embedding=record.embedding,
                embedding_dim=record.embedding_dim,
                embedding_model=record.embedding_model,
                embedding_version=record.embedding_version,
            )
        else:
            raise TypeError(f"unknown vector record type {type(record).__name__}")

        logger.debug(
            "vector upsert: backend=neo4j scope=%s dim=%d written=%s elapsed_ms=%d",
            record.scope, record.embedding_dim, written,
            int((time.perf_counter() - started) * 1000),
        )
        return written

    async def ensure_index(
        self, *, project_id: str, embedding_model_uuid: str, embedding_dimension: int,
    ) -> dict[str, str]:
        names = await ensure_summary_indexes(
            self._session, project_id, embedding_model_uuid, embedding_dimension
        )
        logger.debug(
            "vector ensure_index: backend=neo4j project=%s dim=%d indexes=%d",
            project_id, embedding_dimension, len(names),
        )
        return names

    async def drop_index(self, *, name: str) -> None:
        # The name check lives in `drop_summary_index`: Cypher cannot parameterise an index
        # name, so validating it IS the injection barrier, and it must not be bypassable by
        # coming through the port instead of the repo.
        await drop_summary_index(self._session, name)
        logger.debug("vector drop_index: backend=neo4j name=%s", name)

    async def list_indexes(self) -> list[dict[str, str]]:
        return await list_summary_vector_indexes(self._session)
