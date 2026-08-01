"""A second generator, and the reason it exists is to try to break the first one.

`item_archetype.consumed_by` has named `loot.table` since the slot was registered.
Until now that was a string in a JSON file; this is the module it names, and it is
here to answer one question that `PPB-A6` has been asserting an answer to:

> Can a generator that owns NO slot do its job from the contract alone, or does it
> need the item generator's L2 output?

If it needs the L2, `PPB-A6` is wrong and the whole two-layer split has to be
redesigned. So the test is arranged so that failure is a real outcome rather than
something the code is written to avoid: a loot table drops *things*, and the most
obvious reading of "thing" is a concrete `ItemDefDecl` that the item generator
produced.

The answer this module argues for is that a drop table references **archetypes**,
not defs — you roll *a sword*, and which sword is an instantiation decision made
later, by whoever owns instances (`ICT-A1`'s third tier). That keeps loot on the
contract side of the freeze. It is an argument, not a proof, and the place it would
break is stated in :func:`build`.

It also exists to give `EPL-A7` a live subject. `equip_slot` is PRIVATE to `item`,
and this module has a legitimate-sounding reason to want it — heavier armour in
better tiers — so the refusal happens in a real call rather than in a fixture.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pool.consume import MissingSlot, NotVisible, PoolView

__all__ = ["DropRow", "LootTable", "build", "what_it_could_not_reach"]

MODULE = "loot"


@dataclass(frozen=True)
class DropRow:
    """One row of a drop table.

    ``archetype``, never ``def_id``. That single field choice is the whole claim:
    a table that named concrete defs would be reading the item generator's output,
    and would have to be regenerated every time item regenerated.
    """

    archetype: str
    item_class: str
    #: The tags a consumer can condition on without leaving the contract.
    instrument_tags: tuple[str, ...]


@dataclass
class LootTable:
    rows: tuple[DropRow, ...]
    pool_digest: str
    #: What this generator asked the contract for and did not get. Reported, never
    #: silently degraded around — the whole failure class this pipeline keeps
    #: catching is a gap that reads like an answer.
    could_not_reach: tuple[str, ...] = ()


def what_it_could_not_reach(view: PoolView) -> tuple[str, ...]:
    """Ask for everything this generator would LIKE, and record the refusals.

    `equip_slot` is the honest case: a drop table would reasonably want to weight
    armour by where it is worn. It is PRIVATE to `item`, so this is the first place
    in the codebase where `EPL-A7` refuses a real call rather than a constructed
    one. The generator does not work around it — it reports it, and a human decides
    whether the slot should become SHARED.
    """
    out: list[str] = []
    for wanted in ("equip_slot", "lex_tag", "item_rarity"):
        try:
            view.members(wanted)
        except NotVisible as e:
            out.append(f"{wanted}: NOT VISIBLE — {e}")
        except MissingSlot as e:
            out.append(f"{wanted}: MISSING — {e}")
    return tuple(out)


def build(view: PoolView) -> LootTable:
    """A drop table over frozen archetypes.

    Where this argument would break: if a drop table ever needs to distinguish two
    concrete items of the SAME archetype — a common sword from a named one — then
    the row needs something the contract does not carry, and either the contract
    grows the distinction (a rarity or tier slot, which is contract-shaped) or
    `PPB-A6` is wrong. It is the first case so far, and the second has not been
    ruled out by anything except not having been reached.
    """
    rows = []
    for m in view.members("item_archetype"):
        body = m.get("body") or {}
        rows.append(DropRow(
            archetype=m["code"],
            item_class=body.get("class", ""),
            instrument_tags=tuple(body.get("instrument_tags") or ()),
        ))
    return LootTable(rows=tuple(rows), pool_digest=view.digest,
                     could_not_reach=what_it_could_not_reach(view))
