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

from app.pool.registry import Operation, Registry, Slot

__all__ = ["PlannerKind", "Enumeration", "ClassifyLink", "Ladder", "Profile",
           "PLANNERS", "planner_for"]

#: The ABSTRACT operation requires this and no slot body declares it.
_COVERS = '      "covers": [ "<an observed object this category applies to>", ... ],\n'


def _envelope(operation_field: str = "") -> str:
    """The output shape, with room for a field the OPERATION requires.

    ``covers`` was the case that forced this. It is demanded by ABSTRACT and it is
    not a slot body field, so for a slot declaring ``member: {}`` the envelope named
    nowhere legal to put it — and the model duly invented a different home on each
    run (``body.covers`` once, ``body.instrument_match`` the next). Two live runs
    failed on placement while the answer underneath was fine, and the first fix went
    into the CHECKER, teaching it to look in both places. That is treating the
    instrument. The requirement belongs in the envelope that states it.
    """
    return f"""Emit ONE JSON object, no prose and no code fence:

{{
  "members": [
    {{ "code":   "<ascii snake_case, starts with a letter — what everything else references>",
      "name":   {{ "zh-Hant": "...", "en": "..." }},
{operation_field}      "body":   {{ <the fields this slot declares, and NOTHING else; see below> }},
      "provenance": "DECLARED|CANON|CITED|DERIVED|PROJECTED|PROPOSED",
      "evidence":   <CITED -> {{"kind":"span","chunk":"..."}}; DERIVED -> {{"kind":"rule","from":"..."}};
                     PROPOSED -> null. There is no genre pack in this run, so CANON is unavailable.> }}
  ],
  "refused": [
    {{ "what": "...", "why": "...", "owner": "<the module that should own it instead>" }}
  ]
}}

Every field above is either named here or named under BODY FIELDS. Do not add one.
Do not emit a rank or ordinal field: position and numbering belong to the engine.
Never emit a magnitude — no damage, price, weight, length, count, rate, duration.
"""


class PlannerKind:
    """The three things a kind supplies, and the one thing most kinds do not.

    ``finalize`` is the planner's last word: it runs **after the criteria have
    passed and the human gate has approved**, never before. That ordering is the
    whole point for :class:`Ladder` — if the planner stamped ordinals before
    validation, the criterion that forbids a model-assigned ordinal would be
    reading the planner's own field and could never fail (``NV-1``).
    """

    operation: Operation

    def probe(self, slot: Slot, reg: Registry) -> list[str]:
        raise NotImplementedError

    def ask(self, slot: Slot, reg: Registry, evidence: str, pool: dict) -> str:
        raise NotImplementedError

    def finalize(self, slot: Slot, members: list[dict]) -> list[dict]:
        """Identity for every kind whose output carries no planner-assigned field."""
        return members


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
class Enumeration(PlannerKind):
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
{_envelope(_COVERS)}"""


@dataclass
class ClassifyLink(PlannerKind):
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
{_envelope()}"""


def _codes_of(reg: Registry, pool: dict, target: str) -> list[str]:
    return [m["code"] for m in pool.get(target, []) if m.get("code")]


@dataclass
class Ladder(PlannerKind):
    """Operation: **PARTITION** — one design axis cut into ordered bands.

    The distinguishing move is not "produce a list"; it is **where the cuts go**.
    So the prompt asks for the boundary, not for the band: a band is only real if
    you can say what a practitioner cannot do below it and can do above it. Bands
    that differ only in how much of the same thing you have are a magnitude, and
    a magnitude belongs to the owning generator, never to a contract slot.

    Ordinals never leave the model. ``finalize`` stamps them from the order the
    model returned, per group, once the set has settled (``QTY-A5``).
    """

    operation: Operation = Operation.PARTITION

    def probe(self, slot: Slot, reg: Registry) -> list[str]:
        base = slot.id.replace("_", " ")
        return [base, f"{base} boundary", *(c.split(".")[-1] for c in slot.consumed_by)]

    def ask(self, slot: Slot, reg: Registry, evidence: str, pool: dict) -> str:
        groups = [f for f in slot.member if f.target_slot]
        blocks, avail = [], []
        for f in groups:
            codes = _codes_of(reg, pool, f.target_slot or "")
            blocks.append(f'  "{f.name}": a code from {f.target_slot}')
            avail.append(f"  {f.target_slot}: {codes or 'NOT YET FILLED'}")
        return f"""SLOT: {slot.id}   (ordered · arity {slot.arity} · propose {slot.suggest})

THE OPERATION IS PARTITION.
  You are cutting an axis into BANDS, in ascending order. A band is real only if
  you can name what changes AT ITS LOWER BOUNDARY — something a practitioner
  cannot do below it and can do at or above it.
  A band that differs from the one below it only by HAVING MORE of the same thing
  is not a band; it is a magnitude, and magnitudes belong to the generator that
  owns them, not to this contract. Merge or refuse it.
  Return the bands in ASCENDING order. Do NOT number them, rank them, or give any
  of them a level: the ORDER you return is the answer, and the planner assigns the
  numbers.

BODY FIELDS:
{chr(10).join(blocks) or "  (none)"}

AVAILABLE CODES:
{chr(10).join(avail) or "  (none yet)"}

  ONE MEMBER PER BAND — never one member per code. The listed codes are the GROUPS
  you sort bands into; they are not themselves the answer. Returning the code list
  back as members is the failure this paragraph exists to prevent.

  The shape, which says nothing about the content:
      {{"code": "<first band of A>",  "body": {{"kind": "A"}}}}
      {{"code": "<second band of A>", "body": {{"kind": "A"}}}}
      {{"code": "<third band of A>",  "body": {{"kind": "A"}}}}
      {{"code": "<first band of B>",  "body": {{"kind": "B"}}}}
      {{"code": "<second band of B>", "body": {{"kind": "B"}}}}

  A code gets AT LEAST TWO bands or it gets none: a code you cannot cut into two
  distinguishable bands goes wholly in "refused", with what is absent as the reason.
  That is a real answer, not a gap — forcing a ladder onto an axis that has none is
  the other failure to avoid.

{_axis_block(slot)}
{evidence}
{_envelope()}"""

    def finalize(self, slot: Slot, members: list[dict]) -> list[dict]:
        """`QTY-A5` — order in, ordinals out. Runs only after the set has settled.

        Round 4 measured the ordinal error class going to zero the moment the model
        stopped being asked for a number, so it is not asked, and this is where the
        numbers come from instead: list position within each group, 1..N.
        """
        group_field = next((f.name for f in slot.member if f.target_slot), None)
        seen: dict[str, int] = {}
        out: list[dict] = []
        for m in members:
            g = str((m.get("body") or {}).get(group_field, "")) if group_field else ""
            seen[g] = seen.get(g, 0) + 1
            out.append({**m, "ordinal": seen[g]})
        return out


@dataclass
class Profile(PlannerKind):
    """Operation: **CONFIRM** — a declared default, kept or overridden with evidence.

    The only kind that starts from an answer. Its failure mode is the opposite of
    every other kind's: not "invented too much" but "agreed with everything". So
    the prompt makes dropping a default a first-class move and the criteria make
    ADDING one cost evidence, which is the asymmetry the operation actually has —
    the platform already carried the burden of proof for what it declared.
    """

    operation: Operation = Operation.CONFIRM

    def probe(self, slot: Slot, reg: Registry) -> list[str]:
        return [d.replace("_", " ") for d in slot.default]

    def ask(self, slot: Slot, reg: Registry, evidence: str, pool: dict) -> str:
        declared = "\n".join(f"  - {d}" for d in slot.default)
        return f"""SLOT: {slot.id}   (unordered · arity {slot.arity} · propose {slot.suggest})

THE OPERATION IS CONFIRM.
  A default set is already declared below. Your job is to decide, for each entry,
  whether this reality HAS it — and then whether it is missing anything.

  KEEP an entry     -> emit it unchanged, provenance DECLARED, evidence null.
  DROP an entry     -> do not emit it; put it in "refused" naming what is absent.
  ADD an entry      -> emit it with CITED or DERIVED provenance AND its evidence.
                       An addition costs evidence because the declared entries
                       already carry theirs; an addition with none is rejected.

  Keeping everything unchanged is a legitimate answer and needs no justification.
  Dropping is equally legitimate: a track this reality does not run is not a gap.

THE DECLARED DEFAULT:
{declared}

{_axis_block(slot)}
{evidence}
{_envelope()}"""


#: `BLD-A5` — keyed by OPERATION, never by slot. Adding a slot adds a registry row.
PLANNERS: dict[Operation, PlannerKind] = {
    Operation.ABSTRACT: Enumeration(),
    Operation.CLASSIFY_LINK: ClassifyLink(),
    Operation.PARTITION: Ladder(),
    Operation.CONFIRM: Profile(),
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
