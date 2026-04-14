"""K11.7 — facts repository.

Functions over `:Fact` nodes. A Fact is a typed propositional
statement extracted from text — distinct from `:Event` (a
discrete narrative happening) and from `:RELATES_TO` (a directed
edge between two entities). Examples per KSA §5.1:

  - decision: "We decided to use fire magic"
  - preference: "Kai always carries a sword"
  - milestone: "Phoenix completes her training"
  - negation: "Water Kingdom does not know Kai killed Zhao"

Facts have a temporal model identical to relations: `valid_from`
on creation, `valid_until` set by `invalidate_fact` when
contradicting evidence arrives. Pass 1 (pattern) facts carry
`pending_validation = true` and are excluded from the L2 RAG
context loader by default; K17 LLM Pass 2 promotes them by
re-merging with higher confidence.

Idempotency: deterministic id from `(user_id, project_id, type,
canonicalize_text(content))`. Re-extracting the same fact from
any source is a no-op.

Reference: KSA §3.4 (Fact nodes), §5.1 (Pass 1 quarantine),
K11.3 schema indexes fact_id_unique, fact_user_evidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write
from app.db.neo4j_repos.canonical import canonicalize_text

logger = logging.getLogger(__name__)

__all__ = [
    "Fact",
    "FactType",
    "FACT_TYPES",
    "fact_id",
    "merge_fact",
    "get_fact",
    "list_facts_by_type",
    "invalidate_fact",
    "delete_facts_with_zero_evidence",
]

# Closed enum per KSA §5.1. New types require both a code change
# and an extraction-side pattern, so a Literal is fine.
FactType = Literal["decision", "preference", "milestone", "negation"]
FACT_TYPES: tuple[str, ...] = ("decision", "preference", "milestone", "negation")


def fact_id(
    user_id: str,
    project_id: str | None,
    type: str,
    content: str,
) -> str:
    """Deterministic id for a `:Fact` node.

    Same `(user_id, project_id, type, canonicalize_text(content))`
    tuple → same id. Re-extraction is a no-op.

    `type` is part of the key so two facts with identical content
    but different types ("decision: use fire magic" vs
    "preference: use fire magic") are distinct nodes.
    """
    if not user_id:
        raise ValueError("user_id is required for fact_id")
    if not type:
        raise ValueError("type is required for fact_id")
    if type not in FACT_TYPES:
        raise ValueError(f"type must be one of {FACT_TYPES}, got {type!r}")
    if not content:
        raise ValueError("content is required for fact_id")
    canonical = canonicalize_text(content)
    if not canonical:
        raise ValueError(
            f"content {content!r} canonicalizes to empty — cannot derive id"
        )
    key = f"v1:{user_id}:{project_id or 'global'}:{type}:{canonical}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class Fact(BaseModel):
    """Pydantic projection of a `:Fact` node."""

    id: str
    user_id: str
    project_id: str | None = None
    type: str
    content: str
    canonical_content: str
    confidence: float = 0.0
    pending_validation: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    source_types: list[str] = Field(default_factory=list)
    source_chapter: str | None = None
    evidence_count: int = 0
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _node_to_fact(node: Any) -> Fact:
    if hasattr(node, "items"):
        data = dict(node.items())
    else:
        data = dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    return Fact.model_validate(data)


# ── merge_fact ────────────────────────────────────────────────────────


_MERGE_FACT_CYPHER = """
MERGE (f:Fact {id: $id})
ON CREATE SET
  f.user_id = $user_id,
  f.project_id = $project_id,
  f.type = $type,
  f.content = $content,
  f.canonical_content = $canonical_content,
  f.confidence = $confidence,
  f.pending_validation = $pending_validation,
  f.valid_from = coalesce($valid_from, datetime()),
  f.valid_until = NULL,
  f.source_types = [$source_type],
  f.source_chapter = $source_chapter,
  f.evidence_count = 0,
  f.archived_at = NULL,
  f.created_at = datetime(),
  f.updated_at = datetime()
ON MATCH SET
  f.source_types = CASE
    WHEN $source_type IN f.source_types THEN f.source_types
    ELSE f.source_types + $source_type
  END,
  f.confidence = CASE
    WHEN $confidence > f.confidence THEN $confidence
    ELSE f.confidence
  END,
  f.pending_validation = CASE
    WHEN $confidence > f.confidence THEN $pending_validation
    ELSE f.pending_validation
  END,
  f.updated_at = datetime()
WITH f
WHERE f.user_id = $user_id
RETURN f
"""


async def merge_fact(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    type: str,
    content: str,
    confidence: float = 0.0,
    pending_validation: bool = False,
    valid_from: datetime | None = None,
    source_type: str = "book_content",
    source_chapter: str | None = None,
) -> Fact:
    """Idempotent upsert. Same (user, project, type, normalized
    content) returns the same node. K17 Pass 2 promotion
    semantics same as relations: higher confidence wins AND
    flips `pending_validation` to the new value.
    """
    if type not in FACT_TYPES:
        raise ValueError(f"type must be one of {FACT_TYPES}, got {type!r}")
    if not content:
        raise ValueError("content must be a non-empty string")
    fid = fact_id(
        user_id=user_id,
        project_id=project_id,
        type=type,
        content=content,
    )
    canonical_content = canonicalize_text(content)
    result = await run_write(
        session,
        _MERGE_FACT_CYPHER,
        user_id=user_id,
        id=fid,
        project_id=project_id,
        type=type,
        content=content,
        canonical_content=canonical_content,
        confidence=confidence,
        pending_validation=pending_validation,
        valid_from=valid_from,
        source_type=source_type,
        source_chapter=source_chapter,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(f"merge_fact returned no row for id={fid!r}")
    return _node_to_fact(record["f"])


# ── get_fact ──────────────────────────────────────────────────────────


_GET_FACT_CYPHER = """
MATCH (f:Fact {id: $id})
WHERE f.user_id = $user_id
RETURN f
"""


async def get_fact(
    session: CypherSession,
    *,
    user_id: str,
    fact_id: str,
) -> Fact | None:
    if not fact_id:
        raise ValueError("fact_id must be a non-empty string")
    result = await run_read(
        session,
        _GET_FACT_CYPHER,
        user_id=user_id,
        id=fact_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_fact(record["f"])


# ── list_facts_by_type ────────────────────────────────────────────────


# K11.7 acceptance: "Fact type filter efficient". The K11.3
# schema doesn't ship a per-type index because the type cardinality
# is tiny (4 values) — a full label scan with WHERE is fast
# enough for any realistic per-user fact volume. If profiling
# shows a hot path here, K11.3-R2 can add `(user_id, type)`.
_LIST_FACTS_BY_TYPE_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND ($project_id IS NULL OR f.project_id = $project_id)
  AND ($type IS NULL OR f.type = $type)
  AND ($exclude_pending = false OR coalesce(f.pending_validation, false) = false)
  AND f.confidence >= $min_confidence
  AND f.valid_until IS NULL
  AND ($include_archived OR f.archived_at IS NULL)
RETURN f
ORDER BY f.confidence DESC, f.created_at DESC
LIMIT $limit
"""


async def list_facts_by_type(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
    type: str | None = None,
    min_confidence: float = 0.8,
    exclude_pending: bool = True,
    include_archived: bool = False,
    limit: int = 100,
) -> list[Fact]:
    """List active facts, optionally filtered by `type`.

    Default filters match the L2 loader: confidence >= 0.8,
    valid_until IS NULL, pending_validation = false. The memory
    UI's "Quarantine" tab can pass `exclude_pending=False` and
    `min_confidence=0.0` to see Pass 1 candidates.

    `type=None` returns facts of all types; otherwise pass one
    of `FACT_TYPES`.
    """
    if type is not None and type not in FACT_TYPES:
        raise ValueError(f"type must be one of {FACT_TYPES} or None, got {type!r}")
    if min_confidence < 0.0 or min_confidence > 1.0:
        raise ValueError(f"min_confidence must be in [0,1], got {min_confidence}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    result = await run_read(
        session,
        _LIST_FACTS_BY_TYPE_CYPHER,
        user_id=user_id,
        project_id=project_id,
        type=type,
        min_confidence=min_confidence,
        exclude_pending=exclude_pending,
        include_archived=include_archived,
        limit=limit,
    )
    return [_node_to_fact(record["f"]) async for record in result]


# ── invalidate_fact ───────────────────────────────────────────────────


_INVALIDATE_FACT_CYPHER = """
MATCH (f:Fact {id: $id})
WHERE f.user_id = $user_id
SET f.valid_until = coalesce($valid_until, datetime()),
    f.updated_at = datetime()
RETURN f
"""


async def invalidate_fact(
    session: CypherSession,
    *,
    user_id: str,
    fact_id: str,
    valid_until: datetime | None = None,
) -> Fact | None:
    """Soft-invalidate a fact by setting `valid_until`.

    Same idempotency semantics as `invalidate_relation`. Default
    queries exclude `valid_until IS NOT NULL` so invalidated
    facts vanish from the L2 loader without losing audit history.
    """
    if not fact_id:
        raise ValueError("fact_id must be a non-empty string")
    result = await run_write(
        session,
        _INVALIDATE_FACT_CYPHER,
        user_id=user_id,
        id=fact_id,
        valid_until=valid_until,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_fact(record["f"])


# ── delete_facts_with_zero_evidence ───────────────────────────────────


_DELETE_FACTS_ZERO_EVIDENCE_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND ($project_id IS NULL OR f.project_id = $project_id)
  AND f.evidence_count = 0
DETACH DELETE f
RETURN count(*) AS deleted
"""


async def delete_facts_with_zero_evidence(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    """Cascade cleanup. Same race-window warning as
    `delete_entities_with_zero_evidence` and
    `delete_events_with_zero_evidence` — K11.8 must orchestrate
    so this never runs concurrently with extraction.
    """
    result = await run_write(
        session,
        _DELETE_FACTS_ZERO_EVIDENCE_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["deleted"])
