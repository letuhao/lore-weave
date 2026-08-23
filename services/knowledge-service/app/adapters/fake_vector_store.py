"""In-memory `VectorStore` for tests (plan T14).

This fake is about to carry the ~561 tests that currently skip without a live Neo4j (T20).
That makes drift between it and the real adapter the single most dangerous thing in this
package: 561 tests passing against a fake that has quietly diverged is worse than 561 tests
skipping, because skipping is at least visible. Two things follow.

**It computes REAL cosine similarity.** A fake that returned insertion order would let
every ranking bug through — and ranking is what a vector store is for. The arithmetic is
eight lines; there is no excuse for stubbing it.

**It enforces the contract's rules, it does not just satisfy the signatures.** Tenant
scoping, the dim/index family split, the `False`-on-missing-entity return, index-name
validation on drop. A fake that skips these teaches tests that the rules do not exist, and
they then fail only in production. QC-2 diffs this against the Neo4j adapter on a live
stack, which is the backstop — this is the part that has to hold between those runs.
"""

from __future__ import annotations

import logging
import math

from app.db.graph_repos.vector_indexes import parse_summary_index_name, summary_index_name
from app.ports.vector_store import (
    EntityVectorRecord,
    PassageVectorRecord,
    VectorFilter,
    VectorHit,
    VectorRecord,
    VectorScope,
)

logger = logging.getLogger(__name__)

__all__ = ["FakeVectorStore"]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, 0.0 for a zero vector. Not a stub: ranking IS the behaviour
    under test, so a fake that faked the ordering would pass every test the real thing
    would fail."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class FakeVectorStore:
    """Records are kept in insertion order so a test can assert that ordering comes from
    SIMILARITY and not from arrival — the failure a dict-backed fake hides."""

    def __init__(self) -> None:
        # (scope, key) -> record, mirroring each backend's natural identity: a passage is
        # keyed by (user, source, chunk) because re-embedding the same chunk must REPLACE
        # rather than duplicate; an entity by its own id.
        self._records: dict[tuple[str, str], VectorRecord] = {}
        self._indexes: dict[str, dict[str, str]] = {}
        # Entities the caller declared to exist. Empty means "accept every entity write";
        # a test that wants to exercise the write-after-delete race registers explicitly.
        self._known_entities: set[str] | None = None

    # ── test affordances (not part of the port) ──────────────────────────────

    def register_entities(self, entity_ids: list[str]) -> None:
        """Declare which entity ids exist, so `upsert` can return False for the rest.
        Without this the fake would accept every entity write and no test could reach the
        deleted-between-embedding-and-write path the port documents."""
        self._known_entities = set(entity_ids)

    def record_count(self, scope: VectorScope | None = None) -> int:
        if scope is None:
            return len(self._records)
        return sum(1 for (s, _) in self._records if s == scope)

    # ── the port ─────────────────────────────────────────────────────────────

    async def search(
        self,
        *,
        scope: VectorScope,
        user_id: str,
        embedding: list[float],
        dim: int,
        k: int = 10,
        filter: VectorFilter | None = None,
        include_vectors: bool = False,
    ) -> list[VectorHit]:
        f = filter or VectorFilter()
        hits: list[VectorHit] = []

        for (rec_scope, key), rec in self._records.items():
            if rec_scope != scope or rec.user_id != user_id:
                continue
            # Dim routes to an index family in every real backend: a 384-dim query must
            # not match a 1024-dim record. Skipping this in the fake would let a
            # model-change bug pass every test and fail on the first real search.
            if rec.embedding_dim != dim:
                continue
            if f.embedding_model is not None and rec.embedding_model != f.embedding_model:
                continue

            if isinstance(rec, PassageVectorRecord):
                if f.project_id is not None and rec.project_id != f.project_id:
                    continue
                if f.source_type is not None and rec.source_type != f.source_type:
                    continue
                if not f.include_drafts and rec.canon is False:
                    continue
                attributes = {
                    "text": rec.text,
                    "source_type": rec.source_type,
                    "source_id": rec.source_id,
                    "chunk_index": rec.chunk_index,
                    "is_hub": rec.is_hub,
                    "chapter_index": rec.chapter_index,
                    "canon": rec.canon,
                    "source_lang": rec.source_lang,
                    # T24b — the drawer read needs both; the real adapters return them,
                    # so a fake that omitted them would let a consumer test pass against
                    # a hit shape no backend produces.
                    "project_id": rec.project_id,
                    "created_at": getattr(rec, "created_at", None),
                    "block_index": getattr(rec, "block_index", None),
                }
            else:
                attributes = {"anchor_score": None}

            hits.append(VectorHit(
                record_id=key,
                score=_cosine(embedding, rec.embedding),
                scope=scope,
                attributes=attributes,
                # Honoured rather than ignored: `include_vectors=False` returning a vector
                # anyway would let a caller depend on a payload the real adapters do not
                # send unless asked, and the bug would surface only in production.
                vector=list(rec.embedding) if include_vectors else None,
            ))

        # Descending score; ties keep insertion order (Python's sort is stable), which is
        # the only ordering a caller can reason about when two vectors are equidistant.
        hits.sort(key=lambda h: h.score, reverse=True)
        out = hits[:k]
        logger.debug(
            "vector search: backend=fake scope=%s dim=%d k=%d candidates=%d hits=%d",
            scope, dim, k, len(hits), len(out),
        )
        return out

    async def upsert(self, record: VectorRecord) -> bool:
        if isinstance(record, PassageVectorRecord):
            key = f"{record.user_id}:{record.source_type}:{record.source_id}:{record.chunk_index}"
            self._records[("passage", key)] = record
            return True
        if isinstance(record, EntityVectorRecord):
            if self._known_entities is not None and record.entity_id not in self._known_entities:
                # The entity was deleted between embedding and write. The port says this
                # is a return value, not an exception — a concurrent delete is normal.
                logger.debug("vector upsert: backend=fake entity absent id=%s", record.entity_id)
                return False
            self._records[("entity", record.entity_id)] = record
            return True
        raise TypeError(f"unknown vector record type {type(record).__name__}")

    async def ensure_index(
        self, *, project_id: str, embedding_model_uuid: str, embedding_dimension: int,
    ) -> dict[str, str]:
        if embedding_dimension <= 0:
            raise ValueError(f"invalid embedding_dimension {embedding_dimension!r}")
        # Reuses the REAL name builder rather than inventing a fake scheme: the names are
        # parsed elsewhere (the prune-orphans admin path), so a fake with its own format
        # would make those tests agree with nothing.
        names = {
            level: summary_index_name(project_id, embedding_model_uuid, level)
            for level in ("chapter", "part", "book")
        }
        for level, name in names.items():
            self._indexes[name] = {
                "name": name, "level": level,
                "project_id": project_id.replace("-", "").lower(),
                "embedding_model_uuid": embedding_model_uuid.replace("-", "").lower(),
            }
        return names

    async def drop_index(self, *, name: str) -> None:
        if parse_summary_index_name(name) is None:
            # Same refusal the real adapter makes. A fake that dropped anything would let
            # a test prove the admin endpoint is safe when it is not.
            raise ValueError(f"refusing to DROP non-summary index {name!r}")
        self._indexes.pop(name, None)  # idempotent, like DROP … IF EXISTS

    async def list_indexes(self) -> list[dict[str, str]]:
        return list(self._indexes.values())
