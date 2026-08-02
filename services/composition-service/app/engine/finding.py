"""S3 — one vocabulary for why a heal finding did not become an edit.

What was wrong
--------------
Two heal pipelines produce findings and both carry a `skip_reason: str | None`, documented in
a trailing comment:

    self_heal.Finding      # not_located | overlap | edit_failed | edit_expanded
    plan_heal.PlanFinding  # not_found   | edit_failed | edit_expanded

Three defects in four lines.

1. **`not_located` and `not_found` are the same concept under two names.** Both mean *the text
   the judge quoted could not be located in the thing being edited*. One name for one concept
   is a rule this repo already enforces on the frontend-tool surface; the heal path had two.

2. **The declared list is INCOMPLETE, and a consumer depends on what it omits.** `self_heal`
   also writes `refuted` (a skeptical verify dropped the finding) and `noop` (the "fix" equals
   the text it replaces — the auditor emits ~25% of these). Neither appears in the comment,
   and `worker/operations.py` counts `f.skip_reason == "refuted"` to report how many findings
   the verifier killed. So the documentation was already false, and the undocumented member
   was the load-bearing one.

3. **Both are free strings**, so a typo at an assignment site produces a finding that is
   silently un-countable: `operations.py` would report `refuted: 0` on a run where every
   finding was refuted, and nothing anywhere would raise.

A closed enum plus a mechanical check that no assignment site invents a new string is the
smallest thing that fixes all three, and it is the same shape as `CriticStatus`: the members
ARE the vocabulary, and the check is that the producers cannot write outside it.

What is deliberately NOT merged
-------------------------------
`glossary_build`'s items also have a `skip_reason` — and it is a **free-text sentence** shown
to a human (*"the glossary already has an entry with this name"*), persisted in a `TEXT`
column. Same spelling, different concept: one is a closed machine vocabulary, the other is
prose. Folding them together would be the one-name-two-concepts drift this module exists to
end, arrived at from the other direction — so it stays separate, and this note is why.
"""
from __future__ import annotations

from enum import StrEnum

__all__ = ["SkipReason"]


class SkipReason(StrEnum):
    """Why a heal finding did not become an applied edit.

    `StrEnum`, NOT `class SkipReason(str, Enum)` — and the difference is not cosmetic.

    The first version was `(str, Enum)`, which makes `== "refuted"` work (it is a `str`
    subclass) and JSON-serialise correctly, so every unit test passed. But `str()` and
    f-string interpolation return **`"SkipReason.NOOP"`**, not `"noop"` — so any consumer that
    FORMATS a skip_reason rather than comparing it would silently start emitting the member
    path. Every test here used `==`; none could see it. A live self-heal run printed
    `skip_reasons seen: ['SkipReason.NOOP']` and that is how it was found.

    `StrEnum` overrides `__str__` to return the value, so comparison, formatting and
    serialisation all agree.
    """

    #: The quoted span could not be found in the chapter/outline being edited. This is the
    #: member `plan_heal` used to spell `not_found`; the two were always one concept.
    NOT_LOCATED = "not_located"
    #: The span overlaps an already-accepted edit, so applying it would double-splice.
    OVERLAP = "overlap"
    #: The splice itself failed.
    EDIT_FAILED = "edit_failed"
    #: The replacement grew far beyond the span it replaces — the satellite guard. A span edit
    #: must stay local, or a "fix" quietly rewrites the passage around it.
    EDIT_EXPANDED = "edit_expanded"
    #: A skeptical verify pass refuted the finding. UNDOCUMENTED before this module existed,
    #: and the one `worker/operations.py` actually counts.
    REFUTED = "refuted"
    #: The proposed replacement equals the text it would replace. Dropped in code because the
    #: auditor emits these in volume and a human should never be shown a no-op edit.
    NOOP = "noop"
