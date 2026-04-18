"""K15.10 — quarantine cleanup job.

Per KSA §5.1 quarantine model: Pass 1 extraction writes facts with
`pending_validation=true` and `confidence=0.5` so L2 retrieval skips
them until the K17 LLM validator promotes or rejects each one on
Pass 2. If Pass 2 never runs (worker-ai outage, provider budget
exhausted, user disabled auto-validation) facts accumulate in the
quarantine forever, silently inflating node counts and evidence-count
dashboards.

This job is the safety net: any fact still flagged
`pending_validation=true` after a configurable TTL (default 24h)
gets soft-invalidated by setting `valid_until = datetime()`. The
node stays in the graph for audit / manual review via the memory
UI's Quarantine tab, but standard L2 queries exclude it via the
`valid_until IS NULL` filter.

**Soft-invalidate, not delete.** The K11.7 model treats
`valid_until IS NOT NULL` as "no longer active" without losing
provenance. A deleted fact would orphan its `EVIDENCED_BY` edges
and force a K11.9 reconciler run; soft-invalidate keeps the
evidence chain intact and leaves K18.3 archive policy to decide
when (if ever) to actually remove the node.

**Tenant-scoped by default.** Pass `user_id=None` to sweep
globally — only appropriate for admin cron, not per-request paths.
Production callers should always scope to a tenant.

**What this module deliberately does NOT do:**
  - Clear `pending_validation` on invalidation — the flag stays
    true so the audit trail records "this fact was quarantined and
    never promoted", distinct from "this fact was promoted then
    invalidated for a different reason".
  - Remove EVIDENCED_BY edges — K11.9 reconciler owns orphan
    evidence sweeps.
  - Respect project_id — the TTL is a tenant-wide policy, not
    per-project. If a per-project override becomes necessary it
    should live in K18 governance, not here.
  - Clean facts that have `pending_validation=true` but a NULL
    `updated_at`. Neo4j NULL comparison makes them unreachable by
    the TTL predicate (NULL < x is NULL). This is a deliberate
    fail-safe: facts without a timestamp came from a legacy/bulk
    import path that skipped K11 stamping, and we'd rather leak
    them into the Quarantine UI than risk sweeping something whose
    age we cannot verify. Fix the writer, not this sweeper.

Reference: KSA §5.1 quarantine model, K15.10 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import logging

from app.db.neo4j_helpers import CypherSession, assert_user_id_param
from app.metrics import quarantine_auto_invalidated_total

logger = logging.getLogger(__name__)

__all__ = [
    "run_quarantine_cleanup",
    "DEFAULT_TTL_HOURS",
]


DEFAULT_TTL_HOURS = 24


_CLEANUP_CYPHER = """
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


async def run_quarantine_cleanup(
    session: CypherSession,
    *,
    user_id: str | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    limit: int | None = None,
) -> int:
    """Soft-invalidate quarantined facts older than `ttl_hours`.

    Args:
        session: K11.4 CypherSession.
        user_id: tenant scope. `None` sweeps globally — only use
            from admin cron, never per-request paths.
        ttl_hours: facts whose `updated_at` is older than
            `now - ttl_hours` AND still have `pending_validation=true`
            get soft-invalidated. Default 24h per KSA §5.1.
        limit: P-K15.10-01 (session 46). Cap on facts invalidated
            per call. `None` means "invalidate everything that
            matches the TTL filter in one statement" — fine for
            hobby-scale tenants, problematic under a large backlog.
            When set, the scheduler should loop until a call
            returns zero.

    Returns:
        Number of facts invalidated on this run. The
        `knowledge_quarantine_auto_invalidated_total` counter is
        incremented by the same amount.
    """
    if ttl_hours <= 0:
        raise ValueError(f"ttl_hours must be > 0, got {ttl_hours}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be positive when set, got {limit}")

    # Bypass run_write because it types user_id as str; this is the
    # one caller that legitimately passes None (admin global sweep).
    # The $user_id reference safety check still applies — the Cypher
    # above handles the NULL branch explicitly via
    # `($user_id IS NULL OR f.user_id = $user_id)`.
    assert_user_id_param(_CLEANUP_CYPHER)
    result = await session.run(
        _CLEANUP_CYPHER,
        user_id=user_id,
        ttl_hours=ttl_hours,
        limit=limit,
    )
    record = await result.single()
    invalidated = int(record["invalidated"]) if record else 0

    if invalidated:
        quarantine_auto_invalidated_total.inc(invalidated)
        logger.info(
            "K15.10: quarantine cleanup invalidated %d fact(s) "
            "user=%s ttl_hours=%d",
            invalidated,
            user_id or "<global>",
            ttl_hours,
        )

    return invalidated
