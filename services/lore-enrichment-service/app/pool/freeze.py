"""The freeze — the artifact that crosses the boundary between the two layers.

`PPB-A6` says the pipeline is two layers separated by a freeze, and that **no
module ever reads another module's L2 output**. Until now that was a rule written
in a document. The pool was produced, hashed, and read by nobody: the digest was
computed and thrown away, which means the load-bearing claim of the architecture
had never been under any load at all.

This is the artifact a consumer actually gets. Three decisions shape it:

**It carries its own digest, and the digest is checkable.** `verify()` recomputes
it from the members. An artifact whose hash is stored beside it and never
recomputed is a label, not a checksum — the pool could be edited on disk and every
consumer downstream would pin a digest that describes different bytes.

**It carries the UNMET demands forward.** A slot that no module registered is not
absent from the freeze; it is present as a named hole with the reference that wants
it. This is the whole difference between a refusal and a gap: a consumer that asks
for `equip_slot` must be told *"no module has registered it, and `item_archetype`
is waiting on it too"*, never handed an empty list that reads like *"there are no
equip slots in this world"*.

**It carries visibility, not just members.** `EPL-A7` splits SHARED from PRIVATE,
and a split nothing enforces is a comment. :mod:`app.pool.consume` is what enforces
it; this is what gives it something to enforce against.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any, Mapping

from app.pool.registry import Registry, Visibility

__all__ = ["FrozenSlot", "Unmet", "Freeze", "digest_of", "freeze_of", "closure_for",
           "consumers_of"]

#: Bumped when the artifact's SHAPE changes. A consumer refuses a version it does
#: not know rather than reading a field that has moved.
SCHEMA_VERSION = 1


def digest_of(pool: Mapping[str, list[dict]]) -> str:
    """Content-address the pool. Sorted, so the digest is of the CONTENT.

    Lives here rather than in :mod:`app.pool.loop` because the artifact and the
    function that verifies it must be the same function. Two implementations of
    "the digest" is how a checksum quietly stops checking.
    """
    canon = json.dumps(pool, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canon.encode("utf-8"), digest_size=32).hexdigest()


@dataclass(frozen=True)
class FrozenSlot:
    id: str
    owner: str
    visibility: Visibility
    members: tuple[dict, ...]

    def codes(self) -> tuple[str, ...]:
        return tuple(m["code"] for m in self.members if m.get("code"))


@dataclass(frozen=True)
class Unmet:
    """A reference target no module registered — carried forward, not dropped."""

    target: str
    wanted_by: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.target} (wanted by {', '.join(self.wanted_by)})"


@dataclass(frozen=True)
class Freeze:
    digest: str
    slots: Mapping[str, FrozenSlot]
    unmet: tuple[Unmet, ...] = ()
    #: Slots inside this consumer's closure that are PRIVATE to another module.
    #: Named but not carried: withholding the MEMBERS is what enforces `EPL-A7`,
    #: and naming the SLOT is what keeps "may not look" distinguishable from
    #: "is not there".
    withheld: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    @property
    def pool(self) -> dict[str, list[dict]]:
        return {sid: list(s.members) for sid, s in self.slots.items()}

    def verify(self) -> None:
        """Recompute the digest and refuse a mismatch.

        The reason this is a method and not a comment: a consumer pins the digest
        into whatever it generates, so a freeze whose bytes no longer match its
        label would put a truthful-looking provenance on untruthful content.
        """
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"freeze schema_version {self.schema_version}, this build reads "
                f"{SCHEMA_VERSION}. Refusing rather than reading a moved field."
            )
        actual = digest_of(self.pool)
        if actual != self.digest:
            raise ValueError(
                f"freeze digest mismatch: labelled {self.digest[:16]}…, content "
                f"hashes to {actual[:16]}…. The artifact was edited after it was "
                f"frozen, or the digest function changed."
            )

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.schema_version,
            "digest": self.digest,
            "slots": {sid: {"owner": s.owner, "visibility": s.visibility.value,
                            "members": list(s.members)}
                      for sid, s in sorted(self.slots.items())},
            "unmet": [{"target": u.target, "wanted_by": list(u.wanted_by)}
                      for u in self.unmet],
            "withheld": list(self.withheld),
        }, ensure_ascii=False, indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "Freeze":
        raw: dict[str, Any] = json.loads(text)
        return cls(
            digest=raw["digest"],
            schema_version=int(raw.get("schema_version", 0)),
            slots={sid: FrozenSlot(id=sid, owner=s["owner"],
                                   visibility=Visibility(s["visibility"]),
                                   members=tuple(s["members"]))
                   for sid, s in (raw.get("slots") or {}).items()},
            unmet=tuple(Unmet(target=u["target"], wanted_by=tuple(u["wanted_by"]))
                        for u in (raw.get("unmet") or [])),
            withheld=tuple(raw.get("withheld") or ()),
        )

    def write(self, path: pathlib.Path) -> None:
        path.write_text(self.to_json(), encoding="utf-8", newline="\n")

    @classmethod
    def read(cls, path: pathlib.Path) -> "Freeze":
        f = cls.from_json(path.read_text(encoding="utf-8"))
        f.verify()
        return f


def consumers_of(reg: Registry) -> set[str]:
    """Every module the registry knows about — owners and declared consumers alike.

    `consumed_by` entries are dotted paths (`loot.table`, `df07.stat_term.…`); the
    module is the first segment. These strings were authored to explain the
    abstraction axis (`BLD-A2`) and turn out to be the only place a pure consumer
    declares that it exists at all.
    """
    out = {s.owner for s in reg.slots.values()}
    for s in reg.slots.values():
        out |= {c.split(".")[0] for c in s.consumed_by if c}
    return out


def closure_for(reg: Registry, module: str) -> set[str]:
    """Every slot a module's contract depends on — what it owns, what it CONSUMES,
    and everything those point at.

    The seed was ownership alone until a generator that owns nothing was written.
    `loot` owns no slot; `item_archetype.consumed_by` has named `loot.table` since
    the slot was registered, and an ownership-seeded closure handed that module an
    empty set — a consumer with no contract, which is not a state the architecture
    has any account of. A module's needs are declared on the slots that name it, and
    that declaration was already there, being read by nothing.

    This exists because the first freeze was **pool-wide**, and three consecutive
    live runs failed to produce an artifact for a reason that had nothing to do with
    item: `progression_stage` would not settle, and item cannot reference it. Item's
    own contract was complete and unusable.

    That is `PPB-A5` inverted. *A planner is done when it is internally closed* —
    and "internally" is not "its own slots", because `item_archetype.gates_on`
    points at `progression_kind` and a consumer handed a code it cannot resolve has
    an artifact with a hole in it. The right unit is the **transitive closure of the
    references**, which is neither the module nor the whole pool.

    An unregistered target is not in the closure: it cannot be, and it travels as
    :class:`Unmet` instead.
    """
    seen: set[str] = set()
    stack = [s.id for s in reg.slots.values()
             if s.owner == module
             or any(c.split(".")[0] == module for c in s.consumed_by)]
    while stack:
        sid = stack.pop()
        if sid in seen or sid not in reg.slots:
            continue
        seen.add(sid)
        stack += [f.target_slot for f in reg[sid].refs() if f.target_slot]
    return seen


def freeze_of(reg: Registry, pool: Mapping[str, list[dict]],
              *, scope: set[str] | None = None,
              for_consumer: str | None = None) -> Freeze:
    """Build the artifact from a settled pool plus the registry that shaped it.

    ``scope`` narrows it to one consumer's closure (see :func:`closure_for`); the
    default is the whole pool. `unmet` is derived from
    :meth:`Registry.dangling_targets`, so the hole a consumer is told about is the
    SAME fact the abductive register reports — one source, two readers, rather than
    two lists that can disagree.

    ``for_consumer`` WITHHOLDS another module's PRIVATE slots from the bytes rather
    than relying on the reader to refuse itself. The closure drags them in — `loot`
    needs `item_archetype`, whose members carry `equip_slot` codes — so without this
    an artifact written for `loot` would ship item's private members to disk, and
    `EPL-A7` would be enforced only by the good manners of whoever opened the file.
    The withheld ids are still LISTED, because *may not look* and *is not there* are
    different answers and a consumer has to be able to tell them apart.
    """
    withheld = tuple(sorted(
        sid for sid, ms in pool.items()
        if (scope is None or sid in scope)
        and for_consumer is not None
        and reg[sid].visibility is not Visibility.SHARED
        and reg[sid].owner != for_consumer))
    members_by_slot = {sid: ms for sid, ms in pool.items()
                       if (scope is None or sid in scope) and sid not in withheld}
    dangling = {t: refs for t, refs in reg.dangling_targets().items()
                if scope is None or any(r.split(".")[0] in scope for r in refs)}
    return Freeze(
        digest=digest_of(members_by_slot),
        slots={sid: FrozenSlot(id=sid, owner=reg[sid].owner,
                               visibility=reg[sid].visibility,
                               members=tuple(ms))
               for sid, ms in members_by_slot.items()},
        unmet=tuple(Unmet(target=t, wanted_by=tuple(sorted(refs)))
                    for t, refs in sorted(dangling.items())),
        withheld=withheld,
    )
