"""The ONLY surface a generator gets on the frozen pool.

`PPB-A6` — *no module ever reads another module's L2 output* — has been a written
rule since doc 03. A written rule is not a mechanism, and this file is the attempt
to make it one. The mechanism is an **absence**: :class:`PoolView` has no method
that could return another module's generated content, so a generator cannot reach
it by being careless, only by importing something it has no business importing.
A test asserts the public surface is exactly these methods, which means ADDING such
an accessor turns the rule red instead of turning it into a code review.

Two refusals, both of which exist because the silent version is worse than the
error:

* **A slot no module registered** raises, naming who else is waiting on it. The
  alternative is returning `[]`, which reads as *"this world has no equip slots"*
  when the truth is *"nobody has decided yet"*. This project has now shipped that
  exact confusion twice, once in the register and once in the pool.
* **A PRIVATE slot belonging to someone else** raises. `EPL-A7` draws the SHARED /
  PRIVATE line and, until this file, nothing was on the other side of it.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.pool.freeze import Freeze
from app.pool.registry import Visibility

__all__ = ["PoolView", "MissingSlot", "NotVisible"]


class MissingSlot(LookupError):
    """Asked for a slot the freeze does not carry."""


class NotVisible(PermissionError):
    """Asked for a slot that is PRIVATE to another module (`EPL-A7`)."""


@dataclass(frozen=True)
class PoolView:
    """A frozen pool, as seen by one named consumer.

    ``consumer`` is the MODULE, not the caller — `item`, `progression`. It decides
    what PRIVATE means for this view, so it is required rather than defaulted: a
    view with no consumer would have to either see everything or nothing, and both
    make `EPL-A7` unenforceable.
    """

    freeze: Freeze
    consumer: str

    def __post_init__(self) -> None:
        if not self.consumer:
            raise ValueError("a view must name its consumer module (EPL-A7)")
        self.freeze.verify()

    @property
    def digest(self) -> str:
        """What a consumer pins into everything it generates."""
        return self.freeze.digest

    def visible_slots(self) -> tuple[str, ...]:
        return tuple(sorted(
            sid for sid, s in self.freeze.slots.items()
            if s.visibility is Visibility.SHARED or s.owner == self.consumer))

    def has(self, slot_id: str) -> bool:
        """Whether this consumer could read the slot — used to DEGRADE knowingly.

        Deliberately not the same question as "does the freeze contain it": a slot
        that exists but is not visible answers False here and still raises from
        :meth:`members`, because "I may not look" and "I looked and it was empty"
        must not collapse into one answer.
        """
        return slot_id in self.visible_slots()

    def members(self, slot_id: str) -> tuple[dict, ...]:
        slot = self.freeze.slots.get(slot_id)
        if slot is None:
            unmet = next((u for u in self.freeze.unmet if u.target == slot_id), None)
            if unmet is not None:
                raise MissingSlot(
                    f"{slot_id!r} is not in this freeze: no module has registered it, "
                    f"and {', '.join(unmet.wanted_by)} is waiting on it too. This is an "
                    f"open decision, NOT an empty set."
                )
            raise MissingSlot(
                f"{slot_id!r} is not in this freeze and nothing references it. "
                f"Present: {sorted(self.freeze.slots)}"
            )
        if slot.visibility is not Visibility.SHARED and slot.owner != self.consumer:
            raise NotVisible(
                f"{slot_id!r} is PRIVATE to {slot.owner!r} and this view is "
                f"{self.consumer!r} (EPL-A7)"
            )
        return slot.members

    def codes(self, slot_id: str) -> tuple[str, ...]:
        return tuple(m["code"] for m in self.members(slot_id) if m.get("code"))

    def member(self, slot_id: str, code: str) -> dict:
        for m in self.members(slot_id):
            if m.get("code") == code:
                return m
        raise MissingSlot(
            f"no member {code!r} in {slot_id!r}. Have: {list(self.codes(slot_id))}")

    def unmet(self) -> tuple[str, ...]:
        """The named holes, so a consumer can report what it could not source."""
        return tuple(str(u) for u in self.freeze.unmet)
