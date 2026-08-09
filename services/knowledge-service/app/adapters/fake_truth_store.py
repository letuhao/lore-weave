"""In-memory `TruthStore` for tests (plan T19).

Holds `TruthFact`s and answers from them. The rules it must reproduce are the ones a
consumer cannot see going wrong:

  - **scope isolation.** A book fact must never surface in a project read. Both stores
    return well-formed facts, so a leak looks like an answer.
  - **half-open intervals on BOTH axes.** `valid_from <= as_of < valid_to`, whether the
    position is a chapter ordinal or a datetime. The axes differ; the interval semantics
    must not, or T45 inherits two conventions instead of one.
  - **axis mismatch is an ERROR.** An ordinal in a wall-clock scope (or the reverse)
    raises. Both comparisons would "work" in Python and return a confidently wrong set.
"""

from __future__ import annotations

from datetime import datetime

from app.ports.truth_store import TruthFact, TruthScope

__all__ = ["FakeTruthStore"]

_ORDINAL_SCOPES = ("book",)


class FakeTruthStore:
    def __init__(self, facts: list[TruthFact] | None = None) -> None:
        self._facts: list[TruthFact] = list(facts or [])

    # ── test affordance (not part of the port) ───────────────────────

    def add(self, fact: TruthFact) -> None:
        self._facts.append(fact)

    # ── the axis rule ────────────────────────────────────────────────

    @staticmethod
    def _check_axis(scope: TruthScope, as_of: int | datetime | None) -> None:
        if as_of is None:
            return
        if scope in _ORDINAL_SCOPES and isinstance(as_of, datetime):
            raise TypeError("book truth is positioned on story ordinals, not wall clock")
        if scope not in _ORDINAL_SCOPES and isinstance(as_of, int):
            raise TypeError("memory truth is positioned on wall clock, not story ordinals")

    @staticmethod
    def _covers(fact: TruthFact, at: int | datetime) -> bool:
        start, end = fact.valid_from, fact.valid_to
        # An unpositioned fact has no interval to cover a position with. Excluding it is
        # the same rule the graph as-of read applies to a positionless edge: untimed data
        # must not leak into a timed answer.
        if start is None:
            return False
        if at < start:
            return False
        if end is not None and at >= end:  # half-open
            return False
        return True

    # ── the port ─────────────────────────────────────────────────────

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
        self._check_axis(scope, as_of)
        out = [
            f for f in self._facts
            if f.scope == scope and f.subject_id == subject_id
            and f.confidence >= min_confidence
            and (as_of is None or self._covers(f, as_of))
        ]
        return out[:limit]

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
        self._check_axis(scope, as_of)
        out = [
            f for f in self._facts
            if f.scope == scope and f.confidence >= min_confidence
            and (query is None or query.lower() in f.value.lower()
                 or query.lower() in f.attribute.lower())
            and (as_of is None or self._covers(f, as_of))
        ]
        return out[:limit]
