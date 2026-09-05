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


def _fact(fid: str, pred: str, value: str, origin: str | None = "plan", kind="relation",
          valid_from: int | None = None):
    """`valid_from` defaults to the ordinal `publish_planned_roles` would have opened a role
    at for a holder introduced at chapter 5 — the double's most important field, added after
    a live smoke found the close 422ing on every unmoved holder because this fake had no
    interval to violate. A double that omits a field the server VALIDATES cannot fail the way
    the server does."""
    return {"fact_id": fid, "fact_kind": kind, "attr_or_predicate": pred,
            "value": value, "origin": origin, "valid_to_ordinal": None,
            "valid_from_ordinal": 5 * KG_EVENT_ORDER_CHAPTER_STRIDE
            if valid_from is None else valid_from}


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
    kal = _Kal({"ent-kai": [_fact("f1", "betrayed", "Mira",
                                  valid_from=2 * KG_EVENT_ORDER_CHAPTER_STRIDE)]})
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"}, introduce_at={"Kai": 5}, user_id=USER)
    assert n == 1
    assert kal.closed == [{"fact_id": "f1",
                           "valid_to_ordinal": 5 * KG_EVENT_ORDER_CHAPTER_STRIDE}]


@pytest.mark.asyncio
async def test_the_close_is_never_at_or_BEFORE_the_facts_own_start():
    """🔴 THE LIVE BUG, and the fake KAL is why six green tests missed it.

    `publish_planned_roles` opens a role at `introduce_at * STRIDE`. This function closed it
    at the SAME expression — so for the ordinary revision, the one that drops a role and
    leaves its holder's introduction alone, `valid_to == valid_from`. The interval is
    half-open (`valid_from <= N < valid_to`), so that describes a span in which the fact was
    never true, and a real glossary rejects it:

        422 GLOSS_INVALID "valid_to_ordinal must be greater than the fact's valid_from_ordinal"

    Every close failed live. Nothing here caught it because the double had no
    `valid_from_ordinal` to contradict — the server validated a field the fake did not model.
    """
    at_3 = 3 * KG_EVENT_ORDER_CHAPTER_STRIDE
    kal = _Kal({"ent-kai": [_fact("f1", "betrayed", "Mira", valid_from=at_3)]})
    n = await close_stale_planned_roles(
        kal, BOOK, cast_objs=[_char("Kai", [])],
        id_by_name={"Kai": "ent-kai"},
        introduce_at={"Kai": 3},          # holder did NOT move — the common revision
        user_id=USER)
    assert n == 1
    got = kal.closed[0]["valid_to_ordinal"]
    assert got > at_3, (
        f"closed at {got} against a fact starting at {at_3} — a real glossary 422s this, and "
        "the role would stay open forever while the pipeline swallowed the error")
    assert got == at_3 + 1, "clamp to the MINIMUM legal span, not an invented chapter"


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
