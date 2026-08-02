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

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["SkipReason", "Locator", "LocatorKind"]


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


# ── S3 · one locator ──────────────────────────────────────────────────────────────────────


class LocatorKind(StrEnum):
    """WHERE a finding is. One closed set across every producer.

    Five producers carry five locators today and none of them can be read by anything but its
    own module: `self_heal.Finding` has `(start, end)` char offsets, `plan_heal.PlanFinding`
    has `chapter`/`scene`, `stitch` has a `(left_scene, right_scene)` seam pair,
    `error_block_heal.MergedFinding` has `block_ids` + offsets, and `CanonViolation` has an
    entity id plus the matched surface form. Two of the five are hand-serialised into a
    payload, in two different shapes; three never leave their module at all.

    `StrEnum` for the reason `SkipReason` documents: `(str, Enum)` formats as `"LocatorKind.
    SPAN"` in an f-string while comparing equal to `"span"`, so every `==` test passes and
    every rendered string is wrong.
    """

    #: Character offsets into a specific text, plus the quote they were found from.
    SPAN = "span"
    #: A position in the plan: 1-based chapter + scene.
    SCENE = "scene"
    #: The JOIN between two scenes — a finding that belongs to neither one alone.
    SEAM = "seam"
    #: One or more editor blocks, by id.
    BLOCKS = "blocks"
    #: An entity, plus the surface form that matched in the text.
    ENTITY = "entity"
    #: The judge found something and NOTHING could place it.
    #:
    #: This is the member the union is worth building for. `self_heal` expresses it today as
    #: `located=None`, which reaches a human only as a smaller `located` COUNT — so a run that
    #: finds six problems and places none reports "0 edits" and the panel says *"No issues
    #: found — the prose is clean."* A check that ran, found things, could not point at them,
    #: and reported CLEAN is the exact defect this whole cycle has been closing. Making
    #: "nowhere" a locator rather than an absent one is what lets a consumer say so.
    UNLOCATED = "unlocated"


@dataclass(frozen=True)
class Locator:
    """Where one finding is, in a shape any consumer can read.

    A tagged union rather than five optional fields: a consumer switches on `kind` and a
    producer cannot half-fill two of them. Every field beyond `kind` is optional because each
    kind uses a different subset — which is the honest shape for a union in a language without
    them, and why `describe()` exists so a consumer never has to know the subset.

    `trace_span_id` is on EVERY kind, reserved by spec §S3 and deliberately unused today: the
    spec's own note is that `span | scene_index | node_id` cannot express *which lens produced
    this*, and that is what the trace makes addressable. Reserved rather than invented, because
    composition emits no trace spans yet (tracked in Debt) — a field with a producer and no
    consumer is the shape this run keeps finding, and so is its mirror.
    """

    kind: LocatorKind
    #: SPAN / BLOCKS — offsets into the text the finding is about.
    start: int | None = None
    end: int | None = None
    #: SPAN / ENTITY / UNLOCATED — the verbatim text the judge quoted. Kept even when the
    #: offsets are known: the quote is what a human recognises, the offsets are what a splice
    #: needs, and the two answer different questions.
    quote: str = ""
    #: SCENE / SEAM — 1-based positions in the plan.
    chapter: int | None = None
    scene: int | None = None
    right_scene: int | None = None
    #: BLOCKS — editor block ids.
    block_ids: tuple[str, ...] = ()
    #: ENTITY — the entity, and the surface form that matched.
    entity_id: str | None = None
    matched: str = ""
    #: UNLOCATED — why nothing could place it. A `SkipReason` value where one applies.
    why: str = ""
    #: Reserved (spec §S3). See the class docstring.
    trace_span_id: str | None = None

    @classmethod
    def span(cls, start: int, end: int, quote: str = "", **kw) -> "Locator":
        return cls(LocatorKind.SPAN, start=start, end=end, quote=quote, **kw)

    @classmethod
    def scene_at(cls, chapter: int, scene: int, **kw) -> "Locator":
        return cls(LocatorKind.SCENE, chapter=chapter, scene=scene, **kw)

    @classmethod
    def seam(cls, left_scene: int, right_scene: int, **kw) -> "Locator":
        return cls(LocatorKind.SEAM, scene=left_scene, right_scene=right_scene, **kw)

    @classmethod
    def blocks(cls, block_ids, start: int | None = None, end: int | None = None,
               **kw) -> "Locator":
        return cls(LocatorKind.BLOCKS, block_ids=tuple(block_ids), start=start, end=end, **kw)

    @classmethod
    def entity(cls, entity_id: str | None, matched: str = "", quote: str = "",
               **kw) -> "Locator":
        return cls(LocatorKind.ENTITY, entity_id=entity_id, matched=matched, quote=quote, **kw)

    @classmethod
    def nowhere(cls, quote: str = "", why: str = "") -> "Locator":
        """A finding nothing could place. `why` is a `SkipReason` value where one applies."""
        return cls(LocatorKind.UNLOCATED, quote=quote, why=str(why) if why else "")

    @property
    def placed(self) -> bool:
        """False ⇒ the finding exists and points nowhere. The count a report must not hide."""
        return self.kind is not LocatorKind.UNLOCATED

    def as_payload(self) -> dict:
        """The wire shape. Empty/None members are dropped EXCEPT `kind` and `placed`.

        `placed` is emitted redundantly on purpose: a consumer that has not learned every
        member of `LocatorKind` can still tell a placed finding from an unplaced one, so
        adding a sixth kind cannot silently turn "nowhere" into "somewhere" in an old reader.
        """
        out: dict = {"kind": str(self.kind), "placed": self.placed}
        for name in ("start", "end", "quote", "chapter", "scene", "right_scene",
                     "entity_id", "matched", "why", "trace_span_id"):
            value = getattr(self, name)
            if value not in (None, "", ()):
                out[name] = value
        if self.block_ids:
            out["block_ids"] = list(self.block_ids)
        return out

    def describe(self) -> str:
        """One short human phrase. Not translated — this is a log/diagnostic string; the
        user-facing wording lives in the frontend's i18n bundle, keyed on `kind`."""
        if self.kind is LocatorKind.SPAN:
            return f"chars {self.start}-{self.end}"
        if self.kind is LocatorKind.SCENE:
            return f"chapter {self.chapter}, scene {self.scene}"
        if self.kind is LocatorKind.SEAM:
            return f"between scenes {self.scene} and {self.right_scene}"
        if self.kind is LocatorKind.BLOCKS:
            return f"blocks {', '.join(self.block_ids)}"
        if self.kind is LocatorKind.ENTITY:
            return f"entity {self.entity_id}" + (f" ({self.matched})" if self.matched else "")
        return "not located" + (f": {self.why}" if self.why else "")
