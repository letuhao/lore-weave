"""T37d — a plan revision closes the roles it no longer implies (SPEC §4.2b).

THE DEBT THIS PAYS
------------------
A role appended when a plan was designed outlives the plan that justified it. An as-of read
would then hand the canon guard a tie the book abandoned — the same *stale but confidently
served* failure T36 measured in the 175 already-closed `:RELATES_TO` edges being served as
currently true.

THE SAFETY PROPERTY, WHICH IS THE WHOLE FILE
--------------------------------------------
Roles have TWO producers. **This closes only `origin='plan'`.** An author's hand-declared tie
is not the plan's to remove, and before chain step 0066 nothing in `entity_facts` could tell
them apart — both were `fact_kind='relation'` with a NULL episode. A close without that mark
would have silently erased what a human deliberately said.

**A stale role is wrong; an erased one is gone.**

CLOSED, NOT DELETED
-------------------
The fact stays true for the interval it covered, so a chapter drafted under the old plan still
sees the role that was in force when it was written. Deleting rewrites history; invalidating
says the claim was never believed. A revision means neither.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.engine.planning_pipeline import (
    KG_EVENT_ORDER_CHAPTER_STRIDE,
    close_stale_planned_roles,
)

BOOK = uuid4()
USER = uuid4()


def _fact(fid: str, pred: str, value: str, origin: str | None = "plan", kind="relation"):
    return {"fact_id": fid, "fact_kind": kind, "attr_or_predicate": pred,
            "value": value, "origin": origin, "valid_to_ordinal": None}


class _Kal:
    def __init__(self, facts: dict[str, list[dict]], fail_read: bool = False):
        self._facts = facts
        self._fail_read = fail_read
        self.closed: list[dict] = []

    async def open_facts_for(self, book_id, entity_id, *, user_id=None):
        # Mirrors the real client: a failed read degrades to [] so a blind close does nothing.
        return [] if self._fail_read else list(self._facts.get(str(entity_id), []))

    async def close_fact(self, book_id, *, fact_id, valid_to_ordinal, user_id=None):
        self.closed.append({"fact_id": fact_id, "valid_to_ordinal": valid_to_ordinal})
        return {"fact_id": fact_id}


def _char(name, roles=None):
    return SimpleNamespace(name=name, roles=roles or [])


@pytest.mark.asyncio
async def test_a_role_the_revision_DROPPED_is_closed_at_the_holders_position():
    """The base case. The old plan had Kai betray Mira; the new one does not, so that role
    stops being in force from where Kai now stands — closed, not deleted, because the chapters
    already drafted under the old plan must still see it."""
    kal = _Kal({"ent-kai": [_fact("f1", "betrayed", "Mira")]})
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 5}, user_id=USER)
    assert n == 1
    assert kal.closed == [{"fact_id": "f1",
                           "valid_to_ordinal": 5 * KG_EVENT_ORDER_CHAPTER_STRIDE}]


@pytest.mark.asyncio
async def test_a_role_the_revision_STILL_implies_is_left_open():
    """Idempotence across re-plans. A plan re-run that changes nothing must close nothing —
    otherwise every planning run would silently end the roles it just re-asserted."""
    kal = _Kal({"ent-kai": [_fact("f1", "betrayed", "Mira")]})
    n = await close_stale_planned_roles(
        kal, BOOK,
        cast_objs=[_char("Kai", [{"predicate": "betrayed", "object": "Mira"}])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 5}, user_id=USER)
    assert n == 0 and kal.closed == []


@pytest.mark.asyncio
async def test_the_AUTHORS_role_is_NEVER_closed_by_a_plan_revision():
    """🔴 THE rule this whole task turned on. Before chain step 0066 there was no way to tell
    an author's declaration from the plan's, so this close would have erased a human's
    deliberate claim on a plan revision they may not even associate with it.

    A stale role is wrong; an erased one is gone.
    """
    kal = _Kal({"ent-kai": [
        _fact("f-plan", "betrayed", "Mira", origin="plan"),
        _fact("f-author", "sworn_to", "Ada", origin="author"),
    ]})
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 2}, user_id=USER)
    assert n == 1, "the plan's own stale role was not closed"
    assert [c["fact_id"] for c in kal.closed] == ["f-plan"], (
        "a plan revision closed a role the AUTHOR declared — that is not the plan's to remove")


@pytest.mark.asyncio
async def test_an_UNMARKED_legacy_fact_is_never_touched():
    """Everything written before chain step 0066 has `origin` NULL. Unmarked means unclaimed:
    this producer retracts only what it can prove it wrote, so a legacy role is left alone
    rather than swept up by whoever runs a plan next."""
    kal = _Kal({"ent-kai": [_fact("f-legacy", "betrayed", "Mira", origin=None)]})
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 1}, user_id=USER)
    assert n == 0 and kal.closed == [], "an unmarked legacy fact was retracted"


@pytest.mark.asyncio
async def test_a_non_relation_fact_is_never_closed_by_the_ROLE_producer():
    """`origin='plan'` will eventually mark more than roles. An attribute the plan wrote is
    not a role, and closing it here would make this function a general-purpose retractor of
    everything the planner ever said."""
    kal = _Kal({"ent-kai": [_fact("f-attr", "occupation", "monk", kind="attribute")]})
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 1}, user_id=USER)
    assert n == 0 and kal.closed == []


@pytest.mark.asyncio
async def test_a_BLIND_close_does_nothing_rather_than_guessing():
    """🔴 The degrade direction, and it is the one that matters. `open_facts_for` returns []
    when the read fails, so a KAL timeout means this retracts NOTHING.

    The opposite default — treating an unreadable state as "no roles wanted" — would close
    every plan-authored role in the book because a request timed out.
    """
    kal = _Kal({"ent-kai": [_fact("f1", "betrayed", "Mira")]}, fail_read=True)
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 1}, user_id=USER)
    assert n == 0 and kal.closed == [], (
        "a close ran against a state it could not read — a read timeout must retract nothing")
