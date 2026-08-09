"""The `TruthStore` port (plan T19).

Facts, from whichever store owns them, behind one vocabulary. Two adapters exist **from the
start** — that is the point of the task, not an implementation detail:

  - `GlossaryTruthAdapter` — BOOK-scoped authored facts, owned by glossary-service
    (`entity_facts`, bitemporal, the substrate Phase 1 taught to answer `as_of`).
  - `MemoryTruthAdapter` — PROJECT and GLOBAL facts, owned by knowledge-service
    (`:Fact` nodes in the graph).

`ScopedTruthStore` routes between them and is the only thing consumers hold. **A consumer
must not be able to tell which one answered**, because Phase 8 (T44–T46) merges the two:
the Go bitemporal machinery — `maintain_chain`, the content-addressed natural key, the
half-open interval invariants — moves to Python and the stores become one. Every consumer
that learned which store it was talking to is a consumer Phase 8 has to rewrite.

── WHY SCOPE IS AN ARGUMENT AND NOT A GUESS ─────────────────────────────────────────────
Routing on "is book_id set?" would be an inference, and it breaks the moment a project-
scoped read happens to carry a book id for logging. `scope` is explicit, and the store
raises rather than guessing when the identifiers do not match it — a truth read that
silently answered from the wrong store is the worst failure available here, because both
stores return well-formed facts.

── VALID TIME MEANS DIFFERENT THINGS IN THE TWO STORES, AND T45 OWNS THAT ────────────────
Book truth is positioned on STORY ordinals (chapter positions). Memory truth is positioned
on WALL CLOCK. The plan names this as the one piece of Phase 8 that must be *designed*
rather than ported (T45: valid-time as a scope-dependent axis). This port therefore takes
`as_of` as an opaque position whose meaning follows the scope, and does NOT pretend the two
are interchangeable — `as_of=40` means chapter 40 in a book scope and is a type error in a
memory scope, where a datetime belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

__all__ = ["TruthFact", "TruthScope", "TruthStore"]

# Which store owns the answer. Explicit, never inferred — see the module docstring.
TruthScope = Literal["book", "project", "global"]


@dataclass(frozen=True)
class TruthFact:
    """One fact, in the shape both stores can honestly produce.

    Deliberately NOT the `:Fact` Pydantic model or glossary's fact DTO: those carry
    store-specific fields (`canonical_content`, `pending_validation`, `coverage_xid`) and a
    consumer that touched one would be pinned to that store. What survives here is what
    both actually have and every consumer actually needs.

    `valid_from` / `valid_to` are `int | datetime | None` because the two stores position
    facts on different axes — story ordinals and wall clock (see T45). The union is honest;
    a single type would force one store to lie.
    """

    fact_id: str
    subject_id: str | None
    attribute: str
    value: str
    scope: TruthScope
    confidence: float = 0.0
    valid_from: int | datetime | None = None
    valid_to: int | datetime | None = None
    source_ref: str | None = None


@runtime_checkable
class TruthStore(Protocol):
    """Implementations: `adapters/glossary_truth_adapter.py`,
    `adapters/memory_truth_adapter.py`, `adapters/scoped_truth_store.py` (the router that
    consumers hold), `adapters/fake_truth_store.py`."""

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
        """Facts about one subject, optionally at a position.

        `as_of=None` reads the current belief. With a position, only facts whose validity
        interval covers it are returned, half-open — `valid_from <= as_of < valid_to`, the
        same convention on both axes even though the axes differ.
        """
        ...

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
        """Facts matching a free-text query within a scope. `query=None` returns the
        scope's facts unfiltered, bounded by `limit` — which is why `limit` has a default
        rather than being optional: an unbounded truth read is how a context block stops
        being a context block."""
        ...
