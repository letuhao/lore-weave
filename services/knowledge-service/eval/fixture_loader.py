"""K17.9 — golden-set fixture loader.

Takes a parsed `GoldenSet` and materialises each entity as a tagged
`:Passage` node in Neo4j so the vector-search path can be benchmarked
end-to-end. Tagging uses:

  - source_type = "benchmark_entity"   (never collides with real
                                        extraction sources)
  - source_id   = entity["id"]         (e.g. "ent-001")

**Indexed text = `f"{name}. {summary}"`** (review-impl catch, HIGH).
Queries in the golden set come in two bands: "easy" queries name the
entity directly ("Who is Kaelen Voss?") and "hard" queries paraphrase
("Which alchemist serves the Solenne family?"). If we embedded only
the summary, easy-band queries would rely on the model semantically
bridging proper nouns to occupation phrases — exactly what the
benchmark is trying to MEASURE, not assume. Concatenating name +
summary lets the embedding carry both name-lookup and paraphrase-
lookup signal, matching ContextHub's L-CH-01 methodology.

The loader is idempotent — re-running overwrites the passage in
place because `passage_canonical_id` hashes on (user, project,
source_type, source_id, chunk_index) so the MERGE hits the same
node. That means a fresh embedding run replaces any stale vector
from a previous model, which is the behaviour we want.

Partial-failure note: each upsert is its own write-transaction.
If the embedder fails on entity 7 of 10, entities 0–6 are left in
the graph. Re-running the loader is safe and cheap, so we accept
partial state rather than adding transactional wrapping that would
make the loader harder to retry.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import upsert_passage

from .run_benchmark import GoldenSet

__all__ = ["BENCHMARK_SOURCE_TYPE", "load_golden_set_as_passages"]

logger = logging.getLogger(__name__)


# Source-type tag that distinguishes benchmark passages from real
# extraction output in the same project. A real Mode-3 query against
# this project would pick up these passages too — that's fine for the
# benchmark project (no real chapters should be loaded there) but
# callers should NEVER use a real user's project as the benchmark
# target; K17.9 assumes a dedicated benchmark project.
BENCHMARK_SOURCE_TYPE = "benchmark_entity"


def _build_indexed_text(name: str, summary: str) -> str:
    """Concatenate name + summary so the embedding carries BOTH
    name-lookup signal (for easy-band queries like "Who is Kaelen
    Voss?") AND paraphrase-lookup signal (for hard-band queries like
    "Which alchemist serves Solenne?"). Matches ContextHub L-CH-01.

    If either field is blank, returns whichever is non-blank. If
    both are blank, returns an empty string — caller skips the entity.
    """
    name = name.strip()
    summary = summary.strip()
    if name and summary:
        # Period + space keeps the two as logically separate sentences
        # so the encoder doesn't merge them into one weird token run.
        return f"{name}. {summary}" if not summary.startswith(name) else summary
    return name or summary


async def load_golden_set_as_passages(
    session: CypherSession,
    embedding_client: EmbeddingClient,
    golden: GoldenSet,
    *,
    user_id: str,
    project_id: str,
    user_uuid: UUID,
    model_source: str,
    embedding_model: str,
    embedding_dim: int,
) -> int:
    """Embed each golden-set entity's summary and upsert as a tagged
    `:Passage` node.

    Returns the count of passages successfully written. Logs (but does
    NOT raise) per-entity embedding failures — a flaky provider
    shouldn't abort the whole fixture load, the harness will catch
    low-coverage at score time anyway.
    """
    count = 0
    for entity in golden.entities:
        entity_id = entity["id"]
        name = (entity.get("name") or "").strip()
        summary = (entity.get("summary") or "").strip()
        indexed_text = _build_indexed_text(name, summary)
        if not indexed_text:
            logger.warning(
                "K17.9 fixture: entity %s has no name AND no summary — skipping",
                entity_id,
            )
            continue

        try:
            result = await embedding_client.embed(
                user_id=user_uuid,
                model_source=model_source,
                model_ref=embedding_model,
                texts=[indexed_text],
            )
        except EmbeddingError as exc:
            logger.warning(
                "K17.9 fixture: embed failed for %s (%s) — skipping",
                entity_id, exc,
            )
            continue

        if not result.embeddings:
            logger.warning(
                "K17.9 fixture: empty embedding for %s — skipping",
                entity_id,
            )
            continue

        await upsert_passage(
            session,
            user_id=user_id,
            project_id=project_id,
            source_type=BENCHMARK_SOURCE_TYPE,
            source_id=entity_id,
            chunk_index=0,
            text=indexed_text,
            embedding=result.embeddings[0],
            embedding_dim=embedding_dim,
            embedding_model=embedding_model,
            is_hub=False,
            chapter_index=None,
        )
        count += 1

    logger.info(
        "K17.9 fixture: loaded %d/%d entities into project %s (model=%s)",
        count, len(golden.entities), project_id, embedding_model,
    )
    return count
