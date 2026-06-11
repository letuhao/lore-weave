"""A2-S1 — entity-status repository (`:EntityStatus` nodes).

The SCORE-style canon guard (composition A2) needs to ask *"is entity E in a
contradicted status at story position P?"* (a dead character acting). The KG has
no native status model, and `:Fact` does NOT fit (closed `FACT_TYPES`, content-
keyed idempotency, no order axis, no entity link — confirmed at BUILD against
`facts.py`). So status is its own node.

An `:EntityStatus` is a **transition** for one entity at one reading position:
`(entity_id, status, from_order)`. "Status at P" = the latest evidenced
transition with `from_order ≤ P`, defaulting to `active`. `from_order` is on the
**reading axis** (`event_order`, the EVENT_ORDER_CHAPTER_STRIDE scale) so it lines
up with the composition packer's spoiler/position axis.

Coarse V1 vocab = `active | gone` (review M3: `gone→active` revivals are
LEGITIMATE — so this is an *advisory* signal the A2 LLM-judge confirms, never a
standalone hard gate). Evidence-backed like facts/events so the persist path
(A2-S1b) can wire `add_evidence`/retract-then-write and zero-evidence cleanup,
preserving the canon=published invariant on re-extraction.

Idempotency: deterministic id from `(user_id, project_id, entity_id, from_order,
status)` — re-extracting the same transition is a no-op; a later revival is a
DISTINCT node (different from_order/status).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write

logger = logging.getLogger(__name__)

__all__ = [
    "EntityStatus",
    "StatusValue",
    "STATUS_VALUES",
    "GONE_STATES",
    "entity_status_id",
    "merge_entity_status",
    "status_at_order",
    "statuses_detail_at_order",
    "delete_entity_status_with_zero_evidence",
]

# Coarse V1 vocabulary. Fine states (dead/destroyed/lost/departed/transformed)
# all map to `gone` for now; the LLM-judge (A2-S3) covers the semantic residue.
StatusValue = Literal["active", "gone"]
STATUS_VALUES: tuple[str, ...] = ("active", "gone")
# The states whose "referenced as present/acting" is a candidate contradiction.
GONE_STATES: tuple[str, ...] = ("gone",)


def entity_status_id(
    user_id: str, project_id: str | None, entity_id: str, from_order: int, status: str,
) -> str:
    """Deterministic id — same transition → same node (idempotent re-extraction)."""
    if not user_id:
        raise ValueError("user_id is required for entity_status_id")
    if not entity_id:
        raise ValueError("entity_id is required for entity_status_id")
    if status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {STATUS_VALUES}, got {status!r}")
    if not isinstance(from_order, int):
        raise ValueError(f"from_order must be an int, got {from_order!r}")
    key = f"v1:{user_id}:{project_id or 'global'}:{entity_id}:{from_order}:{status}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class EntityStatus(BaseModel):
    """Pydantic projection of an `:EntityStatus` node."""

    id: str
    user_id: str
    project_id: str | None = None
    entity_id: str
    status: str
    from_order: int
    source_types: list[str] = Field(default_factory=list)
    provenances: list[str] = Field(default_factory=list)
    source_chapter: str | None = None
    evidence_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _node_to_status(node: Any) -> EntityStatus:
    data = dict(node.items()) if hasattr(node, "items") else dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    return EntityStatus.model_validate(data)


# ── merge_entity_status ───────────────────────────────────────────────

_MERGE_CYPHER = """
MERGE (s:EntityStatus {id: $id})
ON CREATE SET
  s.user_id = $user_id,
  s.project_id = $project_id,
  s.entity_id = $entity_id,
  s.status = $status,
  s.from_order = $from_order,
  s.source_types = [$source_type],
  s.provenances = [$provenance],
  s.source_chapter = $source_chapter,
  s.evidence_count = 0,
  s.created_at = datetime(),
  s.updated_at = datetime()
ON MATCH SET
  s.source_types = CASE
    WHEN $source_type IN s.source_types THEN s.source_types
    ELSE s.source_types + $source_type
  END,
  s.provenances = CASE
    WHEN $provenance IN coalesce(s.provenances, []) THEN s.provenances
    ELSE coalesce(s.provenances, []) + $provenance
  END,
  s.updated_at = datetime()
WITH s
WHERE s.user_id = $user_id
RETURN s
"""


async def merge_entity_status(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    entity_id: str,
    status: str,
    from_order: int,
    source_type: str = "book_content",
    source_chapter: str | None = None,
    provenance: str = "human_authored",
) -> EntityStatus:
    """Idempotent upsert of one status transition. `evidence_count` starts 0 — the
    persist path (A2-S1b) calls `add_evidence` so retract-then-write + zero-evidence
    cleanup keep status in lockstep with the source on re-extraction."""
    if status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {STATUS_VALUES}, got {status!r}")
    if not entity_id:
        raise ValueError("entity_id must be a non-empty string")
    if not isinstance(from_order, int):
        raise ValueError("from_order must be an int (reading-axis event_order)")
    sid = entity_status_id(user_id, project_id, entity_id, from_order, status)
    result = await run_write(
        session, _MERGE_CYPHER,
        user_id=user_id, id=sid, project_id=project_id, entity_id=entity_id,
        status=status, from_order=from_order, source_type=source_type,
        source_chapter=source_chapter or None, provenance=provenance,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(f"merge_entity_status returned no row for id={sid!r}")
    return _node_to_status(record["s"])


# ── status_at_order ───────────────────────────────────────────────────

# OPTIONAL MATCH + collect-inside (NOT a CALL subquery) so an entity with NO
# status transition survives the row and defaults to 'active' — a CALL subquery
# returning 0 rows would DROP the entity (memory: neo4j_call_subquery_drops_outer_row).
_STATUS_AT_ORDER_CYPHER = """
UNWIND $entity_ids AS eid
OPTIONAL MATCH (s:EntityStatus {user_id: $user_id, entity_id: eid})
WHERE ($project_id IS NULL OR s.project_id = $project_id)
  AND s.from_order <= $at_order
  AND s.evidence_count >= $min_evidence
WITH eid, s ORDER BY s.from_order DESC
WITH eid, head(collect(s)) AS latest
RETURN eid AS entity_id, coalesce(latest.status, 'active') AS status
"""


async def status_at_order(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    entity_ids: list[str],
    at_order: int,
    min_evidence: int = 1,
) -> dict[str, str]:
    """`{entity_id: status}` — the latest EVIDENCED transition with `from_order ≤
    at_order` per entity; entities with none default to `active`. Every requested
    id appears in the result (no silent drop)."""
    if not entity_ids:
        return {}
    result = await run_read(
        session, _STATUS_AT_ORDER_CYPHER,
        user_id=user_id, project_id=project_id,
        entity_ids=list(dict.fromkeys(entity_ids)), at_order=at_order,
        min_evidence=min_evidence,
    )
    return {record["entity_id"]: record["status"] async for record in result}


# ── statuses_detail_at_order (T2.1) ───────────────────────────────────

# Same window logic as status_at_order, but projects from_order too so the codex
# can show WHEN the latest transition happened. Kept separate from status_at_order
# (dict[str,str], used by the A2 canon guard) to avoid changing that return type.
_STATUS_DETAIL_AT_ORDER_CYPHER = """
UNWIND $entity_ids AS eid
OPTIONAL MATCH (s:EntityStatus {user_id: $user_id, entity_id: eid})
WHERE ($project_id IS NULL OR s.project_id = $project_id)
  AND s.from_order <= $at_order
  AND s.evidence_count >= $min_evidence
WITH eid, s ORDER BY s.from_order DESC
WITH eid, head(collect(s)) AS latest
RETURN eid AS entity_id,
       coalesce(latest.status, 'active') AS status,
       latest.from_order AS from_order
"""


async def statuses_detail_at_order(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    entity_ids: list[str],
    at_order: int,
    min_evidence: int = 1,
) -> dict[str, dict[str, Any]]:
    """`{entity_id: {status, from_order}}` — latest EVIDENCED transition with
    `from_order <= at_order` per entity; none → `{status: 'active', from_order:
    None}`. Every requested id appears (no silent drop). A restrictive `at_order`
    (e.g. -1 for a fail-closed window) yields all-`active` with no leak."""
    if not entity_ids:
        return {}
    result = await run_read(
        session, _STATUS_DETAIL_AT_ORDER_CYPHER,
        user_id=user_id, project_id=project_id,
        entity_ids=list(dict.fromkeys(entity_ids)), at_order=at_order,
        min_evidence=min_evidence,
    )
    return {
        record["entity_id"]: {"status": record["status"], "from_order": record["from_order"]}
        async for record in result
    }


# ── delete_entity_status_with_zero_evidence ───────────────────────────

_DELETE_ZERO_EVIDENCE_CYPHER = """
MATCH (s:EntityStatus)
WHERE s.user_id = $user_id
  AND ($project_id IS NULL OR s.project_id = $project_id)
  AND s.evidence_count = 0
DETACH DELETE s
RETURN count(*) AS deleted
"""


async def delete_entity_status_with_zero_evidence(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    """Cascade cleanup after retract (mirrors facts/events). Same orchestration
    rule: must NOT run concurrently with extraction (one-active-job-per-project)."""
    result = await run_write(
        session, _DELETE_ZERO_EVIDENCE_CYPHER,
        user_id=user_id, project_id=project_id,
    )
    record = await result.single()
    return int(record["deleted"]) if record else 0
