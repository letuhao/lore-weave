"""T37b-planforge part 2 — the plan-time role producer (SPEC §4.2b).

WHAT THIS CLOSES
----------------
T36 measured `relation 0` in `entity_facts` and named that number T37's acceptance test. The
studio half moved it to 1 by hand. This is the half that writes the roles a PLAN implies, so
the number moves without an author typing anything.

WHY IT RUNS AFTER STAGE 3, NOT IN STAGE 0
-----------------------------------------
Stage 0 has the cast and the roster and could write immediately. It would write the roles at
the wrong position: **a role cannot be in force before its holder appears on the page.**
Stage 3's `introduce_at_chapter` is the answer to exactly that question, already clamped to
`[1, n_chapters]`, so the producer waits for it.

WHY IT NEVER RAISES — the opposite of the studio path, on purpose
------------------------------------------------------------------
`KalClient.append_role_fact` raises, and `routers/canon.py` lets it: an author must learn that
their declaration did not land. Here the caller is a pipeline whose every stage *"degrades
independently"*, and a KAL hiccup must not cost the user the plan they just waited for. A
missing role is a thinner canon check; a lost plan is the whole run.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.engine.planning_pipeline import (
    KG_EVENT_ORDER_CHAPTER_STRIDE,
    publish_planned_roles,
)

BOOK = uuid4()
USER = uuid4()


class _Kal:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[dict] = []
        self._fail_on = fail_on

    async def append_role_fact(self, book_id, **kw):
        if self._fail_on and kw.get("predicate") == self._fail_on:
            raise RuntimeError("KAL is down")
        self.calls.append({"book_id": book_id, **kw})
        return {"fact_id": str(uuid4())}


def _char(name: str, roles=None):
    return SimpleNamespace(name=name, roles=roles or [])


@pytest.mark.asyncio
async def test_a_planned_role_lands_at_the_HOLDERS_introduction_chapter():
    """🔴 The positioning rule. Kai is introduced at chapter 4, so the betrayal he commits
    opens at 4 000 000 — not at chapter 1, and not on composition's 1000-scale.

    Writing it earlier would put a role in force during chapters where its holder is not yet
    on the page, and the canon check would then enforce a tie the reader cannot have seen.
    """
    kal = _Kal()
    n = await publish_planned_roles(
        kal, BOOK,
        cast_objs=[_char("Kai", [{"predicate": "betrayed", "object": "Mira"}])],
        id_by_name={"Kai": "ent-kai"},
        introduce_at={"Kai": 4},
        user_id=USER,
    )
    assert n == 1 and len(kal.calls) == 1
    call = kal.calls[0]
    assert call["valid_from_ordinal"] == 4 * KG_EVENT_ORDER_CHAPTER_STRIDE == 4_000_000, (
        f"the role opened at {call['valid_from_ordinal']}; chapter 4 on the KG reading axis "
        f"is 4_000_000, and 4_000 would be composition's outline scale")
    assert call["subject_entity_id"] == "ent-kai"
    assert call["predicate"] == "betrayed"
    assert call["object_value"] == "Mira", (
        "the object must stay a NAME — resolving it to an id here would invent an identity "
        "claim the plan did not make")


@pytest.mark.asyncio
async def test_a_character_with_NO_introduction_opens_at_chapter_one():
    """An existing character has no `introduce_at_chapter` — they are already on the page, so
    their role is in force from the start rather than from nowhere."""
    kal = _Kal()
    await publish_planned_roles(
        kal, BOOK, cast_objs=[_char("Mira", [{"predicate": "allied_with", "object": "Kai"}])],
        id_by_name={"Mira": "ent-mira"}, introduce_at={"Mira": None}, user_id=USER)
    assert kal.calls[0]["valid_from_ordinal"] == KG_EVENT_ORDER_CHAPTER_STRIDE


@pytest.mark.asyncio
async def test_a_role_about_an_UNSEEDED_character_is_DROPPED_not_guessed():
    """`id_by_name` is the roster read back AFTER seeding. A character the glossary did not
    accept has no id, and writing its role against a guessed or minted one would attach a
    canon claim to the wrong entity — which is worse than the claim being absent."""
    kal = _Kal()
    n = await publish_planned_roles(
        kal, BOOK,
        cast_objs=[_char("Ghost", [{"predicate": "haunts", "object": "Kai"}]),
                   _char("Kai", [{"predicate": "betrayed", "object": "Mira"}])],
        id_by_name={"Kai": "ent-kai"},          # Ghost never seeded
        introduce_at={}, user_id=USER)
    assert n == 1, "a role was written for a character with no entity id"
    assert [c["subject_entity_id"] for c in kal.calls] == ["ent-kai"]


@pytest.mark.asyncio
async def test_a_KAL_failure_does_NOT_take_the_plan_down_and_the_rest_still_write():
    """🔴 The degrade rule, and the reason it is opposite to the studio endpoint's.

    Every stage of this pipeline degrades independently. A role that fails to write is a
    thinner canon check; an exception here would lose the plan the user waited minutes for.
    The surviving roles must still land — a partial write beats an all-or-nothing rollback of
    work the plan already did.
    """
    kal = _Kal(fail_on="betrayed")
    n = await publish_planned_roles(
        kal, BOOK,
        cast_objs=[_char("Kai", [{"predicate": "betrayed", "object": "Mira"},
                                 {"predicate": "mentors", "object": "Ada"}])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 2}, user_id=USER)
    assert n == 1, "the surviving role did not write after its sibling failed"
    assert kal.calls[0]["predicate"] == "mentors"


@pytest.mark.asyncio
async def test_a_cast_with_no_roles_writes_nothing_and_says_so():
    """The common case on an older model or a plan with no ties. Zero writes, zero calls —
    and the count returned is what the caller logs, so a silent no-op is distinguishable from
    a silent failure."""
    kal = _Kal()
    n = await publish_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai"), _char("Mira", [])],
        id_by_name={"Kai": "ent-kai", "Mira": "ent-mira"},
        introduce_at={"Kai": 1}, user_id=USER)
    assert n == 0 and kal.calls == []
