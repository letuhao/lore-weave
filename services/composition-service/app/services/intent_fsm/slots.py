"""The slot registry — what the FSM may ask for, in what order, and how each answer is written.

## Why a registry rather than a list of column names

Three different things need to agree about a slot and used to be able to drift apart:

1. **the order it is asked in** — closed sets first (spec §5): a weak model picks well from a set and
   invents badly, and each answered slot narrows the next, so the cheapest questions buy quality on
   the later ones for free;
2. **how its answer is COERCED** — `outline_node` holds these in five different Postgres types
   (`TEXT`, `SMALLINT`, `INT`, `JSONB`, and TEXT-with-a-closed-set), so "write the author's answer"
   is not one operation;
3. **its constraint class** — `closed` · `canon_open` · `blank_open`, which the POC needs recorded
   per slot to separate §5's effect from plain fatigue (spec §10 Q1).

Keeping them in one table means adding a slot is one entry, and a slot that is asked but cannot be
written is a construction-time error rather than a runtime surprise.

## The invariant that makes this safe (I-1)

**Every askable slot MUST be one the re-plan merge carries** (`OutlineRepo.INTENT_SLOTS`). A slot
outside that set is silently deleted by the next re-plan — the exact bug the merge precondition
(`dccf2393d`) was built to prevent, re-introduced one layer up and much harder to see. Asserted at
import time, so it can never be half-true.

That is why M1 does not ask `pov_entity_id` / `present_entity_ids` / `location_entity_id` even
though spec §5 names POV as an attractive closed set: the merge does not carry them yet. Asking for
them would be a data-loss bug wearing the costume of a feature.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.db.repositories.outline import OutlineRepo

ConstraintClass = Literal["closed", "canon_open", "blank_open"]


class SlotError(ValueError):
    """An answer that cannot be written to its column — surfaced as 422, never coerced silently."""


#: Mirrors `models._Short`. `outline_node.goal` is plain TEXT in Postgres but `_Short`
#: (max_length=2000) on the Pydantic model, so a longer write SUCCEEDS and then makes every
#: subsequent `get_node` on that node raise ValidationError — the node becomes unreadable to the
#: outline tree, the packer and the rail alike, long after the write that caused it. `settle_intent_slot`
#: writes raw SQL and therefore bypasses the model's own guard, so the bound has to be enforced here,
#: on the way IN, where it is still a 422 the author can act on.
_MAX_TEXT = 2000


def _text(v: Any) -> str:
    s = str(v).strip()
    if len(s) > _MAX_TEXT:
        raise SlotError(
            f"too long: {len(s)} characters (max {_MAX_TEXT}) — an intent slot is a phrase, "
            f"not a passage"
        )
    return s


def _bounded_int(lo: int, hi: int) -> Callable[[Any], int]:
    def coerce(v: Any) -> int:
        try:
            n = int(str(v).strip())
        except (TypeError, ValueError) as exc:
            raise SlotError(f"expected a whole number between {lo} and {hi}, got {v!r}") from exc
        if not lo <= n <= hi:
            raise SlotError(f"expected a number between {lo} and {hi}, got {n}")
        return n
    return coerce


def _positive_int(v: Any) -> int:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError) as exc:
        raise SlotError(f"expected a whole number, got {v!r}") from exc
    if n <= 0:
        raise SlotError(f"expected a positive number, got {n}")
    return n


def _exit_state(v: Any) -> dict[str, Any]:
    """SC12's versioned envelope. A bare string is NOT silently wrapped — the author would have no
    way to see that their sentence became `{"v":1,"note":"…"}` and the shape is validated elsewhere
    on write."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except ValueError as exc:
            raise SlotError("exit_state must be a JSON object, e.g. {\"v\":1,…}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise SlotError("exit_state must be a JSON object")


@dataclass(frozen=True)
class SlotSpec:
    name: str
    #: `outline_node`'s column type, for the parameterised cast in the apply UPDATE.
    pg_cast: str
    constraint_class: ConstraintClass
    #: What the column holds when the author declares the slot `absent`. Must match the column's
    #: NOT NULL / DEFAULT reality: a TEXT slot empties to '', a nullable one to None. Getting this
    #: wrong would make `decline` a 500 on exactly the slots the author most wants to decline.
    empty: Any
    coerce: Callable[[Any], Any]
    #: Shown to the author and given to the model as the question. Kept here, not in the prompt
    #: module, so a slot is defined in ONE place.
    question: str
    #: True ⇒ the closed set is resolved per-BOOK at runtime (the book's structure template), not a
    #: literal in this file. There is no global beat vocabulary — `arc_template.beats[].key` is it.
    dynamic_choices: bool = False
    choices: tuple[Any, ...] = ()


#: Ordered as the FSM asks them: closed sets first, then canon-grounded open, then the rest.
#: `tension` and `value_shift` are `closed` because the author picks from a bounded scale — a weak
#: model choosing "3 of 5" is a far more reliable act than it writing a sentence of stakes.
_SPECS: tuple[SlotSpec, ...] = (
    SlotSpec(
        "beat_role", "text", "closed", None, _text,
        "Which structural beat is this chapter?", dynamic_choices=True,
    ),
    SlotSpec(
        "value_shift", "smallint", "closed", None, _bounded_int(-100, 100),
        "Does the character's situation end better or worse than it started, and by how much "
        "(-100 … +100)?",
        choices=(-60, -30, 0, 30, 60),
    ),
    SlotSpec(
        "tension", "smallint", "closed", None, _bounded_int(1, 5),
        "How much pressure is on, 1 (calm) to 5 (breaking point)?",
        choices=(1, 2, 3, 4, 5),
    ),
    SlotSpec(
        "goal", "text", "canon_open", "", _text,
        "What is the POV character trying to get in this chapter?",
    ),
    SlotSpec(
        "conflict", "text", "canon_open", "", _text,
        "What stands in the way?",
    ),
    SlotSpec(
        "outcome", "text", "canon_open", "", _text,
        "How does it end — do they get it, lose it, or get it at a cost?",
    ),
    SlotSpec(
        "stakes", "text", "canon_open", "", _text,
        "What does the character lose if this goes wrong?",
    ),
    SlotSpec(
        "exit_state", "jsonb", "blank_open", None, _exit_state,
        "What has CHANGED by the end that the next chapter inherits?",
    ),
    SlotSpec(
        "story_time", "text", "blank_open", None, _text,
        "When does this happen in story time?",
    ),
    SlotSpec(
        "target_words", "int", "blank_open", None, _positive_int,
        "About how long should this chapter be, in words?",
    ),
)

SLOTS: dict[str, SlotSpec] = {s.name: s for s in _SPECS}

#: The canonical ask order (spec §5). The `reversed` POC arm is literally this, reversed — which is
#: what makes the two arms a controlled comparison rather than two different experiments.
SLOT_ORDER: tuple[str, ...] = tuple(s.name for s in _SPECS)

# ── I-1, asserted at import ──────────────────────────────────────────────────────────────────────
# A slot the FSM can settle but the re-plan merge does not carry is deleted by the next re-plan.
# Import-time so it is impossible to ship half of it; the message names the fix rather than just
# the violation, because the correct response is to widen the MERGE, never to weaken this check.
_UNCARRIED = [n for n in SLOT_ORDER if n not in OutlineRepo.INTENT_SLOTS]
if _UNCARRIED:  # pragma: no cover — a construction error, proven by test_slots.py
    raise RuntimeError(
        f"intent-FSM slots not carried by the re-plan merge: {_UNCARRIED}. "
        f"Add them to OutlineRepo.INTENT_SLOTS first — otherwise the author settles them and the "
        f"next re-plan silently deletes the answer (the bug dccf2393d exists to prevent)."
    )


def spec(slot: str) -> SlotSpec:
    """The registry lookup, and the ONLY sanctioned way a slot name reaches SQL (I-2).

    The apply step picks a COLUMN at runtime, so the name is interpolated into the UPDATE text.
    Membership here is what makes that safe: an unknown name raises instead of reaching the
    statement. Never interpolate a slot straight from a request."""
    s = SLOTS.get(slot)
    if s is None:
        raise SlotError(f"unknown intent slot: {slot!r}")
    return s


def plan_for(*, arm: str = "constrained_first",
             only: list[str] | None = None) -> list[str]:
    """The ordered slots in scope for one run.

    `only` lets a run be narrowed (spec §10 Q1 — whether a 10-question run exhausts the author is
    the thing being measured, so the machine must support both). Order always comes from
    SLOT_ORDER, never from the caller's list: a caller-ordered run would silently break the
    controlled comparison between arms.

    Deliberately NOT parameterised by node kind. A chapter and a scene carry the same columns and
    M1 asks both the same questions; a `kind` argument that was accepted and ignored would read as
    scene-aware behaviour that does not exist. Q2's delta-seeded scene run is where kind starts to
    matter, and it should arrive with the behaviour, not before it.
    """
    wanted = set(only) if only else set(SLOT_ORDER)
    unknown = wanted - set(SLOT_ORDER)
    if unknown:
        raise SlotError(f"unknown intent slots: {sorted(unknown)}")
    ordered = [n for n in SLOT_ORDER if n in wanted]
    if arm == "reversed":
        ordered.reverse()
    return ordered


def choices_for(slot: str, *, beats: list[dict[str, Any]] | None = None) -> list[Any]:
    """The closed set for a slot, resolved per-book where it is dynamic.

    `beat_role` has NO global vocabulary — the valid keys are the book's chosen structure template's
    beats (`arc_template.beats[].key`), which is why `resolve_structure` is the source here rather
    than a literal list. An unresolvable structure yields `[]`, and the caller must then treat the
    slot as open rather than as a closed set with nothing in it: offering an empty choice list is
    how a step silently becomes unanswerable.
    """
    s = spec(slot)
    if not s.dynamic_choices:
        return list(s.choices)
    return [str(b.get("key")) for b in (beats or []) if str(b.get("key") or "").strip()]


def effective_class(slot: str, *, beats: list[dict[str, Any]] | None = None) -> ConstraintClass:
    """The constraint class as it ACTUALLY applies to this run.

    `beat_role` is only `closed` if the book HAS a structure. With none resolved it degrades to
    `blank_open`, and the instrument must record what happened rather than what was intended — a
    POC that logs the declared class while the run experienced a different one measures nothing.
    """
    s = spec(slot)
    if s.dynamic_choices and not choices_for(slot, beats=beats):
        return "blank_open"
    return s.constraint_class


def render(slot: str, value: Any) -> str:
    """The canonical TEXT rendering used for metric B's `exact`/`drifted`/`dropped` comparison.

    Mechanical on purpose (spec §8): letting a model judge whether the author's words survived would
    be asking the thing under test to grade itself.
    """
    if value is None:
        return ""
    if spec(slot).pg_cast == "jsonb":
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
