"""23 B1/B2/B3/B4 — EFFECT tests for the structure_node (spec-layer) MCP surface.

Handler-shape + scope tests (the proven test_mcp_server.py pattern: patch the
envelope `_ctx`, the grant resolver, and the repo constructors so handlers run
against in-memory stubs — no DB, no book-service). They assert the EFFECT of the
wiring, not just that a symbol exists:

  • arc_create gates EDIT on the BOOK and stamps `created_by` (never a user scope
    key); a no-grant caller is the H13 uniform deny.
  • the depth/cycle/cross-book trigger violation (StructureConflictError) surfaces
    as a CLEAN tool refusal, never a raised 5xx (BA9).
  • a by-id read/mutation resolves the arc's book from the ROW and gates on ITS
    book (the authoring-run fence — the gate can't check a different book).
  • arc_get is ENRICHED with the resolved cascade + derived span + open-promise
    rollup (proves structure_node is READ, not write-only — BA7/BA6/BA15/BA12).
  • conformance_run(scope='arc') now takes `arc_id` (a structure_node) and
    validates it against the gated book (BA4) — a foreign/missing arc is denied.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import StructureNode
from app.db.repositories.structure import StructureConflictError

# conftest.py sets INTERNAL_SERVICE_TOKEN / CONFIRM_TOKEN_SIGNING_SECRET before import.

TEST_USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOOK = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_BOOK = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
PROJECT = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
ARC = uuid.UUID("11111111-1111-1111-1111-111111111111")


class _Ctx:
    """Stand-in for the kit ToolContext (handlers read only `user_id`)."""

    def __init__(self, user_id=TEST_USER):
        self.user_id = user_id
        self.session_id = "sess-1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = "test_token"


def _node(**kw) -> StructureNode:
    return StructureNode(
        id=kw.get("id", uuid.uuid4()),
        book_id=kw.get("book_id", BOOK),
        parent_id=kw.get("parent_id"),
        kind=kw.get("kind", "arc"),
        depth=kw.get("depth", 0),
        rank=kw.get("rank", "n"),
        title=kw.get("title", "Betrayal"),
        status=kw.get("status", "outline"),
        version=kw.get("version", 1),
    )


@asynccontextmanager
async def _patched(*, grant_level=2, structures=None, book=BOOK, grants=None):
    """Patch the server identity + grant resolver + repo constructors. `grant_level`:
    0=none, 1=VIEW, 2=EDIT (loreweave_grants ints).

    `grants` (optional) is a per-book ``{book_id: level}`` map: when given, the
    resolver returns the level for the EXACT book_id the gate asks about (0 for any
    other book). This is what proves a by-id mutation gates on the ROW's book — a
    caller granted only book B is denied on a node whose own book is B' — since a
    flat `grant_level` would grant every book alike and hide the cross-book bug."""
    import app.mcp.server as srv

    if structures is None:
        structures = AsyncMock()

    works = AsyncMock()

    async def _scope_meta(project_id):
        return SimpleNamespace(book_id=book, work_id=uuid.uuid4(), project_id=project_id)

    works.scope_meta = AsyncMock(side_effect=_scope_meta)

    async def _resolve(book_id, user_id):
        if grants is not None:
            return grants.get(book_id, 0)
        return grant_level

    with patch.object(srv, "_ctx", side_effect=lambda ctx: ctx), \
         patch.object(srv, "_grant_resolver", return_value=_resolve), \
         patch.object(srv, "get_pool", return_value=object()), \
         patch.object(srv, "WorksRepo", return_value=works), \
         patch.object(srv, "StructureRepo", return_value=structures), \
         patch.object(srv, "NarrativeThreadRepo", return_value=AsyncMock()):
        yield srv, structures, works


# ── B1 create ─────────────────────────────────────────────────────────────────


async def test_arc_create_gates_edit_and_stamps_book():
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.create_node = AsyncMock(return_value=_node(kind="saga"))
    async with _patched(grant_level=2, structures=structures):
        res = await srv.composition_arc_create(
            _Ctx(), srv._ArcCreateArgs(book_id=str(BOOK), kind="saga", title="Ascension"),
        )
    assert "id" in res and res["_meta"]["undo_hint"]["tool"] == "composition_arc_delete"
    # EFFECT: book_id is the scope (positional), created_by is a plain actor stamp.
    call = structures.create_node.await_args
    assert call.args[0] == BOOK
    assert call.kwargs["created_by"] == TEST_USER
    assert call.kwargs["kind"] == "saga"


async def test_arc_create_denied_without_grant():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=0):
        with pytest.raises(NotAccessibleError):
            await srv.composition_arc_create(
                _Ctx(), srv._ArcCreateArgs(book_id=str(BOOK), kind="arc"),
            )


async def test_arc_create_depth_conflict_is_clean_refusal():
    """BA9: the depth/cycle/cross-book trigger violation surfaces as a structured
    refusal, NEVER a raised 5xx."""
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.create_node = AsyncMock(
        side_effect=StructureConflictError("depth 3 exceeds saga→arc→sub-arc"),
    )
    async with _patched(grant_level=2, structures=structures):
        res = await srv.composition_arc_create(
            _Ctx(), srv._ArcCreateArgs(book_id=str(BOOK), kind="arc", parent_arc_id=str(ARC)),
        )
    assert res["success"] is False and "structure constraint" in res["error"]


# ── B1 list + get (enriched — proves the arc is READ) ───────────────────────────


async def test_arc_list_returns_tree():
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.list_tree = AsyncMock(return_value=[_node(kind="saga"), _node(kind="arc")])
    async with _patched(grant_level=1, structures=structures):
        res = await srv.composition_arc_list(_Ctx(), book_id=str(BOOK))
    assert len(res["nodes"]) == 2
    structures.list_tree.assert_awaited_once()


async def test_arc_get_enriches_resolved_span_and_promises():
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))
    structures.resolve_tracks = AsyncMock(return_value=[{"key": "romance"}])
    structures.resolve_roster = AsyncMock(return_value=[{"key": "protagonist"}])
    structures.resolve_roster_bindings = AsyncMock(return_value={"protagonist": "e1"})
    # BE-A1: the agent door now reads the dense-ranked DERIVED block (same unit as the Hub), NOT
    # the packer's raw strided span(). Mock derived_blocks; assert span() is never touched.
    structures.span = AsyncMock(return_value={"min_story_order": 1, "chapter_count": 3, "is_contiguous": True})
    structures.derived_blocks = AsyncMock(return_value={
        ARC: {"span": {"from_order": 1, "to_order": 3}, "chapter_count": 3, "is_contiguous": True},
    })
    structures.open_promises = AsyncMock(return_value=[])
    async with _patched(grant_level=1, structures=structures):
        res = await srv.composition_arc_get(_Ctx(), node_id=str(ARC))
    assert res["resolved"]["tracks"] == [{"key": "romance"}]
    assert res["span"] == {"from_order": 1, "to_order": 3}
    assert res["chapter_count"] == 3 and res["is_contiguous"] is True
    structures.span.assert_not_called()   # BE-A1: the raw packer axis is left untouched at this door
    assert res["open_promises"] == []


async def test_arc_get_by_id_gates_on_row_book():
    """The by-id read resolves the arc's book from the ROW, then gates on ITS book —
    a no-grant caller is denied even though the node exists."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))
    async with _patched(grant_level=0, structures=structures):
        with pytest.raises(NotAccessibleError):
            await srv.composition_arc_get(_Ctx(), node_id=str(ARC))


async def test_arc_get_missing_is_uniform_deny():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=None)
    async with _patched(grant_level=2, structures=structures):
        with pytest.raises(NotAccessibleError):
            await srv.composition_arc_get(_Ctx(), node_id=str(ARC))


# ── B1 move (conflict path) ─────────────────────────────────────────────────────


async def test_arc_move_conflict_is_clean_refusal():
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))
    structures.move = AsyncMock(
        side_effect=StructureConflictError("cross-book parent"),
    )
    async with _patched(grant_level=2, structures=structures):
        res = await srv.composition_arc_move(
            _Ctx(), srv._ArcMoveArgs(node_id=str(ARC), new_parent_arc_id=str(uuid.uuid4())),
        )
    assert res["success"] is False and "structure constraint" in res["error"]


# ── B1 assign_chapters ──────────────────────────────────────────────────────────


async def test_arc_assign_chapters_returns_count():
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.assign_chapters = AsyncMock(return_value=2)
    async with _patched(grant_level=2, structures=structures):
        res = await srv.composition_arc_assign_chapters(
            _Ctx(), srv._ArcAssignChaptersArgs(
                book_id=str(BOOK), structure_node_id=str(ARC),
                chapter_node_ids=[str(uuid.uuid4()), str(uuid.uuid4())],
            ),
        )
    assert res["assigned"] == 2
    call = structures.assign_chapters.await_args
    assert call.args[0] == BOOK   # book-scoped both sides


# ── B4 conformance_run now keys on arc_id (a structure_node), not a template ─────


async def test_conformance_arc_requires_arc_id_and_model_ref():
    import app.mcp.server as srv

    async with _patched(grant_level=2):
        no_arc = await srv.composition_conformance_run(
            _Ctx(), srv._ConformanceRunArgs(project_id=str(PROJECT), scope="arc"),
        )
        assert no_arc["success"] is False and "arc_id is required" in no_arc["error"]

        no_model = await srv.composition_conformance_run(
            _Ctx(), srv._ConformanceRunArgs(project_id=str(PROJECT), scope="arc",
                                            arc_id=str(ARC)),
        )
        assert no_model["success"] is False and "model_ref is required" in no_model["error"]


async def test_conformance_arc_validates_structure_node_in_book():
    """BA4: the arc is a structure_node in THIS gated book — a foreign-book arc is
    the H13 uniform deny (no oracle); an in-book arc mints the confirm token."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    # foreign-book arc → deny
    foreign = AsyncMock()
    foreign.get = AsyncMock(return_value=_node(id=ARC, book_id=OTHER_BOOK))
    async with _patched(grant_level=2, structures=foreign, book=BOOK):
        with pytest.raises(NotAccessibleError):
            await srv.composition_conformance_run(
                _Ctx(), srv._ConformanceRunArgs(project_id=str(PROJECT), scope="arc",
                                                arc_id=str(ARC), model_ref="m1"),
            )

    # in-book arc → confirm token minted
    ok = AsyncMock()
    ok.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))
    async with _patched(grant_level=2, structures=ok, book=BOOK):
        res = await srv.composition_conformance_run(
            _Ctx(), srv._ConformanceRunArgs(project_id=str(PROJECT), scope="arc",
                                            arc_id=str(ARC), model_ref="m1"),
        )
    assert "confirm_token" in res
    assert res["descriptor"] == srv._CONFORMANCE_RUN_DESCRIPTOR


# ── B2 template ops — honest "pending A5/A4" until the engine seam merges ─────────


async def test_arc_template_drift_no_provenance_returns_unknown():
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))  # arc_template_id None
    async with _patched(grant_level=1, structures=structures):
        res = await srv.composition_arc_template_drift(_Ctx(), node_id=str(ARC))
    assert res["available"] is False and "no template provenance" in res["reason"]


async def test_arc_extract_template_engine_is_wired_not_pending():
    """BE-8 agent-parity (extract): the `extract_template_from_arc` engine seam is MERGED, so the
    MCP tool must actually RUN it — never the honest-pending refusal. If a refactor removes/renames
    the engine fn, `getattr` goes None and this reds (catching a silent regression to a stub)."""
    import app.mcp.server as srv
    from unittest.mock import patch

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))
    fake = {"success": True, "arc_template_id": str(uuid.uuid4()), "reconstructed": {}}
    with patch("app.engine.arc_apply.extract_template_from_arc",
               AsyncMock(return_value=fake)) as eng:
        async with _patched(grant_level=1, structures=structures):
            res = await srv.composition_arc_extract_template(
                _Ctx(), srv._ArcExtractTemplateArgs(node_id=str(ARC), code="c1", name="My Arc"),
            )
    eng.assert_awaited_once()                       # the real engine RAN (parity, not a stub)
    assert "pending_dependency" not in res          # NOT the honest-pending refusal
    assert res["success"] is True and res["arc_template_id"] == fake["arc_template_id"]


# ══════════════════════════════════════════════════════════════════════════════
# BY-ID ARC MUTATION tenancy fence — the Stage-1 cross-book IDOR class, now on arcs
# (a confirmed /review-impl coverage gap). composition_arc_update / _move / _delete
# are by-id mutations that carry NO body book_id: `_arc_or_deny` MUST resolve the
# structure_node's own book from the ROW and gate the caller's grant on IT. These
# assert the EFFECT — a non-grantee is denied, the gate keys on the ROW's book (not
# the caller's), and a missing vs a foreign arc are the SAME uniform deny (no
# enumeration oracle). If any mutation skips the gate / gates the wrong book, the
# repo mutator would be reached and one of these reds.
# ══════════════════════════════════════════════════════════════════════════════


# One invoker per by-id mutation. Each builds its arg model against the SAME ARC id
# so the harness's `structures.get` decides which book the row lives in.
def _invoke_arc_update(srv, ctx):
    return srv.composition_arc_update(
        ctx, srv._ArcUpdateArgs(node_id=str(ARC), expected_version=1, title="Renamed"),
    )


def _invoke_arc_move(srv, ctx):
    return srv.composition_arc_move(
        ctx, srv._ArcMoveArgs(node_id=str(ARC), new_parent_arc_id=str(uuid.uuid4())),
    )


def _invoke_arc_delete(srv, ctx):
    return srv.composition_arc_delete(ctx, node_id=str(ARC))


_ARC_MUTATIONS = [_invoke_arc_update, _invoke_arc_move, _invoke_arc_delete]
_ARC_MUTATION_IDS = ["arc_update", "arc_move", "arc_delete"]


def _assert_no_repo_mutation(structures):
    """The gate must deny BEFORE any repo mutator runs — the deny is the gate's, not
    a downstream side effect. (`get` IS awaited: `_arc_or_deny` reads the row first.)"""
    structures.update.assert_not_awaited()
    structures.move.assert_not_awaited()
    structures.archive.assert_not_awaited()
    structures.restore.assert_not_awaited()


@pytest.mark.parametrize("invoke", _ARC_MUTATIONS, ids=_ARC_MUTATION_IDS)
async def test_arc_mutation_denied_without_grant(invoke):
    """A caller with NO grant on the arc's book → the by-id mutation is the H13
    uniform deny (same shape a missing node yields). The node EXISTS (get→a real
    row) so the deny is unambiguously the GRANT gate's, not a missing-node fallback."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=BOOK))
    async with _patched(grant_level=0, structures=structures):
        with pytest.raises(NotAccessibleError):
            await invoke(srv, _Ctx())
    _assert_no_repo_mutation(structures)


@pytest.mark.parametrize("invoke", _ARC_MUTATIONS, ids=_ARC_MUTATION_IDS)
async def test_arc_mutation_gates_on_row_book_not_caller_grant(invoke):
    """Stage-1 cross-book IDOR, on arcs: the caller holds EDIT on book B, but the arc
    ROW lives in book B'. `_arc_or_deny` resolves the book from the row (B'), where
    the caller has NO grant → uniform deny. Had the gate keyed on a caller-favourable
    book (B) instead of the row's, the caller would have been let in. The grant map
    grants ONLY B; the node's own book_id is B' (OTHER_BOOK)."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=OTHER_BOOK))
    async with _patched(structures=structures, grants={BOOK: 2}):  # EDIT on B only
        with pytest.raises(NotAccessibleError):
            await invoke(srv, _Ctx())
    _assert_no_repo_mutation(structures)


@pytest.mark.parametrize("invoke", _ARC_MUTATIONS, ids=_ARC_MUTATION_IDS)
async def test_arc_mutation_allowed_when_grant_on_row_book(invoke):
    """Companion positive control to the IDOR deny — proves the gate resolves+checks
    the ROW's book (not a blanket deny): the SAME arc in book B', but now the caller
    holds EDIT on B' → the mutation PROCEEDS (a plain result envelope, never a refusal
    or a raise). Flip the grant to B' and the identical call that denied above passes."""
    import app.mcp.server as srv

    structures = AsyncMock()
    structures.get = AsyncMock(return_value=_node(id=ARC, book_id=OTHER_BOOK, version=1))
    structures.update = AsyncMock(return_value=_node(id=ARC, book_id=OTHER_BOOK, version=2))
    structures.move = AsyncMock(return_value=_node(id=ARC, book_id=OTHER_BOOK))
    structures.archive = AsyncMock(return_value=None)
    async with _patched(structures=structures, grants={OTHER_BOOK: 2}):  # EDIT on the ROW's book
        res = await invoke(srv, _Ctx())
    assert isinstance(res, dict)
    assert res.get("success") is not False  # not the H13 refusal envelope


@pytest.mark.parametrize("invoke", _ARC_MUTATIONS, ids=_ARC_MUTATION_IDS)
async def test_arc_mutation_missing_and_foreign_are_same_deny(invoke):
    """No enumeration oracle: a MISSING arc (get→None) and a FOREIGN-book arc
    (get→a row in B', caller granted only B) raise the IDENTICAL uniform H13 error —
    same type AND same message — so the caller can't tell 'doesn't exist' apart from
    'not yours'."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError
    from loreweave_mcp.errors import NOT_ACCESSIBLE_MESSAGE

    # missing arc — caller HAS EDIT (so the deny is purely the missing row).
    missing = AsyncMock()
    missing.get = AsyncMock(return_value=None)
    async with _patched(grant_level=2, structures=missing):
        with pytest.raises(NotAccessibleError) as missing_exc:
            await invoke(srv, _Ctx())

    # foreign-book arc — the row exists but in B', caller granted only B.
    foreign = AsyncMock()
    foreign.get = AsyncMock(return_value=_node(id=ARC, book_id=OTHER_BOOK))
    async with _patched(structures=foreign, grants={BOOK: 2}):
        with pytest.raises(NotAccessibleError) as foreign_exc:
            await invoke(srv, _Ctx())

    assert str(missing_exc.value) == str(foreign_exc.value) == NOT_ACCESSIBLE_MESSAGE
