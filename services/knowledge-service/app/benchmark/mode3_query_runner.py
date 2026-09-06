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
from app.ports.vector_store import VectorFilter
from app.domain.passage_contract import SUPPORTED_PASSAGE_DIMS

from .core import ScoredResult

__all__ = ["AsyncQueryRunner", "Mode3QueryRunner"]


class AsyncQueryRunner(Protocol):
    """Awaitable counterpart to `core.QueryRunner`.

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
        # T17 A11 — resolved lazily in `_search`, not here: the provider is async (it may have
        # to pick an adapter per scope) and a constructor cannot await. Holding the session too
        # keeps the harness's other repo reads working unchanged.
        self._vectors = None
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
        # T17 A11 — through `VectorStore`, not the Neo4j repo. This harness measures RETRIEVAL
        # QUALITY (MRR over a golden set), which is a property of the corpus and the embedding,
        # not of the store — so it must keep working when §3.1 finishes moving passages to
        # Postgres. Its two sibling benchmarks stay on the repo deliberately: they measure the
        # BACKEND (ANN recall, a per-engine corpus dump) and need `oversample_factor`, which the
        # port refuses to expose because it is one engine's weakness.
        if self._vectors is None:
            from app.adapters.vector_store_provider import get_vector_store

            self._vectors = await get_vector_store(self._session)
        hits = await self._vectors.search(
            scope="passage",
            user_id=self._user_id,
            embedding=query_vector,
            dim=self._embedding_dim,
            k=self._limit,
            filter=VectorFilter(project_id=self._project_id,
                                embedding_model=self._embedding_model),
        )

        # 3. Map passage.source_id (which we set to entity_id at
        #    fixture load time) back to a `ScoredResult`. `raw_score`
        #    is the Neo4j cosine, same shape `BenchmarkRunner` needs.
        # A BRACKET, not `.get` — the A9 rule. `PgVectorStore` omits a key by design when it
        # genuinely has no value, so a consumer that needs one must RAISE rather than silently
        # score every hit against a missing id. `source_id` is in `_PASSAGE_ATTRS` on both real
        # adapters and the fake; if that ever stops being true this harness must fail loudly,
        # not report a quietly empty MRR.
        return [
            ScoredResult(entity_id=h.attributes["source_id"], score=h.score)
            for h in hits
        ]
