"""CP-2.5 · P5 — the four fields, and no path that omits them.

Spec: ``ARCHITECTURE.md`` §5 (four fields, not five), §0.5 (what a guardrail is for), §0.14.3
(the `scope` of a withholding record). Checkpoint: RUNSTATE → L2 · CP-2.5.

**P5 failed as a retrofit for eleven consecutive rounds and it is not being retried here.** On the
legacy runtime *"every terminal path records"* is a claim about six INSERT sites, thirty mint sites
and five producers; eight fixes were attempted, each correct at the layer it named and blind to the
next. `finish_reason` covers **9.4%** of turns today.

So the property is not enforced, it is made **inexpressible**: an `Observation` has four required
fields and no defaults, so a path that omits one does not produce a partial record — it does not
produce an `Observation` at all, and it cannot end a turn. The same construction argument as M2 and
`Admitted[D]`.

WHAT IS DELIBERATELY NOT HERE
------------------------------
* **The wrong-object counter is not a P5 field** (§5, §0.6): *a counter without a detector ships
  reading zero.* Only substitution-shaped cases are detectable at the call, and the 61.8%
  carry-forward class is detectable only from plan-binding state — so its detector belongs with the
  plan (§0.11) and P5 merely carries the output when there is one.
* **`manifest_revision` is not here either** (CP-1.8): hashing an empty manifest is a
  constant-valued column at every write, which is the exact P4 violation CP-1 repaired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

#: §5 field 3 — `source` on every result. **58–66% of what the model sees as an error is our own
#: prose**, and until this exists that fraction of the signal is uninterpretable.
SOURCES = ("tool", "breaker", "meta")

#: C-14's typed outcome, which replaces `ok: bool`. **`ok=true` is untyped and means seven
#: different things**: 358 refusals rode the success channel, 400 empty results had four
#: indistinguishable causes, 430 results were silently truncated.
OUTCOMES = (
    "done", "partial", "empty", "ambiguous", "refused",
    "degraded", "deferred", "failed", "unknown_effect",
)


class NotObservable(ValueError):
    """A turn that cannot be recorded honestly. Raised rather than defaulted.

    Every field this refuses has a plausible default — `source="tool"`, `outcome="done"`,
    `advertised=()` — and every one of those defaults is a **constant written at a write
    boundary**, which is P4's violation exactly. A record that guesses is worse than a missing one:
    it is a missing one that counts.
    """


@dataclass(frozen=True, slots=True)
class Guardrail:
    """§0.5's guardrail, in its **v1 shadow arm**: evaluate, record, **do not act**.

    🔴 **PROPERTY 3 IS UNOBSERVABLE IF THE GUARDRAIL BLOCKS**, which is why the shadow arm is v1
    and not v2. The property is *"a strong model reaches the transition before the guardrail
    fires"*, and it is measurable only as **fire-rate falling toward zero as model strength
    rises**. A guardrail that acts destroys its own denominator: the turns where the model would
    have recovered on its own never happen, so the rate it produces is about the guardrail rather
    than about the model. *If it does not fall, we built a ceiling and mislabelled it* — and that
    sentence cannot be tested at all once the ceiling is in place.

    `acted` exists as a field rather than as a comment because **an invariant that is only
    documented is one this run has watched fail eleven times.** It is refused at construction, so
    "do not act" is not a rule someone must remember at the moment they are most sure the guardrail
    is right.

    `evidence` is required and must be **deterministic** (§0.5 property 1: an identical call
    repeated, a budget spent) — never a judgement about whether the model *seems* confused. A
    guardrail that fires on a judgement is the sixth breaker with a new name.
    """

    fired: bool
    evidence: str
    #: What it WOULD have proposed. §0.5: *a guardrail's output must be a PLAN STATE TRANSITION,
    #: not a stop.* Recorded even in the shadow arm, because the thing being measured is whether a
    #: strong model reached this transition first — and that comparison needs the transition.
    transition: str
    acted: bool = False

    def __post_init__(self) -> None:
        if self.acted:
            raise NotObservable(
                "the guardrail acted. v1 is a SHADOW ARM (§0.5): it evaluates, it records, and it "
                "does not act — because property 3 (`fire-rate falls toward zero as model strength "
                "rises`) is unobservable once the guardrail removes the turns it would be measured "
                "against. This is un-retrofittable: the data for a v2 decision only exists if v1 "
                "does not act."
            )
        if self.fired and not self.evidence.strip():
            raise NotObservable(
                "a guardrail fired with no evidence. §0.5 property 1: it fires on DETERMINISTIC "
                "evidence — an identical call repeated, a budget spent — never on a judgement "
                "about whether the model seems confused."
            )
        if self.fired and not self.transition.strip():
            raise NotObservable(
                "a guardrail fired with no transition. §0.5: its output must be a PLAN STATE "
                "TRANSITION, not a stop; a fire with nothing to move to IS the stop."
            )


@dataclass(frozen=True, slots=True)
class Observation:
    """One turn's P5 record. **Four fields, all required, no defaults.**

    A path that cannot answer one of these cannot build this object, so it cannot end a turn with a
    partial record. That is the whole mechanism — there is no validator to run and forget to run.
    """

    #: §5 field 1 — **an array PER PASS**, each `{pass, tool_choice, names}`. 🔴 A scalar `text[]`
    #: would record only the LAST pass and lose the mid-turn deletion this field exists to catch:
    #: arm E's silent deletion is invisible in production today precisely because no column answers
    #: *"what did this turn advertise, and when"*.
    advertised: tuple[dict, ...]
    #: §5 field 2 / §0.14.3 — `[{scope, …}]`. The shape is deliberately not `{tool, stage, reason}`:
    #: that admits NEITHER row the code writes, because it omits `pass` and requires `tool`, which
    #: the catalogue and pass scopes do not carry.
    withheld: tuple[dict, ...]
    source: str
    outcome: str
    guardrail: Guardrail = field(default_factory=lambda: Guardrail(False, "", ""))

    def __post_init__(self) -> None:
        if type(self.source) is not str or self.source not in SOURCES:
            raise NotObservable(
                f"source is {self.source!r}; it must be one of {SOURCES} (§5 field 3). A result "
                f"whose origin is unknown makes the error signal uninterpretable — 58-66% of what "
                f"the model sees as an error is our own prose."
            )
        if type(self.outcome) is not str or self.outcome not in OUTCOMES:
            raise NotObservable(
                f"outcome is {self.outcome!r}; C-14 replaced `ok: bool` with exactly {OUTCOMES}. "
                f"`ok=true` meant seven different things: 358 refusals rode the success channel."
            )
        seen: set[int] = set()
        for i, entry in enumerate(self.advertised):
            if type(entry) is not dict or set(entry) != {"pass", "tool_choice", "names"}:
                raise NotObservable(
                    f"advertised[{i}] is {entry!r}; each entry is exactly "
                    f"{{pass, tool_choice, names}} (§5 field 1)."
                )
            p = entry["pass"]
            if type(p) is not int or p < 1:
                raise NotObservable(f"advertised[{i}].pass is {p!r}; passes are 1-based ints")
            # 🔴 **TWO ENTRIES FOR ONE PASS IS THE SCALAR DEFECT WEARING THE ARRAY'S CLOTHES.** The
            # field is per-pass so a mid-turn deletion is visible; two rows for the same pass make
            # "what was advertised at pass 2" ambiguous, and every consumer that reads the first
            # one silently disagrees with every consumer that reads the last.
            if p in seen:
                raise NotObservable(
                    f"advertised has two entries for pass {p}. The array is per PASS — a duplicate "
                    f"makes the field answer two things at once, which is the scalar `text[]` "
                    f"defect this shape exists to avoid."
                )
            seen.add(p)
            if type(entry["names"]) is not tuple:
                raise NotObservable(
                    f"advertised[{i}].names is a {type(entry['names']).__name__}; a mutable or "
                    f"lazily-computed container is a record that can change after it is written"
                )


def observe(
    surfaces: Sequence,
    *,
    source: str,
    outcome: str,
    tool_choice: str = "auto",
    guardrail: Guardrail | None = None,
) -> Observation:
    """Build the record **from the surfaces that were actually assembled**.

    🔴 **DERIVED, NEVER HAND-TYPED.** The one thing this run has proved five times over is that a
    denominator a person maintains is a lower bound. `advertised` is exactly what each pass offered
    and `withheld` is exactly what each pass registered, both read off the `Surface` objects the
    assembler returned — so a pass that happened and was not recorded is not possible to express,
    rather than possible and discouraged.
    """
    return Observation(
        advertised=tuple(
            {"pass": s.pass_number, "tool_choice": tool_choice, "names": tuple(s.names)}
            for s in surfaces
        ),
        withheld=tuple(record for s in surfaces for record in s.withheld),
        source=source,
        outcome=outcome,
        guardrail=guardrail if guardrail is not None else Guardrail(False, "", ""),
    )


__all__ = ["Guardrail", "NotObservable", "OUTCOMES", "Observation", "SOURCES", "observe"]
