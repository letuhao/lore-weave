"""`TruthStore` over knowledge-service's own graph facts (plan T19).

Project- and global-scoped truth: the `:Fact` nodes this service owns. Delegates to
`neo4j_repos/facts.py`, like every other adapter in this package.

The interesting work here is NARROWING, not delegating. `Fact` carries store-specific
fields — `canonical_content`, `pending_validation`, `source_types` — and `TruthFact`
deliberately drops them, because a consumer that read `pending_validation` would be pinned
to this store and Phase 8 would have to rewrite it. What crosses the port is what the
glossary store can also honestly produce.

⚠️ **This store positions facts on WALL CLOCK** (`valid_from` / `valid_until` are
datetimes), while book truth positions them on story ordinals. T45 owns reconciling the two
axes; until then the port passes `as_of` through as an opaque position and this adapter
rejects an ordinal rather than silently comparing an int to a datetime.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.facts import Fact, list_facts_for_entity, recall_facts
from app.ports.truth_store import check_axis, TruthFact, TruthScope

logger = logging.getLogger(__name__)

__all__ = ["MemoryTruthAdapter"]

_SUPPORTED_SCOPES = ("project", "global")


def _to_truth_fact(fact: Fact, scope: TruthScope) -> TruthFact:
    return TruthFact(
        fact_id=fact.id,
        subject_id=getattr(fact, "subject_id", None),
        # This store models a fact as (type, content) rather than (attribute, value). The
        # mapping is stated here, once, instead of leaving every consumer to discover that
        # `attribute` means `type` on one side of the port.
        attribute=fact.type,
        value=fact.content,
        scope=scope,
        confidence=fact.confidence,
        valid_from=fact.valid_from,
        valid_to=fact.valid_until,
        source_ref=fact.source_chapter,
    )


class MemoryTruthAdapter:
    def __init__(self, session: CypherSession) -> None:
        self._session = session

    def _check(self, scope: TruthScope, as_of: int | datetime | None) -> None:
        if scope not in _SUPPORTED_SCOPES:
            raise ValueError(
                f"MemoryTruthAdapter serves {_SUPPORTED_SCOPES}, not {scope!r} — "
                "book-scoped truth belongs to GlossaryTruthAdapter"
            )
        # T45 — one declaration, read here. `_SUPPORTED_SCOPES` above still says WHICH scopes
        # this adapter serves; the port says which AXIS each of them is positioned on.
        check_axis(scope, as_of)

    async def facts_for_subject(
        self,
        *,
        scope: TruthScope,
        user_id: str,
        subject_id: str,
        book_id: str | None = None,
        project_id: str | None = None,
        as_of: int | datetime | None = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[TruthFact]:
        self._check(scope, as_of)
        facts = await list_facts_for_entity(
            self._session,
            user_id=user_id, entity_id=subject_id, project_id=project_id,
            min_confidence=min_confidence, limit=limit,
        )
        out = [_to_truth_fact(f, scope) for f in facts]
        if isinstance(as_of, datetime):
            # Applied HERE rather than pushed into the repo: the repo's fact reads have no
            # wall-clock as-of parameter, and inventing one for a filter this cheap would
            # add a query shape nothing else uses.
            out = [f for f in out if _covers(f, as_of)]
        logger.debug(
            "truth facts_for_subject: backend=memory scope=%s as_of=%s hits=%d",
            scope, as_of, len(out),
        )
        return out

    async def search_facts(
        self,
        *,
        scope: TruthScope,
        user_id: str,
        query: str | None = None,
        book_id: str | None = None,
        project_id: str | None = None,
        as_of: int | datetime | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[TruthFact]:
        self._check(scope, as_of)
        if not project_id:
            raise ValueError("memory truth search requires a project_id")
        facts = await recall_facts(
            self._session,
            user_id=user_id, project_id=project_id,
            subject_name=query, min_confidence=min_confidence, limit=limit,
        )
        out = [_to_truth_fact(f, scope) for f in facts]
        if isinstance(as_of, datetime):
            out = [f for f in out if _covers(f, as_of)]
        return out


def _covers(fact: TruthFact, at: datetime) -> bool:
    """Half-open `valid_from <= at < valid_to`, with an open start or end treated as
    unbounded. Same convention as the story-ordinal side — the axes differ, the interval
    semantics must not."""
    start, end = fact.valid_from, fact.valid_to
    if isinstance(start, datetime) and at < start:
        return False
    if isinstance(end, datetime) and at >= end:
        return False
    return True
