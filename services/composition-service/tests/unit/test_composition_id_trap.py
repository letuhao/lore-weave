"""D-COMPOSITION-ID-TRAP — a book carries THREE uuids and the model picks the wrong one.

Live, on the Mị Đế book: the agent read `composition_get_work`, saw `id` and `project_id`
side by side, passed the returned `id` (the Work's surrogate key) as the next tool's
`project_id`, and `composition_get_outline_node` answered `not found or not accessible`
— for a row that existed. It then told the author, correctly and uselessly, that Chapter 1
did not exist, and stopped. Nothing was wrong except which uuid went in which slot.

Two halves, tested here:
  * `_named_ids`   — stop the mistake being MADE (a bare `id` is a name that means
                     nothing on its own; call it `work_id` and say what wants what);
  * `scope_meta`   — SURVIVE it when it is made anyway (accept a work_id in the
                     project_id slot and resolve to the same Work).
Either half alone leaves the failure reachable: naming does not help a model that has
already guessed, and resolving does not stop the guess spreading to args that have no
repair path.
"""
from __future__ import annotations

import uuid

import pytest

from app.db.repositories.works import WorksRepo
from app.mcp import server as srv


class _FakeConn:
    def __init__(self, rows_by_id):
        self._rows = rows_by_id
        self.last_sql = None
        self.last_arg = None

    async def fetchrow(self, sql, arg):
        self.last_sql, self.last_arg = sql, arg
        return self._rows.get(arg)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return self._conn


BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
WORK = uuid.uuid4()
ROW = {"book_id": BOOK, "id": WORK, "project_id": PROJECT}


def _repo():
    # Both uuids address the same row — exactly the live shape, where the OR in the
    # query is what makes the work_id branch resolve.
    conn = _FakeConn({PROJECT: ROW, WORK: ROW})
    return WorksRepo(_FakePool(conn)), conn


# ── surviving the mistake ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_project_id_resolves_as_before():
    repo, _ = _repo()
    meta = await repo.scope_meta(PROJECT)
    assert (meta.book_id, meta.work_id, meta.project_id) == (BOOK, WORK, PROJECT)


@pytest.mark.asyncio
async def test_a_WORK_id_in_the_project_id_slot_resolves_to_the_same_work():
    """THE FIX. Before this, the agent's mis-slotted id produced `not found` for a row
    that existed, and the turn ended with a confident, wrong 'the chapter does not
    exist'."""
    repo, _ = _repo()
    meta = await repo.scope_meta(WORK)
    assert (meta.book_id, meta.work_id, meta.project_id) == (BOOK, WORK, PROJECT)
    # …and it reports the CANONICAL project_id, not the id it was handed — so a caller
    # that threads `meta.project_id` onward is repaired, not merely un-blocked.
    assert meta.project_id == PROJECT


@pytest.mark.asyncio
async def test_an_unrelated_uuid_still_returns_None():
    """The anti-oracle property is load-bearing and must not widen: an id that matches
    NEITHER column is still an un-resolvable None, which the access layer turns into the
    same uniform H13 as a denied grant. Accepting two columns of the same table is a
    repair; accepting anything else would be a leak."""
    repo, _ = _repo()
    assert await repo.scope_meta(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_the_grant_gate_is_untouched_by_the_repair():
    """scope_meta only ever answers 'which book does this Work belong to'. The E0 grant
    still gates on that book_id afterwards, so resolving by work_id cannot reach a Work
    the caller could not already reach by project_id."""
    repo, _ = _repo()
    by_project = await repo.scope_meta(PROJECT)
    by_work = await repo.scope_meta(WORK)
    assert by_project.book_id == by_work.book_id == BOOK


# ── stopping the mistake ───────────────────────────────────────────────────────


class TestNamedIds:
    def test_the_bare_id_becomes_work_id(self):
        out = srv._named_ids({"id": str(WORK), "project_id": str(PROJECT), "status": "active"})
        assert out["work_id"] == str(WORK)
        assert "id" not in out, "a bare `id` is the ambiguity — it must not survive"
        assert out["project_id"] == str(PROJECT)

    def test_it_says_which_id_the_other_tools_want(self):
        out = srv._named_ids({"id": str(WORK), "project_id": str(PROJECT)})
        assert "do not pass work_id as project_id" in out["_ids"]

    def test_other_fields_are_preserved(self):
        out = srv._named_ids({"id": str(WORK), "book_id": str(BOOK), "settings": {"a": 1}})
        assert out["book_id"] == str(BOOK)
        assert out["settings"] == {"a": 1}

    def test_it_does_not_mutate_its_input(self):
        src = {"id": str(WORK), "project_id": str(PROJECT)}
        srv._named_ids(src)
        assert src == {"id": str(WORK), "project_id": str(PROJECT)}
