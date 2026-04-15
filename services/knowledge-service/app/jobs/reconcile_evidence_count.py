"""K11.9 — evidence_count drift reconciler.

Offline job that verifies the cached `evidence_count` property on
`:Entity|:Event|:Fact` nodes matches the actual count of outgoing
`EVIDENCED_BY` edges, and corrects any drift in place.

Per KSA §3.6 and 101_DATA_RE_ENGINEERING_PLAN.md §3.6, every
`add_evidence` / `remove_evidence_for_source` call is supposed to
atomically update the parent counter. K11.8 is the runtime primitive
that makes this true; K11.9 is the offline safety net that catches
the cases where it isn't:

  - a caller bypassing `add_evidence` to write an edge directly
  - a partial-operation cascade crashing between edge delete and
    counter decrement (K11.8 delete_source_cascade is intentionally
    non-atomic across its three round-trips — see its docstring)
  - a glossary sync path that creates edges via raw Cypher for
    bulk import
  - a test fixture bypassing the repo layer
  - a future bug in the write path

Run cadence: daily at low traffic per KSA §3.6. A normal run should
fix ZERO nodes; a non-zero `total` is a signal to grep git log for
the most recent Cypher change.

**Cross-label query strategy.** Three separate queries — one per
label — rather than one `(n:Entity OR n:Event OR n:Fact)` query.
Neo4j's planner can't efficiently combine label predicates with
property filters via index, so the OR form degenerates into a full
graph scan. Per-label queries each use the K11.3
`<label>_user_project_*` / `<label>_user_evidence` composite index.

**Race caveat — DO NOT run concurrently with extraction.** Between
`MERGE (target)-[e:EVIDENCED_BY]` and the counter increment there
is a transaction-local window where `count(r)` would already see
the new edge but `target.evidence_count` would not yet reflect it.
The reconciler would "fix" the counter up and then the extraction
transaction would commit its own increment, producing a +1 drift
in the opposite direction. Same rule as K11.8's
`cleanup_zero_evidence_nodes`: call only from a paused / completed
extraction-job state.

Reference: KSA §3.6, 101_DATA_RE_ENGINEERING_PLAN.md §3.6,
K11.8 provenance repo, K11.9 plan item in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from app.db.neo4j_helpers import CypherSession, run_write
from app.metrics import evidence_count_drift_fixed_total

logger = logging.getLogger(__name__)

__all__ = [
    "ReconcileResult",
    "ReconcileLabel",
    "RECONCILE_LABELS",
    "reconcile_evidence_count",
]


# Closed enum — the three node types that carry `evidence_count`.
# Relations are intentionally excluded: they track provenance via
# `source_event_ids` on the edge, not via EVIDENCED_BY, and have no
# cached counter to reconcile (K11.6 design).
ReconcileLabel = Literal["Entity", "Event", "Fact"]
RECONCILE_LABELS: tuple[str, ...] = ("Entity", "Event", "Fact")


class ReconcileResult(BaseModel):
    """Per-label drift-fix counts for a single reconciler run."""

    entities_fixed: int = 0
    events_fixed: int = 0
    facts_fixed: int = 0

    @property
    def total(self) -> int:
        return self.entities_fixed + self.events_fixed + self.facts_fixed


# Label dispatch via f-string interpolation at module load time,
# same pattern as K11.8 `add_evidence`. `label` comes exclusively
# from RECONCILE_LABELS (closed Literal enum) so user input never
# reaches the template. Cypher labels can't be parameterised in a
# way that uses the label-scoped index, hence the dispatch.
#
# Query shape:
#   - MATCH on label with user_id filter (satisfies K11.4 invariant)
#   - Optional project_id narrowing for single-project reconciles
#   - OPTIONAL MATCH + count(r) computes the true edge count;
#     when a node has zero edges, OPTIONAL MATCH yields null and
#     count() skips the null, returning 0 (not 1)
#   - K11.9-R1/R1: the OPTIONAL MATCH filters the edge target's
#     `user_id` too. K11.8 `add_evidence` only creates edges with
#     matching user_ids on both endpoints, so this filter is a
#     no-op in steady state — but the reconciler exists to catch
#     write-path bugs, and a cross-user edge is exactly the kind
#     of bug we should not count toward the user's drift. Being
#     paranoid here costs nothing (src.user_id lookup uses the
#     extraction_source_user_source index).
#   - coalesce(n.evidence_count, 0) normalises legacy nodes that
#     pre-date the counter field or had the property deleted
#   - WHERE cached <> actual filters to drift cases only; nodes
#     that match exactly are skipped without a SET
#   - SET bumps updated_at so downstream read-caches invalidate
#   - RETURN count(*) aggregates post-SET, so the return is one
#     row with the fixed total
def _build_reconcile_cypher(label: str) -> str:
    return f"""
MATCH (n:{label})
WHERE n.user_id = $user_id
  AND ($project_id IS NULL OR n.project_id = $project_id)
OPTIONAL MATCH (n)-[r:EVIDENCED_BY]->(src:ExtractionSource)
  WHERE src.user_id = $user_id
WITH n, count(r) AS actual_count
WITH n, actual_count, coalesce(n.evidence_count, 0) AS cached
WHERE cached <> actual_count
SET n.evidence_count = actual_count,
    n.updated_at = datetime()
RETURN count(*) AS fixed
"""


_RECONCILE_CYPHER: dict[str, str] = {
    label: _build_reconcile_cypher(label) for label in RECONCILE_LABELS
}


async def _reconcile_label(
    session: CypherSession,
    *,
    label: str,
    user_id: str,
    project_id: str | None,
) -> int:
    result = await run_write(
        session,
        _RECONCILE_CYPHER[label],
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return 0
    fixed = int(record["fixed"])
    if fixed > 0:
        evidence_count_drift_fixed_total.labels(node_label=label).inc(fixed)
    return fixed


async def reconcile_evidence_count(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> ReconcileResult:
    """Scan `:Entity|:Event|:Fact` nodes for the given user and
    correct any drift between `evidence_count` and the actual
    `EVIDENCED_BY` edge count.

    Arguments:
        session: Neo4j session — routed through K11.4 `run_write`,
            which asserts that `$user_id` is a bound parameter.
        user_id: multi-tenant scope. Every Cypher query filters on
            this predicate first.
        project_id: optional narrowing. When set, only nodes in the
            given project are reconciled — cheap path for per-project
            maintenance (e.g., after a project rebuild). When None,
            reconciles every node owned by the user.

    Returns:
        ReconcileResult with per-label fix counts. A clean run
        returns all zeros. A non-zero total logs a WARNING because
        drift in steady state means a write-path bug somewhere —
        K11.8 `add_evidence` / `remove_evidence_for_source` are the
        two functions to audit first.

    Emits:
        `knowledge_evidence_count_drift_fixed_total{node_label}`
        counter, incremented by the per-label fix count on each
        run. Monotonic across runs — a dashboard can compute
        "drift fixed in the last N hours" via `rate()`.

    **Do NOT run concurrently with extraction.** See module
    docstring for the race analysis.
    """
    if not user_id:
        raise ValueError("user_id is required for reconcile_evidence_count")

    entities_fixed = await _reconcile_label(
        session, label="Entity", user_id=user_id, project_id=project_id
    )
    events_fixed = await _reconcile_label(
        session, label="Event", user_id=user_id, project_id=project_id
    )
    facts_fixed = await _reconcile_label(
        session, label="Fact", user_id=user_id, project_id=project_id
    )

    result = ReconcileResult(
        entities_fixed=entities_fixed,
        events_fixed=events_fixed,
        facts_fixed=facts_fixed,
    )

    if result.total > 0:
        logger.warning(
            "K11.9: reconcile_evidence_count fixed drift user=%s "
            "project=%s entities=%d events=%d facts=%d total=%d "
            "— investigate the write path, this should be zero in "
            "steady state",
            user_id,
            project_id,
            entities_fixed,
            events_fixed,
            facts_fixed,
            result.total,
        )
    else:
        # K11.9-R1/R2: debug, not info. A daily job across many
        # users would flood the log at INFO; aggregate INFO lives
        # at the orchestrator layer that calls this.
        logger.debug(
            "K11.9: reconcile_evidence_count clean user=%s project=%s",
            user_id,
            project_id,
        )

    return result
