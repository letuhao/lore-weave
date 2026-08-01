"""S3 catalog-unification (2026-07-25) — dispatch tests for the two unified arc-family
op-tools: ``composition_arc_edit`` and ``composition_arc_template_edit``.

They prove the NEW code (op-routing + per-op arg construction + required-field
validation), NOT the underlying handlers — those keep their own EFFECT tests in
test_mcp_arc_structure.py / test_arc_template_*.py. Each op is patched at the delegate
so the assertion is mutation-strong: a mis-routed op (create→update, delete→restore)
calls the WRONG mock and reds; and the returned dict is the delegate's verbatim (proves
the unified tool never rewraps — Undo hints / conflict shapes pass through untouched).

Also pins the _present() invariant that gives this whole flat-superset pattern its
safety: a None the caller omitted must NOT be forced onto a sub-Args field whose own
default is non-None (e.g. _ArcCreateArgs.status='outline') — else op=create would 422
on a bare `{op:'create', book_id}`.
"""

from __future__ import annotations

import uuid

import pytest
from unittest.mock import AsyncMock, patch

import app.mcp.server as srv

BOOK = "cccccccc-cccc-cccc-cccc-cccccccccccc"
NODE = "11111111-1111-1111-1111-111111111111"
TPL = "22222222-2222-2222-2222-222222222222"


class _Ctx:
    def __init__(self):
        self.user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.session_id = "s"
        self.project_id = None
        self.trace_id = None
        self.internal_token = "t"


# ── composition_arc_edit ────────────────────────────────────────────────────────


async def test_arc_edit_create_routes_and_present_keeps_subargs_defaults():
    sentinel = {"id": "x", "_meta": {"undo_hint": {"tool": "composition_arc_delete"}}}
    with patch.object(srv, "composition_arc_create", AsyncMock(return_value=sentinel)) as m:
        res = await srv.composition_arc_edit(
            _Ctx(), srv._ArcEditArgs(op="create", book_id=BOOK, title="Ascension"),
        )
    m.assert_awaited_once()
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._ArcCreateArgs)
    assert passed.book_id == BOOK and passed.title == "Ascension"
    # _present dropped the omitted status=None/kind=None → the sub-model's OWN defaults
    # apply. If _present forgot to drop None, _ArcCreateArgs(status=None) would 422.
    assert passed.status == "outline" and passed.kind == "arc"
    # the delegate's dict passes through verbatim (Undo hint preserved, not rewrapped).
    assert res is sentinel


async def test_arc_edit_create_missing_book_id_raises():
    with pytest.raises(ValueError, match="book_id"):
        await srv.composition_arc_edit(_Ctx(), srv._ArcEditArgs(op="create", title="x"))


async def test_arc_edit_update_routes_with_optimistic_version():
    with patch.object(srv, "composition_arc_update", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_arc_edit(
            _Ctx(),
            srv._ArcEditArgs(op="update", node_id=NODE, expected_version=3, goal="win"),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._ArcUpdateArgs)
    assert passed.node_id == NODE and passed.expected_version == 3 and passed.goal == "win"


async def test_arc_edit_update_requires_node_id_and_expected_version():
    with pytest.raises(ValueError, match="expected_version"):
        await srv.composition_arc_edit(_Ctx(), srv._ArcEditArgs(op="update", node_id=NODE))
    with pytest.raises(ValueError, match="node_id"):
        await srv.composition_arc_edit(
            _Ctx(), srv._ArcEditArgs(op="update", expected_version=1),
        )


async def test_arc_edit_delete_routes_to_delete_not_restore():
    with patch.object(srv, "composition_arc_delete", AsyncMock(return_value={"archived": True})) as d, \
         patch.object(srv, "composition_arc_restore", AsyncMock()) as r:
        res = await srv.composition_arc_edit(_Ctx(), srv._ArcEditArgs(op="delete", node_id=NODE))
    d.assert_awaited_once()
    r.assert_not_awaited()
    assert d.await_args.kwargs["node_id"] == NODE and res["archived"] is True


async def test_arc_edit_restore_routes_to_restore_not_delete():
    with patch.object(srv, "composition_arc_restore", AsyncMock(return_value={"archived": False})) as r, \
         patch.object(srv, "composition_arc_delete", AsyncMock()) as d:
        await srv.composition_arc_edit(_Ctx(), srv._ArcEditArgs(op="restore", node_id=NODE))
    r.assert_awaited_once()
    d.assert_not_awaited()
    assert r.await_args.kwargs["node_id"] == NODE


async def test_arc_edit_move_routes_with_reparent_and_after():
    with patch.object(srv, "composition_arc_move", AsyncMock(return_value={"ok": 1})) as m:
        await srv.composition_arc_edit(
            _Ctx(),
            srv._ArcEditArgs(op="move", node_id=NODE, new_parent_arc_id=None, after_id=TPL),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._ArcMoveArgs)
    assert passed.node_id == NODE and passed.new_parent_arc_id is None and passed.after_id == TPL


async def test_arc_edit_assign_chapters_routes_and_null_unassigns():
    with patch.object(srv, "composition_arc_assign_chapters", AsyncMock(return_value={"assigned": 2})) as m:
        await srv.composition_arc_edit(
            _Ctx(),
            srv._ArcEditArgs(op="assign_chapters", book_id=BOOK, structure_node_id=None,
                             chapter_node_ids=[NODE, TPL]),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._ArcAssignChaptersArgs)
    assert passed.book_id == BOOK and passed.structure_node_id is None
    assert passed.chapter_node_ids == [NODE, TPL]


async def test_arc_edit_assign_chapters_requires_book_and_chapters():
    with pytest.raises(ValueError, match="chapter_node_ids"):
        await srv.composition_arc_edit(
            _Ctx(), srv._ArcEditArgs(op="assign_chapters", book_id=BOOK),
        )


# ── composition_arc_template_edit ─────────────────────────────────────────────────


async def test_template_edit_create_routes_and_coerces_subargs():
    with patch.object(srv, "composition_arc_template_create", AsyncMock(return_value={"id": TPL})) as m:
        res = await srv.composition_arc_template_edit(
            _Ctx(),
            srv._ArcTemplateEditArgs(op="create", code="revenge", name="Revenge Arc",
                                     summary="s", threads=[]),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv.ArcTemplateCreateArgs)
    assert passed.code == "revenge" and passed.name == "Revenge Arc"
    # _present dropped omitted language=None → the sub-model default 'en' applies.
    assert passed.original_language == "en" and passed.visibility == "private"
    assert res == {"id": TPL}


async def test_template_edit_create_requires_code_and_name():
    with pytest.raises(ValueError, match="code and name"):
        await srv.composition_arc_template_edit(
            _Ctx(), srv._ArcTemplateEditArgs(op="create", code="x"),
        )


async def test_template_edit_update_routes_with_arc_id():
    with patch.object(srv, "composition_arc_template_update", AsyncMock(return_value={"id": TPL})) as m:
        await srv.composition_arc_template_edit(
            _Ctx(),
            srv._ArcTemplateEditArgs(op="update", arc_id=TPL, expected_version=2, name="New"),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._ArcTemplateUpdateArgs)
    assert passed.arc_id == TPL and passed.expected_version == 2 and passed.name == "New"


async def test_template_edit_archive_routes_to_archive_not_restore():
    with patch.object(srv, "composition_arc_template_archive", AsyncMock(return_value={"archived": True})) as a, \
         patch.object(srv, "composition_arc_template_restore", AsyncMock()) as r:
        await srv.composition_arc_template_edit(
            _Ctx(), srv._ArcTemplateEditArgs(op="archive", arc_id=TPL),
        )
    a.assert_awaited_once()
    r.assert_not_awaited()
    assert a.await_args.kwargs["arc_id"] == TPL


async def test_template_edit_restore_routes_and_requires_arc_id():
    with patch.object(srv, "composition_arc_template_restore", AsyncMock(return_value={"archived": False})) as r:
        await srv.composition_arc_template_edit(
            _Ctx(), srv._ArcTemplateEditArgs(op="restore", arc_id=TPL),
        )
    r.assert_awaited_once()
    with pytest.raises(ValueError, match="arc_id"):
        await srv.composition_arc_template_edit(_Ctx(), srv._ArcTemplateEditArgs(op="restore"))
