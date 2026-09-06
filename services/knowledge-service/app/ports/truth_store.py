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

__all__ = [
    "AXIS_FOR_SCOPE",
    "Axis",
    "axis_for",
    "check_axis","TruthFact", "TruthScope", "TruthStore"]

# Which store owns the answer. Explicit, never inferred — see the module docstring.
TruthScope = Literal["book", "project", "global"]

# ── T45: valid-time is a SCOPE-DEPENDENT AXIS, declared once ─────────────────────────────
#
# 🔴 THE FACT LIVED IN THREE PLACES AND WAS NAMED IN NONE OF THEM. Measured 2026-08-14:
#
#   scoped_truth_store.py     `if scope == "book": glossary else memory`   (the routing)
#   glossary_truth_adapter    rejects a datetime                           (⇒ book is ordinal)
#   memory_truth_adapter      _SUPPORTED_SCOPES + rejects an int           (⇒ the rest is clock)
#
# Three files independently encoding one mapping, with nothing asserting they agree — the
# duplicated-constant drift shape this repo has already recorded for CSS vars and for the
# three FastMCP schema sources. Add a fourth scope and three files must be edited; move a
# scope between axes and two of them keep the old answer while the router sends traffic on
# the new one.
#
# So the mapping is DECLARED here and read by all three. `axis_for` is the only place that
# knows, and `test_every_scope_declares_an_axis` makes a new `TruthScope` member impossible
# to add without deciding its axis — which is precisely the design question T45 exists to
# answer rather than leave implicit.
Axis = Literal["story_ordinal", "wall_clock"]

#: Book truth is positioned by where the READER is — a chapter ordinal, monotone in the story
#: and meaningless as a timestamp. Memory truth is positioned by when something was TRUE for
#: the user — a wall clock, meaningless as a chapter. They are not two spellings of one axis:
#: an ordinal silently compares against a datetime (both order) and returns a confidently
#: wrong answer, which is the failure this port exists to prevent.
AXIS_FOR_SCOPE: dict[str, Axis] = {
    "book": "story_ordinal",
    "project": "wall_clock",
    "global": "wall_clock",
}


def axis_for(scope: str) -> Axis:
    """The axis a scope is positioned on. Raises for an unknown scope rather than defaulting.

    A default here would pick an axis for a scope nobody had thought about, and the wrong
    choice is silent: `as_of` would be accepted and the comparison would just answer wrongly.
    """
    try:
        return AXIS_FOR_SCOPE[scope]
    except KeyError:
        raise ValueError(
            f"no valid-time axis declared for scope {scope!r} — add it to AXIS_FOR_SCOPE "
            "(T45). A scope without an axis cannot be positioned, and guessing one is how an "
            "ordinal ends up compared against a clock."
        ) from None


def check_axis(scope: str, as_of: int | datetime | None) -> None:
    """Refuse an `as_of` that is on the wrong axis for this scope.

    ONE implementation, called by every adapter. The two adapters each had their own
    isinstance check before T45; they agreed, and nothing made them.

    ⚠️ `bool` is an `int` in Python, so `isinstance(True, int)` is True — a caller passing a
    boolean by mistake would otherwise be told it is a story ordinal. Both branches reject it
    on the type, which is what a positional argument that is neither must get.
    """
    if as_of is None:
        return
    axis = axis_for(scope)
    if axis == "story_ordinal" and isinstance(as_of, datetime):
        raise TypeError(
            f"{scope} truth is positioned on STORY ORDINALS; as_of must be an int chapter "
            f"position, got the datetime {as_of!r}. See T45."
        )
    if axis == "wall_clock" and not isinstance(as_of, datetime):
        # Raising beats coercing: the comparison would "work" (ints and datetimes both order)
        # and return a confidently wrong set of facts.
        raise TypeError(
            f"{scope} truth is positioned on WALL CLOCK; as_of must be a datetime, "
            f"got {as_of!r}. See T45 — the two axes are not interchangeable."
        )


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
