"""The L0 slot registry — typed loader over ``contracts/pool/registry.json``.

``EPL-A2``: a module registers a slot's SHAPE in code; the pool loop fills its
MEMBERS per reality. This module is the Python half of that split, and it reads
the same file the Rust engine reads so the two cannot disagree (doc 40.12 §7 —
one source, one generated artifact, a drift test; the generation step is not
built yet, and ``registry.generated`` says so).

Two things the loader computes rather than reads, because both were findings:

* :attr:`Slot.axis` — ``BLD-A2``. The abstraction axis is derived from the slot's
  CONSUMERS, never from how its evidence looks. P20 grouped a sash, a spear and a
  string of pearls as "elongated things" because the prompt said *shape*; naming
  the consumers is what fixed it.
* :attr:`Slot.criteria_kind` — ``BLD-A1``. The operation, not the output shape,
  decides what can be checked without an answer key.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["Operation", "Visibility", "FieldRef", "Slot", "Registry", "load_registry"]

#: contracts/pool/registry.json, from services/lore-enrichment-service/app/pool/
_DEFAULT = pathlib.Path(__file__).resolve().parents[4] / "contracts" / "pool" / "registry.json"


class Operation(str, Enum):
    """What a planner does to its evidence (``BLD-A1``)."""

    PARTITION = "PARTITION"           # Ladder — a design axis cut into bands
    ABSTRACT = "ABSTRACT"             # Enumeration — n objects -> m categories, m < n
    CONFIRM = "CONFIRM"               # Profile — accept a default, or override with evidence
    CLASSIFY_LINK = "CLASSIFY_LINK"   # Composite — assign kinds, wire references


class Visibility(str, Enum):
    SHARED = "SHARED"     # other modules may reference its members (EPL-A7)
    PRIVATE = "PRIVATE"   # the owner only


@dataclass(frozen=True)
class FieldRef:
    """One member-body field, and what it points at."""

    name: str
    ref: str                 # "engine:<Enum>" | "slot:<slot_id>" | "" for a scalar
    is_list: bool = False
    required: bool = True

    @property
    def target_slot(self) -> str | None:
        return self.ref[5:] if self.ref.startswith("slot:") else None

    @property
    def engine_enum(self) -> str | None:
        return self.ref[7:] if self.ref.startswith("engine:") else None


@dataclass(frozen=True)
class Slot:
    id: str
    owner: str
    shape: str
    operation: Operation
    visibility: Visibility
    arity: tuple[int, int]
    suggest: tuple[int, int]
    member: tuple[FieldRef, ...] = ()
    consumed_by: tuple[str, ...] = ()

    @property
    def ordered(self) -> bool:
        return self.shape == "ordered"

    @property
    def axis(self) -> str:
        """``BLD-A2`` — derived from the consumers, never authored per slot.

        A slot with no registered consumer has no computable axis, and the loop
        must say so rather than invent one. That is not a defect in this code: it
        is `MEM-A4`'s finding surfacing again — item's contract keeps being blocked
        on other modules not having registered theirs.
        """
        if not self.consumed_by:
            return ""
        return " · ".join(self.consumed_by)

    def refs(self) -> tuple[FieldRef, ...]:
        return tuple(f for f in self.member if f.target_slot)


@dataclass
class Registry:
    slots: dict[str, Slot]
    engine_enums: dict[str, tuple[str, ...]]
    generated: bool = False
    unregistered: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, slot_id: str) -> Slot:
        return self.slots[slot_id]

    def consumers_of(self, slot_id: str) -> tuple[str, ...]:
        return self.slots[slot_id].consumed_by if slot_id in self.slots else ()

    def dangling_targets(self) -> dict[str, list[str]]:
        """Reference targets that no registered slot provides.

        Not an error. `EPL-A8` says a decision in one module routinely opens one in
        another, so a reference to an unregistered slot is the NORMAL way that
        demand becomes visible — it is the same fact as a `pool_reference` row with
        `to_member IS NULL`, one level up.
        """
        out: dict[str, list[str]] = {}
        for slot in self.slots.values():
            for f in slot.refs():
                if f.target_slot not in self.slots:
                    out.setdefault(f.target_slot or "?", []).append(f"{slot.id}.{f.name}")
        return out


def _field(name: str, spec: dict[str, Any]) -> FieldRef:
    return FieldRef(name=name, ref=spec.get("ref", ""),
                    is_list=bool(spec.get("list")), required=bool(spec.get("required", True)))


def load_registry(path: pathlib.Path | None = None) -> Registry:
    raw = json.loads((path or _DEFAULT).read_text(encoding="utf-8"))
    slots: dict[str, Slot] = {}
    for s in raw["slots"]:
        slots[s["id"]] = Slot(
            id=s["id"], owner=s["owner"], shape=s["shape"],
            operation=Operation(s["operation"]),
            visibility=Visibility(s["visibility"]),
            arity=(s["arity"][0], s["arity"][1]),
            suggest=(s["suggest"][0], s["suggest"][1]),
            member=tuple(_field(k, v) for k, v in (s.get("member") or {}).items()),
            consumed_by=tuple(s.get("consumed_by") or ()),
        )
    return Registry(
        slots=slots,
        engine_enums={k: tuple(v) for k, v in (raw.get("engine_enums") or {}).items()},
        generated=bool(raw.get("generated")),
        unregistered=dict(raw.get("_not_registered_yet") or {}),
    )
