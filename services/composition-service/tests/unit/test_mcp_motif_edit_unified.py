"""S3·motif — dispatch tests for the 3 unified motif op-tools: composition_motif_edit,
composition_motif_link_edit, composition_motif_bind_edit.

Proves the NEW code (op-routing + arg construction + validation), not the underlying
handlers (they keep their EFFECT tests in test_motif_mcp.py). Delegates are patched so a
mis-routed op reds. Extra pins on this family's two sharp edges:
  • PATCH semantics survive the wrapper — the constructed _MotifPatchToolArgs.model_fields_set
    (which the handler uses to decide WHICH fields to patch) contains exactly the caller's
    supplied fields, so a unified op=patch that sets only `summary` doesn't clobber the rest.
  • _present keeps sub-Args defaults (create target='user'/visibility='private').
"""

from __future__ import annotations

import uuid

import pytest
from unittest.mock import AsyncMock, patch

import app.mcp.server as srv

M1 = "11111111-1111-1111-1111-111111111111"
M2 = "22222222-2222-2222-2222-222222222222"
LINK = "33333333-3333-3333-3333-333333333333"
PROJECT = "44444444-4444-4444-4444-444444444444"
NODE = "55555555-5555-5555-5555-555555555555"
BOOK = "66666666-6666-6666-6666-666666666666"


class _Ctx:
    def __init__(self):
        self.user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.session_id = "s"
        self.project_id = None
        self.trace_id = None
        self.internal_token = "t"


# ── composition_motif_edit ────────────────────────────────────────────────────────


async def test_motif_edit_create_routes_and_keeps_defaults():
    with patch.object(srv, "composition_motif_create", AsyncMock(return_value={"id": M1})) as m:
        await srv.composition_motif_edit(
            _Ctx(), srv._MotifEditArgs(op="create", code="rescue", name="The Rescue"),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._MotifCreateArgs)
    assert passed.code == "rescue" and passed.name == "The Rescue"
    # _present dropped omitted target/visibility/kind → sub-model defaults apply.
    assert passed.target == "user" and passed.visibility == "private" and passed.kind == "sequence"


async def test_motif_edit_create_requires_code_and_name():
    with pytest.raises(ValueError, match="code and name"):
        await srv.composition_motif_edit(_Ctx(), srv._MotifEditArgs(op="create", code="x"))


async def test_motif_edit_patch_preserves_partial_patch_semantics():
    """The handler patches exactly model_fields_set - {motif_id,expected_version,book_id}.
    A unified op=patch that sets only `summary` must produce that single-field set — NOT
    a full model with every other field defaulted to None (which would blank them)."""
    with patch.object(srv, "composition_motif_patch", AsyncMock(return_value={"id": M1})) as m:
        await srv.composition_motif_edit(
            _Ctx(),
            srv._MotifEditArgs(op="patch", motif_id=M1, expected_version=4, summary="new blurb"),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._MotifPatchToolArgs)
    patch_fields = passed.model_fields_set - {"motif_id", "expected_version", "book_id"}
    assert patch_fields == {"summary"}
    assert passed.summary == "new blurb" and passed.expected_version == 4


async def test_motif_edit_patch_requires_motif_id_and_version():
    with pytest.raises(ValueError, match="expected_version"):
        await srv.composition_motif_edit(_Ctx(), srv._MotifEditArgs(op="patch", motif_id=M1))


async def test_motif_edit_patch_preserves_explicit_null_clear():
    """motif_patch clears a nullable column on an EXPLICIT null (repo model_dump(exclude_unset)).
    The unified tool must forward an explicitly-passed `emotion_target=None` as a SET field (so it
    clears), not drop it — else motif_edit can't clear what the legacy motif_patch can. Mutation:
    switching op=patch back to `_present` (drop-None) reds this test."""
    with patch.object(srv, "composition_motif_patch", AsyncMock(return_value={"id": M1})) as m:
        await srv.composition_motif_edit(
            _Ctx(),
            srv._MotifEditArgs(op="patch", motif_id=M1, expected_version=1, emotion_target=None),
        )
    passed = m.await_args.args[1]
    # explicit null → must be a SET field on the forwarded patch (so the repo clears it)
    assert "emotion_target" in passed.model_fields_set
    assert passed.emotion_target is None
    # an OMITTED field must NOT be forwarded (still a real partial patch, no clobber)
    assert "summary" not in passed.model_fields_set


async def test_motif_edit_archive_routes_with_book_passthrough_not_restore():
    with patch.object(srv, "composition_motif_archive", AsyncMock(return_value={"archived": True})) as a, \
         patch.object(srv, "composition_motif_restore", AsyncMock()) as r:
        await srv.composition_motif_edit(
            _Ctx(), srv._MotifEditArgs(op="archive", motif_id=M1, book_id=BOOK),
        )
    a.assert_awaited_once()
    r.assert_not_awaited()
    assert a.await_args.kwargs["motif_id"] == M1 and a.await_args.kwargs["book_id"] == BOOK


async def test_motif_edit_restore_routes():
    with patch.object(srv, "composition_motif_restore", AsyncMock(return_value={"archived": False})) as r:
        await srv.composition_motif_edit(_Ctx(), srv._MotifEditArgs(op="restore", motif_id=M1))
    r.assert_awaited_once()
    assert r.await_args.kwargs["motif_id"] == M1


# ── composition_motif_link_edit ──────────────────────────────────────────────────


async def test_motif_link_edit_create_routes():
    with patch.object(srv, "composition_motif_link_create", AsyncMock(return_value={"id": LINK})) as m:
        await srv.composition_motif_link_edit(
            _Ctx(),
            srv._MotifLinkEditArgs(op="create", from_motif_id=M1, to_motif_id=M2, kind="precedes"),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._MotifLinkCreateArgs)
    assert passed.from_motif_id == M1 and passed.to_motif_id == M2 and passed.kind == "precedes"


async def test_motif_link_edit_create_requires_endpoints_and_kind():
    with pytest.raises(ValueError, match="from_motif_id"):
        await srv.composition_motif_link_edit(
            _Ctx(), srv._MotifLinkEditArgs(op="create", from_motif_id=M1),
        )


async def test_motif_link_edit_delete_routes_not_create():
    with patch.object(srv, "composition_motif_link_delete", AsyncMock(return_value={"deleted": True})) as d, \
         patch.object(srv, "composition_motif_link_create", AsyncMock()) as c:
        await srv.composition_motif_link_edit(
            _Ctx(), srv._MotifLinkEditArgs(op="delete", link_id=LINK, book_id=BOOK),
        )
    d.assert_awaited_once()
    c.assert_not_awaited()
    assert d.await_args.kwargs["link_id"] == LINK and d.await_args.kwargs["book_id"] == BOOK


async def test_motif_link_edit_delete_requires_link_id():
    with pytest.raises(ValueError, match="link_id"):
        await srv.composition_motif_link_edit(_Ctx(), srv._MotifLinkEditArgs(op="delete"))


# ── composition_motif_bind_edit ──────────────────────────────────────────────────


async def test_motif_bind_edit_bind_routes():
    with patch.object(srv, "composition_motif_bind", AsyncMock(return_value={"success": True})) as m:
        await srv.composition_motif_bind_edit(
            _Ctx(),
            srv._MotifBindEditArgs(op="bind", project_id=PROJECT, node_id=NODE, motif_id=M1,
                                   role_bindings={"hero": "e1"}),
        )
    passed = m.await_args.args[1]
    assert isinstance(passed, srv._MotifBindArgs)
    assert passed.project_id == PROJECT and passed.node_id == NODE and passed.motif_id == M1
    assert passed.role_bindings == {"hero": "e1"}


async def test_motif_bind_edit_bind_requires_ids():
    with pytest.raises(ValueError, match="motif_id"):
        await srv.composition_motif_bind_edit(
            _Ctx(), srv._MotifBindEditArgs(op="bind", project_id=PROJECT, node_id=NODE),
        )


async def test_motif_bind_edit_unbind_routes_not_bind():
    with patch.object(srv, "composition_motif_unbind", AsyncMock(return_value={"success": True})) as u, \
         patch.object(srv, "composition_motif_bind", AsyncMock()) as b:
        await srv.composition_motif_bind_edit(
            _Ctx(),
            srv._MotifBindEditArgs(op="unbind", project_id=PROJECT, node_id=NODE,
                                   undo_token={"t": 1}),
        )
    u.assert_awaited_once()
    b.assert_not_awaited()
    assert u.await_args.kwargs["project_id"] == PROJECT and u.await_args.kwargs["undo_token"] == {"t": 1}


async def test_motif_bind_edit_unbind_requires_project_and_node():
    with pytest.raises(ValueError, match="project_id and node_id"):
        await srv.composition_motif_bind_edit(_Ctx(), srv._MotifBindEditArgs(op="unbind", project_id=PROJECT))
