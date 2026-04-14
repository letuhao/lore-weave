"""K11.8 — provenance repository (`ExtractionSource` + `EVIDENCED_BY`).

The bookkeeping layer that makes partial extraction operations
safe and composable. KSA §3.4.C invariant:

  > An entity/fact is deleted if and only if its EVIDENCED_BY
  > edge count reaches zero.

That invariant gives every extraction operation (append,
partial overwrite, partial delete, stop, disable) the same
shape: mutate edges, then sweep zero-evidence orphans. K11.5a /
K11.7 ship the per-label sweepers; K11.8 ships the edge writer
+ the cascade cleanup orchestration.

Atomicity contract per the K11.7/K11.8 plan:
  - `add_evidence` increments `target.evidence_count` and
    `target.mention_count` ONLY when the EVIDENCED_BY edge is
    actually created (ON CREATE branch). Re-running the same
    extraction with the same `(target, source, job_id)` is a
    no-op — the edge exists, no increment, no double-count.
  - `remove_evidence_for_source` decrements the counter for
    each removed edge in the same statement. The counter never
    drifts as long as no caller bypasses these helpers.

The K11.9 reconciler (out of K11.8 scope) is the safety net
that runs offline and catches any drift between the counter
and the actual edge count.

Reference: KSA §3.4.C provenance edges, §3.8.5 partial
extraction cascade, K11.3 schema constraints
extraction_source_id_unique + indexes extraction_source_user_*.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write
from app.db.neo4j_repos.entities import delete_entities_with_zero_evidence
from app.db.neo4j_repos.events import delete_events_with_zero_evidence
from app.db.neo4j_repos.facts import delete_facts_with_zero_evidence

logger = logging.getLogger(__name__)

__all__ = [
    "ExtractionSource",
    "SourceType",
    "TargetLabel",
    "SOURCE_TYPES",
    "TARGET_LABELS",
    "extraction_source_id",
    "upsert_extraction_source",
    "get_extraction_source",
    "add_evidence",
    "remove_evidence_for_source",
    "delete_source_cascade",
    "cleanup_zero_evidence_nodes",
]


# Closed enum per KSA §3.4.C. New source types require both an
# extraction-side handler and a code change here.
SourceType = Literal["chapter", "chat_message", "glossary_entity", "manual"]
SOURCE_TYPES: tuple[str, ...] = (
    "chapter",
    "chat_message",
    "glossary_entity",
    "manual",
)

# Targets of EVIDENCED_BY edges. K11.5a/K11.6/K11.7 ship the
# three writeable node types. Relations carry their own evidence
# via source_event_ids on the edge — they do NOT receive
# EVIDENCED_BY edges directly.
TargetLabel = Literal["Entity", "Event", "Fact"]
TARGET_LABELS: tuple[str, ...] = ("Entity", "Event", "Fact")


def extraction_source_id(
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
) -> str:
    """Deterministic id for an `:ExtractionSource` node.

    Same `(user_id, project_id, source_type, source_id)` tuple
    produces the same id, forever. `upsert_extraction_source`
    keys MERGE on this so re-running an extraction job on the
    same chapter is a no-op against the source node.

    `source_id` here is the EXTRACTOR-side identifier (a chapter
    UUID, a message id, a glossary entry id) — distinct from the
    32-hex hash this function returns.
    """
    if not user_id:
        raise ValueError("user_id is required for extraction_source_id")
    if not source_type:
        raise ValueError("source_type is required for extraction_source_id")
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            f"source_type must be one of {SOURCE_TYPES}, got {source_type!r}"
        )
    if not source_id:
        raise ValueError("source_id is required for extraction_source_id")
    key = (
        f"v1:{user_id}:{project_id or 'global'}:{source_type}:{source_id}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class ExtractionSource(BaseModel):
    """Pydantic projection of an `:ExtractionSource` node."""

    id: str
    user_id: str
    project_id: str | None = None
    source_type: str
    source_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _node_to_source(node: Any) -> ExtractionSource:
    if hasattr(node, "items"):
        data = dict(node.items())
    else:
        data = dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    return ExtractionSource.model_validate(data)


# ── upsert_extraction_source ──────────────────────────────────────────


_UPSERT_SOURCE_CYPHER = """
MERGE (s:ExtractionSource {id: $id})
ON CREATE SET
  s.user_id = $user_id,
  s.project_id = $project_id,
  s.source_type = $source_type,
  s.source_id = $source_id,
  s.created_at = datetime(),
  s.updated_at = datetime()
ON MATCH SET
  s.updated_at = datetime()
WITH s
WHERE s.user_id = $user_id
RETURN s
"""


async def upsert_extraction_source(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
) -> ExtractionSource:
    """Idempotent upsert for an extraction source.

    Returns the source so the caller can use its `id` field on
    subsequent `add_evidence` calls. Re-running with the same
    (user, project, source_type, source_id) tuple returns the
    same node — no duplicates.
    """
    sid = extraction_source_id(
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
    )
    result = await run_write(
        session,
        _UPSERT_SOURCE_CYPHER,
        user_id=user_id,
        id=sid,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(
            f"upsert_extraction_source returned no row for id={sid!r}"
        )
    return _node_to_source(record["s"])


# ── get_extraction_source ─────────────────────────────────────────────


_GET_SOURCE_BY_NATURAL_KEY_CYPHER = """
MATCH (s:ExtractionSource)
WHERE s.user_id = $user_id
  AND s.source_type = $source_type
  AND s.source_id = $source_id
RETURN s
"""


async def get_extraction_source(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
) -> ExtractionSource | None:
    """Look up an extraction source by its natural key. Uses the
    K11.3 `extraction_source_user_source` index."""
    if not source_type or not source_id:
        raise ValueError("source_type and source_id are required")
    result = await run_read(
        session,
        _GET_SOURCE_BY_NATURAL_KEY_CYPHER,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_source(record["s"])


# ── add_evidence ──────────────────────────────────────────────────────


# Three templates, one per target label, so the planner uses
# the per-label uniqueness constraint (entity_id_unique /
# event_id_unique / fact_id_unique) on the target lookup.
# Cypher labels can't be parameterised in a way that uses an
# index, so the dispatch lives in Python.
#
# The MERGE on the edge structurally matches `(target)-
# [e:EVIDENCED_BY {job_id: $job_id}]->(src)`. ON CREATE sets the
# edge metadata AND increments target.evidence_count +
# target.mention_count atomically. ON MATCH only refreshes the
# extracted_at timestamp — the counts stay accurate because the
# edge already exists.
#
# coalesce(target.mention_count, 0) handles legacy nodes that
# pre-date the K11.5b mention_count field.
#
# `_just_created` marker property: ON CREATE sets it true, ON
# MATCH sets it false. We read it into the result via
# coalesce(.., false), then REMOVE it so the property never
# persists. This is the cleanest way to surface "was this a
# no-op?" to the caller without a separate pre-read.
def _build_add_evidence_cypher(label: str) -> str:
    return f"""
MATCH (target:{label} {{id: $target_id}})
WHERE target.user_id = $user_id
MATCH (src:ExtractionSource {{id: $source_id}})
WHERE src.user_id = $user_id
MERGE (target)-[e:EVIDENCED_BY {{job_id: $job_id}}]->(src)
ON CREATE SET
  e.extracted_at = datetime(),
  e.extraction_model = $extraction_model,
  e.confidence = $confidence,
  e._just_created = true,
  target.evidence_count = coalesce(target.evidence_count, 0) + 1,
  target.mention_count = coalesce(target.mention_count, 0) + 1,
  target.updated_at = datetime()
ON MATCH SET
  e.extracted_at = datetime(),
  e._just_created = false
WITH target, e, coalesce(e._just_created, false) AS created
REMOVE e._just_created
RETURN target.evidence_count AS evidence_count,
       target.mention_count AS mention_count,
       created
"""


_ADD_EVIDENCE_CYPHER: dict[str, str] = {
    label: _build_add_evidence_cypher(label) for label in TARGET_LABELS
}


class EvidenceWriteResult(BaseModel):
    """Returned by `add_evidence` so the caller can log the
    post-write counters and tell whether the edge was newly
    created or already present."""

    evidence_count: int
    mention_count: int
    created: bool


async def add_evidence(
    session: CypherSession,
    *,
    user_id: str,
    target_label: str,
    target_id: str,
    source_id: str,
    extraction_model: str,
    confidence: float,
    job_id: str,
) -> EvidenceWriteResult | None:
    """Attach an EVIDENCED_BY edge from `target` to the
    extraction source. Idempotent on `(target, source, job_id)`
    — re-running the same extraction job is a no-op against the
    counters.

    The atomic counter increment is the K11.8 critical primitive.
    Bypassing this function (e.g., writing the edge directly via
    raw Cypher) would let the counter drift; the K11.9 reconciler
    is the offline safety net that catches drift, but the cheaper
    path is to never produce drift in the first place.

    Returns `None` if either the target or the source does not
    exist under the calling user. Caller should treat that as
    "no evidence to record" and either create the missing endpoint
    or log + skip.
    """
    if target_label not in _ADD_EVIDENCE_CYPHER:
        raise ValueError(
            f"target_label must be one of {TARGET_LABELS}, got {target_label!r}"
        )
    if not target_id:
        raise ValueError("target_id must be a non-empty string")
    if not source_id:
        raise ValueError("source_id must be a non-empty string")
    if not extraction_model:
        raise ValueError("extraction_model must be a non-empty string")
    if not job_id:
        raise ValueError("job_id must be a non-empty string")
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError(f"confidence must be in [0,1], got {confidence}")

    cypher = _ADD_EVIDENCE_CYPHER[target_label]
    result = await run_write(
        session,
        cypher,
        user_id=user_id,
        target_id=target_id,
        source_id=source_id,
        extraction_model=extraction_model,
        confidence=confidence,
        job_id=job_id,
    )
    record = await result.single()
    if record is None:
        return None
    return EvidenceWriteResult(
        evidence_count=int(record["evidence_count"]),
        mention_count=int(record["mention_count"]),
        created=bool(record["created"]),
    )


# ── remove_evidence_for_source ────────────────────────────────────────


# Single statement: find every EVIDENCED_BY edge into a given
# source, decrement the target counter for each one, then DELETE
# the edge. The decrement uses `coalesce(.., 1) - 1` so a counter
# that's somehow already at NULL doesn't underflow.
#
# `count(*)` AFTER the DELETE aggregates over the processed rows
# and returns one row with the total. Putting `e` into the WITH
# projection BEFORE counting would group by edge and return one
# row per edge, not the total — that was an early bug in this
# query, fixed by deferring the aggregate to the RETURN.
_REMOVE_EVIDENCE_FOR_SOURCE_CYPHER = """
MATCH (target)-[e:EVIDENCED_BY]->(src:ExtractionSource {id: $source_id})
WHERE target.user_id = $user_id
  AND src.user_id = $user_id
SET target.evidence_count = coalesce(target.evidence_count, 1) - 1,
    target.updated_at = datetime()
DELETE e
RETURN count(*) AS removed
"""


async def remove_evidence_for_source(
    session: CypherSession,
    *,
    user_id: str,
    source_id: str,
) -> int:
    """Remove every EVIDENCED_BY edge into the given source,
    decrementing the target counter for each one. Returns the
    number of edges removed.

    Used by partial-extraction cascade: when re-extracting a
    chapter, the orchestrator calls this on the chapter's
    extraction source, then re-runs extraction (which calls
    `add_evidence` again, re-creating the edges with updated
    metadata).

    Note that this does NOT delete the ExtractionSource node
    itself — `delete_source_cascade` does that. Splitting the
    two operations lets the orchestrator re-extract into the
    same source node without re-creating it.

    `mention_count` is intentionally NOT decremented. It
    represents "times observed", a monotonic counter for
    anchor-score recompute, not a live edge count.
    """
    if not source_id:
        raise ValueError("source_id must be a non-empty string")
    result = await run_write(
        session,
        _REMOVE_EVIDENCE_FOR_SOURCE_CYPHER,
        user_id=user_id,
        source_id=source_id,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["removed"])


# ── delete_source_cascade ─────────────────────────────────────────────


# Delete the bare ExtractionSource node by its hash id. Used
# by `delete_source_cascade` AFTER `remove_evidence_for_source`
# has already detached every EVIDENCED_BY edge. Splitting the
# two operations keeps each Cypher trivially correct — packing
# the decrement + delete + aggregate into one statement got
# tangled up in per-row vs. per-target SET semantics that were
# hard to prove correct.
_DELETE_SOURCE_NODE_CYPHER = """
MATCH (s:ExtractionSource {id: $id})
WHERE s.user_id = $user_id
DETACH DELETE s
"""


async def delete_source_cascade(
    session: CypherSession,
    *,
    user_id: str,
    source_type: str,
    source_id: str,
) -> int:
    """Decrement counters for every EVIDENCED_BY edge into the
    source, then DETACH DELETE the source node. Returns the
    number of edges removed (0 if the source did not exist).

    After this call, the orchestrator should call
    `cleanup_zero_evidence_nodes` to sweep any orphans whose
    counter just hit zero.

    Composed from `get_extraction_source` +
    `remove_evidence_for_source` + a bare node delete instead
    of one packed Cypher statement — the per-target SET
    semantics for "decrement the counter for each removed edge"
    were hard to prove correct in a single query (a target with
    two edges to the same source would either compound or not
    depending on Cypher's row-iteration model). Three round-trips
    is a fair price for a provably-correct cascade.

    Idempotent — calling on an already-deleted source returns 0
    and does nothing.
    """
    if not source_type or not source_id:
        raise ValueError("source_type and source_id are required")
    src = await get_extraction_source(
        session,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
    )
    if src is None:
        return 0
    removed = await remove_evidence_for_source(
        session,
        user_id=user_id,
        source_id=src.id,
    )
    await run_write(
        session,
        _DELETE_SOURCE_NODE_CYPHER,
        user_id=user_id,
        id=src.id,
    )
    return removed


# ── cleanup_zero_evidence_nodes ───────────────────────────────────────


class CleanupResult(BaseModel):
    """Per-label deletion counts from `cleanup_zero_evidence_nodes`."""

    entities: int = 0
    events: int = 0
    facts: int = 0

    @property
    def total(self) -> int:
        return self.entities + self.events + self.facts


async def cleanup_zero_evidence_nodes(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> CleanupResult:
    """Sweep zero-evidence orphans across all three node types.

    Delegates to the per-label sweepers from K11.5a (entities)
    and K11.7 (events + facts). Each uses its own
    `(user_id, evidence_count)` composite index so the query
    cost is bounded by the calling user's churn, not the global
    graph.

    **DO NOT run concurrently with extraction.** Same race
    window as the per-label sweepers: a freshly-merged node has
    `evidence_count = 0` and there is a window before the first
    `add_evidence` call where the cleanup would mistakenly
    delete it. The K11.8 orchestrator must call this only from
    a paused / completed extraction-job state, never mid-run.
    """
    entities = await delete_entities_with_zero_evidence(
        session, user_id=user_id, project_id=project_id
    )
    events = await delete_events_with_zero_evidence(
        session, user_id=user_id, project_id=project_id
    )
    facts = await delete_facts_with_zero_evidence(
        session, user_id=user_id, project_id=project_id
    )
    logger.info(
        "K11.8: cleanup_zero_evidence_nodes user=%s project=%s "
        "entities=%d events=%d facts=%d",
        user_id,
        project_id,
        entities,
        events,
        facts,
    )
    return CleanupResult(entities=entities, events=events, facts=facts)
