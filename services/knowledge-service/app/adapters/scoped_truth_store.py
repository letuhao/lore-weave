"""The `TruthStore` consumers actually hold (plan T19).

Routes by scope to `GlossaryTruthAdapter` (book) or `MemoryTruthAdapter` (project/global).
This class exists so that **no consumer names a concrete store**, which is the property
Phase 8 depends on: T44–T46 merge the two, the Go bitemporal machinery moves to Python, the
HTTP hop disappears — and if consumers held the adapters directly, every one of them would
be a rewrite.

It routes on the `scope` ARGUMENT and never on "is book_id set?". Inference would break the
first time a project read carried a book id for logging, and both stores return well-formed
facts, so a misroute produces a confident wrong answer rather than an error.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.ports.truth_store import TruthFact, TruthScope

logger = logging.getLogger(__name__)

__all__ = ["ScopedTruthStore"]


class ScopedTruthStore:
    def __init__(self, *, book_store, memory_store) -> None:
        self._book = book_store
        self._memory = memory_store

    def _route(self, scope: TruthScope):
        if scope == "book":
            return self._book
        if scope in ("project", "global"):
            return self._memory
        raise ValueError(f"unknown truth scope {scope!r}")

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
        store = self._route(scope)
        logger.debug("truth route: scope=%s → %s", scope, type(store).__name__)
        return await store.facts_for_subject(
            scope=scope, user_id=user_id, subject_id=subject_id,
            book_id=book_id, project_id=project_id, as_of=as_of,
            min_confidence=min_confidence, limit=limit,
        )

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
        store = self._route(scope)
        logger.debug("truth route: scope=%s → %s", scope, type(store).__name__)
        return await store.search_facts(
            scope=scope, user_id=user_id, query=query,
            book_id=book_id, project_id=project_id, as_of=as_of,
            min_confidence=min_confidence, limit=limit,
        )
