"""D-K11.9-02 — orphan `:ExtractionSource` cleanup.

`delete_source_cascade` (K11.8) intentionally runs three non-atomic
round-trips: (1) delete provenance edges, (2) delete zero-evidence
nodes, (3) delete the source itself. If a process crashes between
step 2 and step 3 (or between 1 and 3), the graph is left with an
`:ExtractionSource` that still has some edges removed but the node
itself persists — an "orphan" source.

K11.9's evidence-count reconciler fixes cached counter drift but
leaves orphan sources in place. This job is the sweep that cleans
them up.

**What qualifies as an orphan.** A source is orphaned if it has
zero incoming `EVIDENCED_BY` edges. The K11.8 cascade only deletes
the source after all its edges are gone, so any source with an
edge is by definition alive.

**Cross-label caveat — same as K11.9.** Do not run concurrently
with extraction. Between `MERGE (target)-[e:EVIDENCED_BY]` and the
counter increment there's a transaction-local window where the
target has zero edges on the wire while the extraction transaction
is still open. The orphan sweeper would delete the source; the
extraction commit would then complete with dangling edges pointing
at a deleted node.

**Transactional semantics.** Single-statement `DETACH DELETE`, so
a crash midway rolls back — either the source + remaining edges
are deleted, or nothing. Deletion is idempotent by nature: a
second call against the same orphan set returns 0.

Reference: K11.8 `delete_source_cascade` (the partial-failure
origin), K11.9 reconciler (sibling), KSA §3.6.
"""

from __future__ import annotations

import logging

from app.db.neo4j_helpers import CypherSession, run_write

__all__ = ["delete_orphan_extraction_sources"]

logger = logging.getLogger(__name__)


# Cypher: find :ExtractionSource nodes for the user with zero
# incoming EVIDENCED_BY edges. OPTIONAL MATCH yields null when no
# edge exists; count(r) on null returns 0. LIMIT is applied before
# DETACH DELETE so a bounded call fixes at most $limit sources.
#
# `$user_id` is always present (K11.4 assert_user_id_param); project
# narrowing is optional and reuses the `$project_id IS NULL OR ...`
# pattern from the reconciler.
_ORPHAN_CLEANUP_CYPHER = """
MATCH (s:ExtractionSource)
WHERE s.user_id = $user_id
  AND ($project_id IS NULL OR s.project_id = $project_id)
OPTIONAL MATCH (n)-[r:EVIDENCED_BY]->(s)
  WHERE n.user_id = $user_id
WITH s, count(r) AS edge_count
WHERE edge_count = 0
WITH s
LIMIT COALESCE($limit, 2147483647)
DETACH DELETE s
RETURN count(*) AS deleted
"""


async def delete_orphan_extraction_sources(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
    limit: int | None = None,
) -> int:
    """Delete `:ExtractionSource` nodes with zero incoming EVIDENCED_BY
    edges.

    Args:
        session: K11.4 CypherSession (multi-tenant guarded).
        user_id: tenant scope. Required; this job is always per-user.
        project_id: optional narrowing. `None` sweeps all sources for
            the user.
        limit: max orphans deleted per call. `None` removes the cap;
            the scheduler should loop until a call returns zero when
            running against large tenants.

    Returns:
        Number of orphan sources deleted on this run.

    Do NOT run concurrently with extraction — the transaction-local
    race described in the module docstring can delete a source that
    a pending extraction transaction is about to link edges to.
    """
    if not user_id:
        raise ValueError("user_id is required for orphan source cleanup")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be positive when set, got {limit}")

    result = await run_write(
        session,
        _ORPHAN_CLEANUP_CYPHER,
        user_id=user_id,
        project_id=project_id,
        limit=limit,
    )
    record = await result.single()
    # Same anomaly-guard as K11.9 reconciler — RETURN count(*) always
    # produces a row; None means driver/session corruption.
    if record is None:
        raise RuntimeError(
            "D-K11.9-02: delete_orphan_extraction_sources returned no row "
            "— driver or session anomaly"
        )
    deleted = int(record["deleted"])
    if deleted > 0:
        logger.info(
            "D-K11.9-02: deleted %d orphan ExtractionSource(s) "
            "user=%s project=%s",
            deleted, user_id, project_id,
        )
    return deleted
