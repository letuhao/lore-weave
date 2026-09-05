"""`composition_list_derivatives` required a Work's id to enumerate a book's Works.

The handler uses `project_id` only to find the book and then lists BY BOOK
(`works.resolve_by_book`). So the book id was always what it wanted, and demanding a Work's id
first is a chicken-and-egg the tool imposed on itself.

MEASURED 2026-08-24, batches c-override8 / c-override9 / c-override10, K=5 each,
gemma-4-26b-a4b-qat. `composition_entity_override_edit` is refused NOT_A_DERIVATIVE, its refusal
correctly sends the model here, and the model cannot produce a project_id. Across those runs it
tried, in order:

    the turn's BOOK id      -> "not found or not accessible"
    the target ENTITY id    -> "not found or not accessible"
    the book's TITLE        -> "project_id must be a UUID — received 'LOOP-THROWAWAY-…'"

`book_id` is the one id `context_ids` carries on EVERY turn — `project_id` is populated only on
studio/editor turns — so accepting it lets the existing backfiller supply it with no further
change.

The project_id path is kept unchanged: these tests hold BOTH, because a fix that quietly
retires the old way would break every caller that already passes a Work's id.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.test_mcp_server import _Ctx, _patched


def _work(book_id, canonical=True):
    return NS(project_id=uuid.uuid4(), source_work_id=None if canonical else uuid.uuid4(),
              settings={"derivative_name": None if canonical else "what-if"},
              branch_point=None, status="active", version=1, book_id=book_id)


async def _call(srv, **kwargs):
    book = uuid.uuid4()
    rows = [_work(book), _work(book, canonical=False)]
    async with _patched() as s:
        s.WorksRepo(None).resolve_by_book = AsyncMock(return_value=rows)
        with patch.object(srv, "WorksRepo") as WR, \
                patch.object(srv, "_gate", AsyncMock()) as gate, \
                patch.object(srv, "_book_or_deny",
                             AsyncMock(return_value=NS(book_id=book))) as bod:
            WR.return_value.resolve_by_book = AsyncMock(return_value=rows)
            res = await srv.composition_list_derivatives(_Ctx(), **kwargs)
            return res, WR.return_value.resolve_by_book, gate, bod, book


class TestTheBookIdIsAWayIn:
    async def test_book_id_alone_lists_the_works(self):
        import app.mcp.server as srv

        res, resolve, gate, _bod, book = await _call(srv, book_id=str(uuid.uuid4()))
        assert "works" in res, res
        assert len(res["works"]) == 2
        resolve.assert_awaited()
        gate.assert_awaited(), "the book path must still gate on the book"

    async def test_the_derivative_is_identifiable_in_the_result(self):
        """The whole point of the call: the model must be able to pick the derivative out."""
        import app.mcp.server as srv

        res, *_ = await _call(srv, book_id=str(uuid.uuid4()))
        derivs = [w for w in res["works"] if w["is_canonical"] is False]
        assert len(derivs) == 1
        assert derivs[0]["project_id"], "the derivative's project_id is not returned"


class TestTheOldWayStillWorks:
    """A fix that quietly retired project_id would break every caller already passing one."""

    async def test_project_id_alone_still_lists_the_works(self):
        import app.mcp.server as srv

        res, resolve, _gate, bod, _book = await _call(srv, project_id=str(uuid.uuid4()))
        assert len(res["works"]) == 2
        bod.assert_awaited(), "the project path must still resolve-then-gate as it did"
        resolve.assert_awaited()


class TestExactlyOne:
    async def test_neither_is_refused_and_names_both(self):
        import app.mcp.server as srv

        res, resolve, *_ = await _call(srv)
        assert res["success"] is False
        assert "book_id" in res["error"] and "project_id" in res["error"]
        resolve.assert_not_awaited()

    async def test_both_is_refused_rather_than_silently_preferring_one(self):
        """Ambiguity resolved by a rule nobody stated is how a caller learns the wrong model
        of a tool."""
        import app.mcp.server as srv

        res, resolve, *_ = await _call(
            srv, book_id=str(uuid.uuid4()), project_id=str(uuid.uuid4()))
        assert res["success"] is False
        assert "EXACTLY ONE" in res["error"]
        resolve.assert_not_awaited()


class TestTheDescriptionLeadsWithTheBook:
    async def test_it_tells_the_model_which_entry_to_take(self):
        """The refusal in composition_entity_override_edit sends the model here; this tool must
        then say which row of the answer is the one it wants, or the journey stalls one step
        later instead."""
        import app.mcp.server as srv

        desc = srv.composition_list_derivatives.__mcp_tool_description__ if hasattr(
            srv.composition_list_derivatives, "__mcp_tool_description__") else None
        if desc is None:  # description lives on the registered tool, not the function
            import inspect
            src = inspect.getsource(srv)
            i = src.find('name="composition_list_derivatives"')
            desc = src[i:i + 900]
        assert "is_canonical=false" in desc, "it never says which entry is a derivative"
        assert desc.index("book_id") < desc.index("project_id"), (
            "project_id is offered before book_id — the argument the model does not have, first"
        )
