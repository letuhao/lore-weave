"""K17.9 — live `AsyncQueryRunner` implementation for the benchmark.

Wraps the same embedding + vector-search path that production Mode 3
uses (K12.2 embedding_client + K18.3 `find_passages_by_vector`) and
maps each returned `:Passage.source_id` back to the golden-set
`entity_id` for scoring.

The runner is async because it has to `await` the embedding round-
trip and the Cypher query. The sync `QueryRunner` Protocol in
`run_benchmark.py` stays unchanged so existing unit tests that use
an in-memory mock runner keep working — this module adds an
`AsyncQueryRunner` Protocol as a sibling interface.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.clients.embedding_client import EmbeddingClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    find_passages_by_vector,
)

from .run_benchmark import ScoredResult

__all__ = ["AsyncQueryRunner", "Mode3QueryRunner"]


class AsyncQueryRunner(Protocol):
    """Awaitable counterpart to `run_benchmark.QueryRunner`.

    Real-world runners have to await embedding + Neo4j I/O, so the
    live benchmark adapter keeps the Protocol async. The sync
    Protocol in `run_benchmark` stays for pure-unit-test callers
    that just return hard-coded `ScoredResult` lists.
    """

    async def run(self, query: str) -> Sequence[ScoredResult]: ...  # pragma: no cover


class Mode3QueryRunner:
    """Live runner: embed the query → search the vector index →
    map passage.source_id → entity_id → return top-K scored results.

    Reuses `find_passages_by_vector` directly instead of going
    through the full Mode 3 builder because the benchmark's goal is
    to isolate retrieval quality. Running `build_full_mode` would
    drag in L0/L1/glossary/facts/absences — noise for a pure
    recall@3 / MRR measurement against a fixture of known entities.
    """

    def __init__(
        self,
        session: CypherSession,
        embedding_client: EmbeddingClient,
        *,
        user_id: str,
        project_id: str,
        user_uuid: UUID,
        model_source: str,
        embedding_model: str,
        embedding_dim: int,
        limit: int = 10,
    ) -> None:
        if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
            raise ValueError(
                f"embedding_dim {embedding_dim} not in {SUPPORTED_PASSAGE_DIMS}"
            )
        self._session = session
        self._embedding_client = embedding_client
        self._user_id = user_id
        self._project_id = project_id
        self._user_uuid = user_uuid
        self._model_source = model_source
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim
        self._limit = limit

    async def run(self, query: str) -> Sequence[ScoredResult]:
        # 1. Embed the query using the same model that the fixture
        #    was loaded with — otherwise cross-model nonsense.
        result = await self._embedding_client.embed(
            user_id=self._user_uuid,
            model_source=self._model_source,
            model_ref=self._embedding_model,
            texts=[query],
        )
        if not result.embeddings:
            return []
        query_vector = result.embeddings[0]

        # 2. Vector-search against the passage index. `limit=10` is
        #    generous; the scorer only looks at top-3 but we hand it
        #    a longer list so MRR can still see hits at rank 4+ if
        #    the golden set has unusually noisy query → target
        #    mappings.
        hits = await find_passages_by_vector(
            self._session,
            user_id=self._user_id,
            project_id=self._project_id,
            query_vector=query_vector,
            dim=self._embedding_dim,
            embedding_model=self._embedding_model,
            limit=self._limit,
        )

        # 3. Map passage.source_id (which we set to entity_id at
        #    fixture load time) back to a `ScoredResult`. `raw_score`
        #    is the Neo4j cosine, same shape `BenchmarkRunner` needs.
        return [
            ScoredResult(entity_id=h.passage.source_id, score=h.raw_score)
            for h in hits
        ]
