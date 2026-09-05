"""What KIND of thing is this id? — the types the platform itself handed the model this turn.

🔴 THE DEFECT THIS CLOSES, MEASURED LIVE 2026-08-14 ON 3 OF 3 RUNS. Asked "Please write a chapter.
Add a new one after what I have, called The Drowned Road", from the chat panel, the model did the
sensible thing: it called ``book_list {kind: "chapters", book_id: <the book>}`` to see what was
there. The reply gave it ``chapter_id: 019ffcb5-bbff-…``. It then called ``book_chapter_create``
with ``book_id`` set to that CHAPTER id.

The platform refused with ``book not accessible`` — a sentence that is wrong twice over. The id is
not an inaccessible book; it is a chapter, and the user owns it. So the model had nothing to
correct against: it retried the identical call, then went looking for a book it COULD write to and
started reading an unrelated book of the user's. A bad refusal did not just fail the turn, it
pushed the turn out of its own scope.

🔴 WHY THE EXISTING REPAIR COULD NOT CATCH IT. ``_crosswired_ids`` (D-FJ-20) already fixes exactly
this shape — but only when the offending value is one of the THREE ids the server is holding for
the turn (book_id / chapter_id / project_id from the request envelope). On this turn there was no
editor context, so the server was not holding a chapter_id, and the model's value matched nothing.
The rule was right and its evidence base was too small.

The evidence base is the thing to widen. The platform did not merely *know* that
``019ffcb5-bbff-…`` is a chapter — it SAID SO, under the key ``chapter_id``, in a tool result it
returned seconds earlier through this very turn. An id the platform published under one name and
then received back under a different one is a cross-wire by construction. That needs no similarity
heuristic, no policy call and no surface gate; it is the same certainty standard D-FJ-20 already
uses, applied to a larger set of ids the server can vouch for.

**What this deliberately does NOT do.** It never guesses. A value the ledger has not seen is left
strictly alone — a valid-but-unknown UUID is still honoured as a deliberate cross-book call, which
is the invariant ``_inject_context_ids`` has protected since S02. It only ever reports the name a
value was published under, and only for values this turn produced.
"""
from __future__ import annotations

import re

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: How deep to walk a tool result. Results nest (``{"result": {"chapters": [{...}]}}``) but not
#: unboundedly, and an unbounded walk over a large listing is a per-call cost on the hot path.
_MAX_DEPTH = 6

#: Only keys that NAME a resource are recorded. `id` alone is excluded on purpose: it is the one
#: key whose meaning depends entirely on what contains it, so recording it would let a chapter's
#: bare `id` be reported as whatever the enclosing object happened to be.
_ID_KEY = re.compile(r"^[a-z][a-z0-9_]*_id$")


class IdLedger:
    """Turn-scoped: value -> the key name the platform published it under.

    First writer wins. A value published as ``chapter_id`` and later echoed inside some other
    envelope keeps its original, most specific meaning — and re-labelling on every sighting would
    make the ledger's answer depend on tool-call order.
    """

    __slots__ = ("_by_value",)

    def __init__(self) -> None:
        self._by_value: dict[str, str] = {}

    def record(self, payload, *, _depth: int = 0) -> None:
        """Walk a tool result and remember every ``*_id`` it announced."""
        if _depth > _MAX_DEPTH:
            return
        if isinstance(payload, dict):
            for k, v in payload.items():
                if isinstance(v, str) and _ID_KEY.match(str(k)) and _UUID.match(v):
                    self._by_value.setdefault(v, str(k))
                elif isinstance(v, (dict, list)):
                    self.record(v, _depth=_depth + 1)
        elif isinstance(payload, list):
            for v in payload:
                if isinstance(v, (dict, list)):
                    self.record(v, _depth=_depth + 1)

    def note(self, key: str, value: str | None) -> None:
        """Record a single known id — used for the turn's own context ids."""
        if value and _ID_KEY.match(key) and _UUID.match(str(value)):
            self._by_value.setdefault(str(value), key)

    def type_of(self, value: str | None) -> str | None:
        """The key name this value was published under, or None if this turn never saw it."""
        if not value:
            return None
        return self._by_value.get(str(value))

    def is_crosswired(self, key: str, value) -> bool:
        """True when `value` is an id this turn published under a DIFFERENT name.

        The whole test. Not "does it look like a chapter id" — UUIDs carry no type — but "did we
        ourselves hand this to the model as something else".
        """
        if not isinstance(value, str) or not _UUID.match(value):
            return False
        seen = self.type_of(value)
        return bool(seen) and seen != key

    def describe(self, value) -> str:
        """A refusal the model can act on: what this id actually is.

        ``book not accessible`` sent a live turn off to a different book entirely. Naming the type
        gives the model the one fact it needs to fix its own call.
        """
        seen = self.type_of(value)
        return f"that id is a {seen}, not a book_id" if seen else "unknown id"

    def __len__(self) -> int:  # pragma: no cover - diagnostics only
        return len(self._by_value)
