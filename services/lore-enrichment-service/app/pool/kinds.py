"""The planner KINDS — one per operation, none per slot (``BLD-A5``).

The falsifiable claim of this whole design lives here: **adding a slot must never
add a file.** A slot names its kind in the registry; this table resolves it. If a
sixth slot ever needs a fifth kind, `MOD-A1` is wrong and should be said so.

Each kind supplies three things and nothing else:

* :meth:`PlannerKind.probe` — the searches, derived from the slot (``ENR-A2``)
* :meth:`PlannerKind.ask`   — the prompt, carrying the OPERATION and the AXIS
* the criteria, which come from the operation and live in :mod:`app.pool.criteria`

What every kind refuses to do: assign ordinals (the planner does that — `QTY-A5`,
and round 4 measured the error class going to zero when the model stopped being
asked), choose a cardinality a derivation already fixed, or accept a member that
should have been a refusal (`BLD-A3` — refusal is a separate channel).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.pool.registry import Operation, Registry, Slot

__all__ = ["PlannerKind", "Enumeration", "ClassifyLink", "PLANNERS", "planner_for"]

_ENVELOPE = """Emit ONE JSON object, no prose and no code fence:

{
  "members": [
    { "code":   "<ascii snake_case, stable, immutable — what everything else references>",
      "name":   { "zh-Hant": "...", "en": "..." },
      "body":   { <the fields this slot declares; see below> },
      "provenance": "DECLARED|CANON|CITED|DERIVED|PROJECTED|PROPOSED",
      "evidence":   <CITED -> {"kind":"span","chunk":"..."}; DERIVED -> {"kind":"rule","from":"..."};
                     PROPOSED -> null. There is no genre pack in this run, so CANON is unavailable.> }
  ],
  "refused": [
    { "what": "...", "why": "...", "owner": "<the module that should own it instead>" }
  ]
}

Do not emit a rank or ordinal field: position and numbering belong to the engine.
Never emit a magnitude — no damage, price, weight, length, count, rate, duration.
"""


class PlannerKind(Protocol):
    operation: Operation

    def probe(self, slot: Slot, reg: Registry) -> list[str]: ...

    def ask(self, slot: Slot, reg: Registry, evidence: str, pool: dict) -> str: ...


def _axis_block(slot: Slot) -> str:
    """``BLD-A2`` — the axis is the consumers, and a slot with none says so."""
    if not slot.consumed_by:
        return ("NO REGISTERED CONSUMER for this slot yet, so its axis cannot be computed.\n"
                "Say what axis you are using and why, and mark the choice for human review.\n")
    return ("WHO CONSUMES THESE MEMBERS, AND WHAT THEY CONDITION ON — this decides the axis:\n"
            + "\n".join(f"  * {c}" for c in slot.consumed_by)
            + "\nGroup by what those consumers need to condition on. Grouping by how a thing\n"
              "LOOKS is the failure this instruction exists to prevent: \"long things\" is a true\n"
              "statement about a spear, a sash and a string of pearls, and no rule wants it.\n")


@dataclass
class Enumeration:
    """Operation: **ABSTRACT** — n observed objects become m categories, m < n."""

    operation: Operation = Operation.ABSTRACT

    def probe(self, slot: Slot, reg: Registry) -> list[str]:
        return [slot.id.replace("_", " "), *(c.split(".")[-1] for c in slot.consumed_by)]

    def ask(self, slot: Slot, reg: Registry, evidence: str, pool: dict) -> str:
        return f"""SLOT: {slot.id}   (unordered · arity {slot.arity} · propose {slot.suggest})

THE OPERATION IS ABSTRACTION.
  You are given N observed objects. Return M CATEGORIES, M meaningfully smaller
  than N. A category is what several different objects have in common.
  Naming each object once is a RENAMING, not an abstraction, and it is the exact
  failure this instruction exists to prevent.
  Each member carries "covers": the observed objects it applies to. At least one
  category must cover two or more.

{_axis_block(slot)}
Anything that is not a member of this slot at all goes in "refused", never in
"members", and never as a category named after its own exclusion.

{evidence}
{_ENVELOPE}"""


@dataclass
class ClassifyLink:
    """Operation: **CLASSIFY + LINK** — assign kinds and wire references."""

    operation: Operation = Operation.CLASSIFY_LINK

    def probe(self, slot: Slot, reg: Registry) -> list[str]:
        return [f"{slot.id} {f.name}" for f in slot.member]

    def ask(self, slot: Slot, reg: Registry, evidence: str, pool: dict) -> str:
        lines, avail = [], []
        for f in slot.member:
            if f.engine_enum:
                variants = reg.engine_enums.get(f.engine_enum, ())
                lines.append(f'  "{f.name}": one of {list(variants)}   '
                             f'(ENGINE-FIXED — a reality may not add a variant)')
            elif f.target_slot:
                codes = [m["code"] for m in pool.get(f.target_slot, [])]
                opt = "" if f.required else "  (optional)"
                if codes:
                    lines.append(f'  "{f.name}": {"list of " if f.is_list else ""}'
                                 f'codes from {f.target_slot}{opt}')
                    avail.append(f"  {f.target_slot}: {codes}")
                else:
                    lines.append(f'  "{f.name}": {f.target_slot} is NOT YET FILLED — '
                                 f'omit this field{opt}')
        return f"""SLOT: {slot.id}   (unordered · arity {slot.arity} · propose {slot.suggest})

THE OPERATION IS CLASSIFY + LINK.
  Each member is a KIND, not a named object — several observed objects may share one.
  Every body field is either an engine-fixed enum value or a CODE from another slot.
  Never a display name; codes are what everything references.

BODY FIELDS:
{chr(10).join(lines)}

AVAILABLE CODES:
{chr(10).join(avail) or "  (none yet)"}

{_axis_block(slot)}
Anything owned by another module goes in "refused" with that module named.

{evidence}
{_ENVELOPE}"""


#: `BLD-A5` — keyed by OPERATION, never by slot. Adding a slot adds a registry row.
PLANNERS: dict[Operation, PlannerKind] = {
    Operation.ABSTRACT: Enumeration(),
    Operation.CLASSIFY_LINK: ClassifyLink(),
}


def planner_for(slot: Slot) -> PlannerKind:
    try:
        return PLANNERS[slot.operation]
    except KeyError:  # pragma: no cover - reached only by an unbuilt kind
        raise NotImplementedError(
            f"slot {slot.id!r} declares operation {slot.operation.value}, which has no planner "
            f"kind yet. Built: {[o.value for o in PLANNERS]}. Adding one is an architecture "
            f"decision (MOD-A1), not a per-slot fix."
        ) from None


def parse(text: str) -> tuple[list[dict], list[dict]]:
    """Read the model's object back. A missing `refused` is [], never an error."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1].rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    doc = json.loads(t[i:j + 1])
    return list(doc.get("members") or []), list(doc.get("refused") or [])
