"""Q4b-feed — worker-ai run-sample write.

worker-ai is the ONLY place an extraction run's `run_id`, its extracted
`items`, and the chapter `source_text` coexist (the live persist-pass2 path
writes only post-merge, run-unattributable Neo4j; it never populates
extraction_leaves). So for projects opted into raw retention
(`save_raw_extraction`), worker-ai persists one `extraction_run_samples` row
per SUCCEEDED chapter — the run-attributable feed learning-service's online
LLM judge fetches by `run_id`.

Plan: docs/plans/2026-06-01-q4b-feed-extraction-run-samples.md §2.2 / §4-B2.

worker-ai shares knowledge-service's Postgres (same pattern as
`outbox_emit.py`), so the INSERT runs directly on the worker's pool.

REDACT-MINIMIZED projection: only the fields the judge renders
(`format_items_for_judge`) are stored — name/kind (entity),
subject/predicate/object/polarity (relation), summary/participants (event).
Confidence, canonical ids, offsets, evidence are dropped. `fact` is excluded
(the online judge has no fact category).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _Executor(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...


def project_items(candidates: Any) -> dict[str, list[dict]]:
    """Map `Pass2Candidates` to the minimal judge-shape projection.

    Categories mirror the online judge's `_CATEGORIES`
    (entity / relation / event). `fact` is intentionally omitted.
    """
    return {
        "entity": [
            {"name": e.name, "kind": e.kind}
            for e in getattr(candidates, "entities", [])
        ],
        "relation": [
            {
                "subject": r.subject,
                "predicate": r.predicate,
                "object": r.object,
                "polarity": r.polarity,
            }
            for r in getattr(candidates, "relations", [])
        ],
        "event": [
            {"summary": ev.summary, "participants": list(ev.participants)}
            for ev in getattr(candidates, "events", [])
        ],
    }


async def persist_run_sample(
    executor: _Executor,
    *,
    run_id: str,
    job: Any,
    book_id: Any,
    config_hash: str | None,
    candidates: Any,
    source_text: str,
) -> None:
    """INSERT one extraction_run_sample. Idempotent on `run_id`
    (ON CONFLICT DO NOTHING — run_id is fresh per chapter; a conflict
    only happens on a re-emit race, first write wins)."""
    items = project_items(candidates)
    await executor.execute(
        """
        INSERT INTO extraction_run_samples
          (run_id, user_id, project_id, book_id, config_hash,
           items_jsonb, source_text)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        ON CONFLICT (run_id) DO NOTHING
        """,
        uuid.UUID(str(run_id)),
        job.user_id,
        job.project_id,
        uuid.UUID(str(book_id)) if book_id else None,
        config_hash,
        json.dumps(items),
        source_text,
    )


async def persist_run_sample_best_effort(
    executor: _Executor,
    *,
    run_id: str,
    job: Any,
    book_id: Any,
    config_hash: str | None,
    candidates: Any,
    source_text: str,
) -> None:
    """Best-effort wrapper — never raises.

    A lost sample only drops a (droppable) online-judging opportunity; it must
    NEVER turn an extraction success into a worker failure (the chapter's real
    work already persisted to Neo4j + the cursor already advanced)."""
    try:
        await persist_run_sample(
            executor, run_id=run_id, job=job, book_id=book_id,
            config_hash=config_hash, candidates=candidates,
            source_text=source_text,
        )
    except Exception:
        logger.warning(
            "Q4b-feed: failed to persist extraction_run_sample for run %s "
            "(non-fatal — the online judge just won't see this run)",
            run_id, exc_info=True,
        )


__all__ = ["project_items", "persist_run_sample", "persist_run_sample_best_effort"]
