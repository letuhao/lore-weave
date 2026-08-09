"""Graph maintenance queries — the sweepers' storage layer (plan T17).

Moved out of `app/jobs/`, where each sweeper carried its own Cypher. The queries were
already repo-shaped; only their address was wrong. Collecting them here is what makes
Phase 7 tractable: an engine swap has to port every query, and queries scattered through
job modules are the ones a swap misses.

The SCHEDULING stays in `app/jobs/` — retry policy, metrics, loop-until-zero, "do not run
concurrently with extraction". Those are operational decisions, not storage.

⚠️ **Two of these deliberately do NOT go through `run_write`, and both reasons are real:**
`invalidate_stale_quarantined_facts` accepts `user_id=None` for the admin global sweep,
which `run_write` cannot type — it calls `assert_user_id_param` directly instead, and its
Cypher handles the NULL branch explicitly. `count_nodes_by_label` interpolates a label
because Cypher cannot parameterise one; the label comes from a closed literal tuple in this
module, never from a caller.
"""

from __future__ import annotations

import logging

from app.db.neo4j_helpers import CypherSession, assert_user_id_param, run_write

logger = logging.getLogger(__name__)

__all__ = [
    "PROJECT_GRAPH_LABELS",
    "delete_project_nodes_by_label",
    "project_graph_stats",
    "RECONCILE_LABELS",
    "clear_embedding_model_tag",
    "reconcile_evidence_count_for_label",
    "COUNTABLE_LABELS",
    "count_nodes_by_label",
    "delete_orphan_extraction_sources",
    "invalidate_stale_quarantined_facts",
]


# ── orphan ExtractionSource sweep (D-K11.9-02) ───────────────────────

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
    """Delete `:ExtractionSource` nodes with zero incoming `EVIDENCED_BY` edges.

    `project_id=None` sweeps every source for the user; `limit=None` removes the cap and
    the caller should loop until a run returns zero.

    **Do NOT run concurrently with extraction.** The window is real: a source with no edges
    yet is indistinguishable from an orphan, so this can delete one a pending extraction
    transaction is about to link.
    """
    if not user_id:
        raise ValueError("user_id is required for orphan source cleanup")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be positive when set, got {limit}")

    result = await run_write(
        session, _ORPHAN_CLEANUP_CYPHER,
        user_id=user_id, project_id=project_id, limit=limit,
    )
    record = await result.single()
    # `RETURN count(*)` always produces a row, so None means driver/session corruption
    # rather than "nothing matched" — worth distinguishing, because the second is normal.
    if record is None:
        raise RuntimeError(
            "D-K11.9-02: delete_orphan_extraction_sources returned no row "
            "— driver or session anomaly"
        )
    deleted = int(record["deleted"])
    if deleted > 0:
        logger.info(
            "D-K11.9-02: deleted %d orphan ExtractionSource(s) user=%s project=%s",
            deleted, user_id, project_id,
        )
    return deleted


# ── quarantined-fact TTL sweep (K15.10) ──────────────────────────────

_QUARANTINE_CLEANUP_CYPHER = """
MATCH (f:Fact)
WHERE coalesce(f.pending_validation, false) = true
  AND f.valid_until IS NULL
  AND f.updated_at < datetime() - duration({hours: $ttl_hours})
  AND ($user_id IS NULL OR f.user_id = $user_id)
WITH f
LIMIT COALESCE($limit, 2147483647)
SET f.valid_until = datetime()
RETURN count(f) AS invalidated
"""


async def invalidate_stale_quarantined_facts(
    session: CypherSession,
    *,
    user_id: str | None = None,
    ttl_hours: int = 24,
    limit: int | None = None,
) -> int:
    """Soft-invalidate quarantined facts older than `ttl_hours`. Returns how many.

    `user_id=None` sweeps globally — admin cron only, never a per-request path.
    """
    if ttl_hours <= 0:
        raise ValueError(f"ttl_hours must be > 0, got {ttl_hours}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be positive when set, got {limit}")

    # NOT run_write: it types user_id as str, and this is the one caller that legitimately
    # passes None. The $user_id reference check still applies — the Cypher handles the NULL
    # branch explicitly via `($user_id IS NULL OR f.user_id = $user_id)`.
    assert_user_id_param(_QUARANTINE_CLEANUP_CYPHER)
    result = await session.run(
        _QUARANTINE_CLEANUP_CYPHER,
        user_id=user_id, ttl_hours=ttl_hours, limit=limit,
    )
    record = await result.single()
    return int(record["invalidated"]) if record else 0


# ── node counts for the project stats reconciler (K16.14) ────────────

# Closed set. The label is INTERPOLATED because Cypher cannot parameterise one, so this
# tuple is the injection barrier — a label must never arrive from a caller.
COUNTABLE_LABELS: tuple[str, ...] = ("Entity", "Fact", "Event")

_COUNT_BY_LABEL_CYPHER = (
    "MATCH (n:{label}) "
    "WHERE n.user_id = $user_id AND n.project_id = $project_id "
    "RETURN count(n) AS c"
)


async def count_nodes_by_label(
    session: CypherSession, *, user_id: str, project_id: str, label: str,
) -> int:
    """Count a project's nodes of one label. `label` MUST come from `COUNTABLE_LABELS`."""
    if label not in COUNTABLE_LABELS:
        raise ValueError(f"label must be one of {COUNTABLE_LABELS}, got {label!r}")
    result = await session.run(
        _COUNT_BY_LABEL_CYPHER.format(label=label),
        user_id=user_id, project_id=project_id,
    )
    record = await result.single()
    return int(record["c"]) if record else 0


# ── evidence-count reconciliation (K11.9) ────────────────────────────

# Closed set, same reason as COUNTABLE_LABELS: the label is interpolated because Cypher
# cannot parameterise one.
# EXACTLY the three that carry `evidence_count`. Relations are excluded on purpose — they
# track provenance differently. Order preserved from the original definition so any
# caller iterating it produces the same sequence of writes.
RECONCILE_LABELS: tuple[str, ...] = ("Entity", "Event", "Fact")

_RECONCILE_CYPHER_TEMPLATE = """
MATCH (n:{label})
WHERE n.user_id = $user_id
  AND ($project_id IS NULL OR n.project_id = $project_id)
OPTIONAL MATCH (n)-[r:EVIDENCED_BY]->(src:ExtractionSource)
  WHERE src.user_id = $user_id
WITH n, count(r) AS actual_count
WITH n, actual_count, coalesce(n.evidence_count, 0) AS cached
WHERE cached <> actual_count
WITH n, actual_count
LIMIT COALESCE($limit, 2147483647)
SET n.evidence_count = actual_count,
    n.updated_at = datetime()
RETURN count(*) AS fixed
"""

_RECONCILE_CYPHER: dict[str, str] = {
    label: _RECONCILE_CYPHER_TEMPLATE.format(label=label) for label in RECONCILE_LABELS
}


async def reconcile_evidence_count_for_label(
    session: CypherSession,
    *,
    label: str,
    user_id: str,
    project_id: str | None = None,
    limit: int | None = None,
) -> int:
    """Recount `EVIDENCED_BY` edges and repair a drifted `evidence_count`. Returns the
    number of nodes fixed.

    Drift is normal, not exceptional: `delete_source_cascade` is deliberately non-atomic
    across its three round-trips, so a mid-failure leaves a counter one too high. This is
    the sweeper that closes that window — which is also why a partial run is fine and
    `limit` lets the scheduler loop instead of holding one transaction over a 100k-node
    tenant.
    """
    if label not in RECONCILE_LABELS:
        raise ValueError(f"label must be one of {RECONCILE_LABELS}, got {label!r}")
    result = await run_write(
        session, _RECONCILE_CYPHER[label],
        user_id=user_id, project_id=project_id, limit=limit,
    )
    record = await result.single()
    # `RETURN count(*)` always produces a row; None is a driver anomaly, not "no drift".
    if record is None:
        raise RuntimeError(
            f"K11.9: reconcile for label {label!r} returned no row — driver or session anomaly"
        )
    return int(record["fixed"])


# ── model-deletion cleanup (admin) ───────────────────────────────────

_CLEAR_EMBEDDING_MODEL_CYPHER = """
MATCH (n)
WHERE n.user_id = $user_id AND n.embedding_model = $model_id
SET n.embedding_model = null
RETURN count(n) AS count
"""


async def clear_embedding_model_tag(
    session: CypherSession, *, user_id: str, model_id: str,
) -> int:
    """Strip a deleted embedding model's tag from every node that advertises it.

    The VECTORS stay — they are harmless data and re-embedding costs the user's own BYOK
    budget — but no node may advertise a model that no longer exists, or a later search
    routes to an index whose model is gone.
    """
    result = await run_write(
        session, _CLEAR_EMBEDDING_MODEL_CYPHER, user_id=user_id, model_id=model_id,
    )
    record = await result.single()
    return int(record["count"]) if record else 0


# ── project graph delete + stats (moved in plan T17) ─────────────────

# The labels a project delete removes. `:Passage` is DELIBERATELY absent — it holds chat-
# and glossary-sourced chunks extraction cannot rebuild, so a plain delete/rebuild (which
# does not change the vector space) must leave them alone; their vectors stay valid.
#
# A model CHANGE is the opposite case and must delete them too, via
# `passages.delete_all_passages_for_project`. Every passage is embedded in the OLD model's
# space, and leaving them behind makes them permanently unreachable from the new index —
# silent zero-recall. Both change-model paths DOCUMENTED themselves as already doing this
# and neither did; proven live on 2026-07-23, when a `:Passage` node was the only survivor
# of this exact loop.
PROJECT_GRAPH_LABELS: tuple[str, ...] = ("Entity", "Event", "Fact", "ExtractionSource")

_DELETE_BY_LABEL_CYPHER = (
    "MATCH (n:{label}) "
    "WHERE n.user_id = $user_id AND n.project_id = $project_id "
    "DETACH DELETE n "
    "RETURN count(n) AS deleted"
)


async def delete_project_nodes_by_label(
    session: CypherSession, *, user_id: str, project_id: str, label: str,
) -> int:
    """Delete one label's nodes for a project. `label` MUST come from
    `PROJECT_GRAPH_LABELS` — it is interpolated, so that tuple is the injection barrier.

    Unbatched `DETACH DELETE` (D-K11.9-01): fine at current scale, and the debt row says
    what to do when it is not.
    """
    if label not in PROJECT_GRAPH_LABELS:
        raise ValueError(f"label must be one of {PROJECT_GRAPH_LABELS}, got {label!r}")
    result = await session.run(
        _DELETE_BY_LABEL_CYPHER.format(label=label),
        user_id=user_id, project_id=project_id,
    )
    record = await result.single()
    return int(record["deleted"]) if record else 0


# One round trip for four counts. The UNION ALL shape looks odd but is deliberate: four
# separate `count()` queries would be four round trips for a stats card, and a single
# `MATCH (n) WHERE n:Entity OR n:Fact …` cannot use the label indexes.
_GRAPH_STATS_CYPHER = """
CALL {
  MATCH (e:Entity {user_id: $user_id, project_id: $project_id})
  RETURN count(e) AS entity_count, 0 AS fact_count,
         0 AS event_count, 0 AS passage_count
  UNION ALL
  MATCH (f:Fact {user_id: $user_id, project_id: $project_id})
  RETURN 0 AS entity_count, count(f) AS fact_count,
         0 AS event_count, 0 AS passage_count
  UNION ALL
  MATCH (ev:Event {user_id: $user_id, project_id: $project_id})
  RETURN 0 AS entity_count, 0 AS fact_count,
         count(ev) AS event_count, 0 AS passage_count
  UNION ALL
  MATCH (p:Passage {user_id: $user_id, project_id: $project_id})
  RETURN 0 AS entity_count, 0 AS fact_count,
         0 AS event_count, count(p) AS passage_count
}
RETURN sum(entity_count) AS entity_count, sum(fact_count) AS fact_count,
       sum(event_count) AS event_count, sum(passage_count) AS passage_count
"""


async def project_graph_stats(
    session: CypherSession, *, user_id: str, project_id: str,
) -> dict[str, int]:
    """Node counts for a project's stats card. Returns zeros for an empty graph — which is
    a legitimate state (a project with extraction enabled but nothing run yet), not an
    error, so the caller renders "Ready" rather than a failure."""
    result = await session.run(
        _GRAPH_STATS_CYPHER, user_id=user_id, project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return {"entity_count": 0, "fact_count": 0, "event_count": 0, "passage_count": 0}
    return {k: int(record[k] or 0) for k in
            ("entity_count", "fact_count", "event_count", "passage_count")}
