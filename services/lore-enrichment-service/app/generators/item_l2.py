"""The item generator's L2 spine — the first thing that ever CONSUMES a freeze.

Everything before this produced contract. The pool was filled, validated, frozen to
a digest, and read by nobody, which meant `PPB-A6`'s claim — two layers separated by
a freeze — had never been under load. This module is the load.

It asks one question the architecture has been asserting an answer to since doc 03:

> Of the fifteen fields on `PL_007`'s ``ItemDefDecl``, how many does the contract
> layer actually supply?

`ICT-A2` says the item module's pool footprint is **small** and its bulk is tier 2,
which it produces itself. That is a claim with a number in it, and :func:`census`
computes the number rather than restating the claim.

The spine is the procedural half of `EPL-A6`'s internal two-layer split. It does not
name anything — naming is the vocabulary half, and a model does it. What the spine
owns is the part a model must not: **which archetypes exist, and what a legal value
is.** The frozen codes are a closed set, so a def whose class or tag is not in the
freeze is refused. That is the contract doing work rather than being documentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.pool.consume import MissingSlot, PoolView

__all__ = ["Source", "FieldSpec", "ITEM_DEF_FIELDS", "FieldCensus", "census",
           "ItemDefSkeleton", "plan", "accept", "Rejected"]

MODULE = "item"


class Source(str, Enum):
    """Where a field's value comes from — the only three possibilities."""

    FROZEN = "FROZEN"    # the contract layer supplies it, through the freeze
    OWN = "OWN"          # this generator produces it (vocabulary or magnitude)
    BLOCKED = "BLOCKED"  # the contract SHOULD supply it and no module registered it


@dataclass(frozen=True)
class FieldSpec:
    name: str
    source: Source
    #: For FROZEN/BLOCKED: the slot it reads. Empty for OWN.
    slot: str = ""
    why: str = ""


#: `PL_007` §5.1, field for field, in declaration order. The table is the finding:
#: it is not a plan for what to wire, it is the measurement of what the contract
#: reaches. Anything marked OWN is marked so for a stated reason — most often
#: `PGN-A5` (a magnitude is authored by whoever owns it, never by the contract) or
#: `EPL-A6` (vocabulary is this generator's own LLM half).
ITEM_DEF_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("def_id", Source.OWN, why="minted by this generator per instance of an archetype"),
    FieldSpec("display_name", Source.OWN, why="EPL-A6 vocabulary half — this generator's model names it"),
    FieldSpec("description", Source.OWN, why="EPL-A6 vocabulary half"),
    FieldSpec("class", Source.FROZEN, slot="item_archetype",
              why="engine-fixed ItemClass, chosen per archetype in the contract"),
    FieldSpec("affordance_overrides", Source.OWN,
              why="Option; None means the ItemClass default — PL_007 §5.3"),
    FieldSpec("equip", Source.FROZEN, slot="equip_slot",
              why="item owns equip_slot and registered it PRIVATE — no other module "
                  "references it yet, so SHARED would be a claim nothing supports"),
    FieldSpec("use_effect", Source.OWN, why="an effect is this generator's content, not a contract enum"),
    FieldSpec("max_charges", Source.OWN, why="PGN-A5 — a magnitude, authored by its owner"),
    FieldSpec("consume_on_exhaust", Source.OWN, why="per-def behaviour flag"),
    FieldSpec("price", Source.OWN, why="PGN-A5 — a magnitude"),
    FieldSpec("weight", Source.OWN, why="PGN-A5 — a magnitude"),
    FieldSpec("lex_tags", Source.BLOCKED, slot="lex_tag",
              why="WA_001 must register it — MEM-A4 §4.2, the last real gap in the "
                  "item contract and not item's to fix. It is now a REFERENCE on "
                  "item_archetype rather than a note in a document, so the register "
                  "reports the demand and this table agrees with it by construction"),
    FieldSpec("instrument_tags", Source.FROZEN, slot="instrument_tag",
              why="the PROG_001 + DF07 instrument_match operand — the seam that "
                  "already shipped (ICT-A3)"),
    FieldSpec("destructible", Source.OWN, why="per-def behaviour flag"),
)


@dataclass
class FieldCensus:
    frozen: tuple[str, ...]
    own: tuple[str, ...]
    blocked: tuple[tuple[str, str], ...]   # (field, why it is blocked, resolved live)

    @property
    def total(self) -> int:
        return len(self.frozen) + len(self.own) + len(self.blocked)

    @property
    def contract_reach(self) -> float:
        """Of the fields the CONTRACT is responsible for, how many it supplies.

        Deliberately not `frozen / total`. That number would fall as the generator
        grew fields of its own, which would read as the contract getting worse when
        nothing about the contract had changed. `ICT-A2`'s claim is about the
        contract's footprint, so the denominator is the contract's own scope.
        """
        owed = len(self.frozen) + len(self.blocked)
        return 0.0 if not owed else round(len(self.frozen) / owed, 4)


def census(view: PoolView) -> FieldCensus:
    """Resolve the field table against a real freeze.

    The table says which slot each contract field wants; the FREEZE says whether it
    is there. A field marked FROZEN whose slot is missing is counted as blocked —
    the table is a claim about intent and the freeze is the fact, and where they
    disagree the freeze wins.
    """
    frozen, own, blocked = [], [], []
    for f in ITEM_DEF_FIELDS:
        if f.source is Source.OWN:
            own.append(f.name)
            continue
        try:
            view.members(f.slot)
        except MissingSlot as e:
            blocked.append((f.name, str(e).split(".")[0]))
        else:
            frozen.append(f.name)
    return FieldCensus(tuple(frozen), tuple(own), tuple(blocked))


@dataclass
class ItemDefSkeleton:
    """One planned def: everything the CONTRACT fixes, and nothing the model owns."""

    archetype: str
    item_class: str
    instrument_tags: tuple[str, ...]
    #: The freeze this came from. A def that cannot name its contract version is a
    #: def nobody can re-derive.
    pool_digest: str = ""
    display_name: dict[str, str] = field(default_factory=dict)


def plan(view: PoolView) -> list[ItemDefSkeleton]:
    """One skeleton per archetype, filled only from the freeze."""
    out = []
    for m in view.members("item_archetype"):
        body = m.get("body") or {}
        out.append(ItemDefSkeleton(
            archetype=m["code"],
            item_class=body.get("class", ""),
            instrument_tags=tuple(body.get("instrument_tags") or ()),
            pool_digest=view.digest,
        ))
    return out


@dataclass(frozen=True)
class Rejected:
    archetype: str
    field_name: str
    value: object
    why: str


def accept(view: PoolView, defs: list[dict]) -> tuple[list[dict], list[Rejected]]:
    """Admit model-produced defs, refusing any value the freeze does not license.

    This is what makes the freeze a CONSTRAINT rather than a suggestion. The model
    writes names and descriptions — its own half — but `archetype`, `class` and
    `instrument_tags` are closed sets it did not choose, and a def that reaches
    outside them is refused with the offending value named.
    """
    archetypes = {m["code"]: (m.get("body") or {}) for m in view.members("item_archetype")}
    ok, bad = [], []
    for d in defs:
        arch = d.get("archetype")
        spec = archetypes.get(str(arch))
        if spec is None:
            bad.append(Rejected(str(arch), "archetype", arch,
                                f"not a frozen archetype; have {sorted(archetypes)}"))
            continue
        cls = d.get("class")
        if cls != spec.get("class"):
            bad.append(Rejected(str(arch), "class", cls,
                                f"the contract fixes {spec.get('class')!r} for this archetype"))
            continue
        # Against THIS archetype's tags, not against the union of all of them. The
        # first version checked membership in the global frozen set, which a live
        # run passed 14 of 14 — and would have passed just as happily if the model
        # had given the pearl cord the binding tag, because both codes are frozen.
        # A closed set that is not the RIGHT closed set is a check that admits the
        # error it was written for.
        allowed = set(spec.get("instrument_tags") or ())
        stray = [t for t in (d.get("instrument_tags") or []) if t not in allowed]
        if stray:
            bad.append(Rejected(str(arch), "instrument_tags", stray,
                                f"the contract gives {sorted(allowed)} to this archetype. A "
                                f"def may narrow that set, never reach outside it — a tag "
                                f"belonging to a different archetype is still the wrong tag"))
            continue
        ok.append({**d, "pool_digest": view.digest})
    return ok, bad
