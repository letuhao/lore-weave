"""S-COMPOSE — tests for the composition-service MCP server facade (MCP fan-out
2026-06-20).

Two layers (mirrors the proven jobs-service S-JOBS test shape):

  1. **Wire path** (loopback uvicorn server, real MCP streamable-HTTP): `tools/list`
     returns the §4 S-COMPOSE catalog; every tool carries valid `_meta` (tier ∈
     {R,A,W} + scope=book + synonyms); no tool leaks a scope/identity arg; auth
     failures (missing/wrong internal token, malformed user-id) are rejected as tool
     errors BEFORE any repo access.

  2. **Handler shape + scope** (direct calls with stubbed repos + grant): identity
     comes from the envelope; a non-owner (no book grant) is rejected with the H13
     uniform error; every Tier-A handler returns an `_meta.undo_hint`; the Tier-W
     propose mints a confirm token; write_prose rejects a stale draft version.

The wire-path server runs in a daemon thread with its own event loop (the
StreamableHTTP session manager is once-per-instance and pytest runs
function-scoped loops under asyncio_mode=auto).
"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.clients.book_client import BookClientError
from app.db.models import CanonRule, CompositionWork, OutlineNode, SceneLink

# conftest.py (tests/conftest.py) sets the required env BEFORE app import.

_GOOD_TOKEN = "test_token"  # matches tests/conftest.py INTERNAL_SERVICE_TOKEN
TEST_USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BOOK = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PROJECT = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
CHAPTER = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

EXPECTED_TOOLS = {
    # Tier R
    "composition_get_work", "composition_list_outline",
    "composition_get_outline_node",
    "composition_get_prose", "composition_list_canon_rules",
    "composition_get_generation_job",
    # Tier A
    "composition_create_work",
    "composition_outline_node_create", "composition_outline_node_update",
    "composition_outline_node_delete", "composition_outline_node_restore",
    "composition_scene_link_create", "composition_scene_link_delete",
    "composition_canon_rule_create", "composition_canon_rule_update",
    "composition_canon_rule_delete", "composition_write_prose",
    # Tier W
    "composition_publish", "composition_generate",
    "composition_decompile_arcs",  # close-21-28 P-O2a — confirm-gated arc decompiler
    # ── D-AGENT-MODE §20 authoring-run tools (register on the SAME server) ──
    # Tier R
    "composition_authoring_run_list", "composition_authoring_run_get",
    # Tier A
    "composition_authoring_run_pause", "composition_authoring_run_close",
    "composition_authoring_run_accept_unit", "composition_authoring_run_reject_unit",
    # Tier W
    "composition_authoring_run_create", "composition_authoring_run_gate",
    "composition_authoring_run_start", "composition_authoring_run_resume",
    "composition_authoring_run_revert_all",
    # ── W4 narrative-motif-library tools (register on the SAME server) ──
    # Tier R (motif)
    "composition_motif_search", "composition_motif_get",
    "composition_motif_suggest_for_chapter", "composition_arc_suggest",
    "composition_get_mine_job", "composition_motif_link_list",
    "composition_motif_book_list",
    # Tier A (motif)
    "composition_motif_create", "composition_motif_archive", "composition_motif_patch",
    "composition_motif_bind", "composition_motif_unbind",
    "composition_motif_link_create", "composition_motif_link_delete",
    # Tier W (motif)
    "composition_motif_adopt", "composition_motif_mine",
    "composition_arc_import_analyze", "composition_conformance_run",
    # ── 23 structure layer — arc SPEC CRUD + outline reorder (SAME server) ──
    # Tier R (arc reads)
    "composition_arc_list", "composition_arc_get", "composition_arc_template_drift",
    # BA11 (O-3) — the 5 arc-template CRUD MCP tools (the "Full MCP surface" BA11 mandates).
    "composition_arc_template_list", "composition_arc_template_get",
    "composition_arc_template_create", "composition_arc_template_update",
    "composition_arc_template_archive",
    "composition_conformance_status",   # 26 IX-14 staleness read contract
    # Tier A (arc auto-writes + outline move)
    "composition_arc_create", "composition_arc_update", "composition_arc_delete",
    "composition_arc_restore", "composition_arc_move", "composition_arc_assign_chapters",
    "composition_arc_apply", "composition_arc_extract_template",
    "composition_outline_node_move",
    # ── PlanForge (M4) plan_* tools ──
    # Tier R
    "plan_validate", "plan_self_check",
    # Tier A
    "plan_propose_spec", "plan_interpret_feedback", "plan_apply_revision",
    "plan_review_checkpoint", "plan_handoff_autofix", "plan_compile",
    # 27 V2-F1 — the compiler-pass surface. The agent CANNOT skip a checkpoint through these:
    # `plan_run_pass` refuses with its blockers named, and only `plan_review_checkpoint` (which a
    # human drives) clears a blocking pass.
    "plan_run_pass", "plan_pass_status", "plan_link",
    # 28 AN-2/AN-3/AN-4 — the agent's three read surfaces (the gap layer AN-1 enumerates).
    "composition_package_tree", "composition_find_references", "composition_diagnostics",
}
TIER_R = {"composition_get_work", "composition_list_outline",
          "composition_get_outline_node",
          "composition_get_prose", "composition_list_canon_rules",
          "composition_get_generation_job",
          "composition_motif_search", "composition_motif_get",
          "composition_motif_suggest_for_chapter", "composition_arc_suggest",
          "composition_get_mine_job", "composition_motif_link_list",
          "composition_arc_list", "composition_arc_get", "composition_arc_template_drift",
          "composition_arc_template_list", "composition_arc_template_get",  # O-3 reads
          "composition_conformance_status",
          "plan_validate", "plan_self_check",
          "composition_authoring_run_list", "composition_authoring_run_get"}
TIER_W = {"composition_publish", "composition_generate", "composition_decompile_arcs",
          "composition_motif_adopt", "composition_motif_mine",
          "composition_arc_import_analyze", "composition_conformance_run",
          "composition_authoring_run_create", "composition_authoring_run_gate",
          "composition_authoring_run_start", "composition_authoring_run_resume",
          "composition_authoring_run_revert_all",
          "composition_arc_template_create", "composition_arc_template_update",  # O-3 writes
          "composition_arc_template_archive"}


# ── wire-path fixture ─────────────────────────────────────────────────────────


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def mcp_base_url():
    from app.mcp.server import build_mcp_app

    app = build_mcp_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("MCP loopback server did not start in time")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@asynccontextmanager
async def _mcp_client(base_url: str, headers: dict[str, str]):
    async with streamablehttp_client(base_url, headers=headers) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _error_text(result) -> str:
    assert result.content, "expected tool error content, got none"
    return result.content[0].text.lower()


# ── Wire path: catalog + _meta ────────────────────────────────────────────────


async def test_tools_list_returns_the_compose_catalog(mcp_base_url):
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    assert {t.name for t in listing.tools} == EXPECTED_TOOLS


async def test_every_tool_has_description(mcp_base_url):
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    assert listing.tools
    for tool in listing.tools:
        assert tool.name and tool.description, f"{tool.name!r} missing description"


async def test_every_tool_carries_valid_meta(mcp_base_url):
    """C-TOOL: each tool's `_meta` declares a valid tier + scope + synonyms.

    MD-10: the W4 motif tools introduce a `user` scope (motif is a User-tier
    resource with no book_id), so the scope assertion is relaxed from the original
    hardcoded `== 'book'` to `in {'book', 'user'}` (the only valid scopes)."""
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    for tool in listing.tools:
        meta = tool.meta
        assert meta is not None, f"{tool.name!r} has no _meta"
        tier = meta.get("tier")
        assert tier in {"R", "A", "W"}, f"{tool.name}: bad tier {tier!r}"
        assert meta.get("scope") in {"book", "user"}, f"{tool.name}: bad scope {meta.get('scope')!r}"
        syns = meta.get("synonyms")
        assert isinstance(syns, list) and syns, f"{tool.name}: missing synonyms"
        if tool.name in TIER_R:
            assert tier == "R"
        if tool.name in TIER_W:
            assert tier == "W"


async def test_no_tool_leaks_a_scope_arg(mcp_base_url):
    """Identity ids are NEVER tool params — they arrive via the envelope headers."""
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    forbidden = {"user_id", "owner_user_id", "session_id", "ctx", "internal_token"}
    for tool in listing.tools:
        schema = tool.inputSchema
        # Collect every property name anywhere in the schema — top-level AND inside
        # nested arg models, which FastMCP emits as `$defs` referenced by `args`.
        names: set[str] = set(schema.get("properties", {}))
        for definition in (schema.get("$defs") or {}).values():
            names |= set(definition.get("properties", {}))
        leaked = names & forbidden
        assert not leaked, f"{tool.name!r} leaks scope args: {leaked}"


# ── Wire path: identity / auth from headers ───────────────────────────────────


async def test_rejects_missing_internal_token(mcp_base_url):
    async with _mcp_client(mcp_base_url, headers={}) as session:
        result = await session.call_tool("composition_get_work", {"project_id": str(PROJECT)})
    assert result.isError is True
    assert "x-internal-token" in _error_text(result)


async def test_rejects_wrong_internal_token(mcp_base_url):
    headers = {
        "X-Internal-Token": "not-the-real-token",
        "X-User-Id": str(TEST_USER),
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("composition_get_work", {"project_id": str(PROJECT)})
    assert result.isError is True
    assert "invalid internal token" in _error_text(result)


async def test_rejects_bad_user_id_uuid(mcp_base_url):
    headers = {
        "X-Internal-Token": _GOOD_TOKEN,
        "X-User-Id": "not-a-uuid",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("composition_get_work", {"project_id": str(PROJECT)})
    assert result.isError is True
    assert "x-user-id" in _error_text(result)


# ── Handler shape + scope (direct calls, stubbed repos + grant) ───────────────


def _work(user=TEST_USER) -> CompositionWork:
    return CompositionWork(project_id=PROJECT, created_by=user, book_id=BOOK, id=PROJECT, version=1)


def _node(**kw) -> OutlineNode:
    return OutlineNode(
        id=kw.get("id", uuid.uuid4()), created_by=TEST_USER, project_id=PROJECT, book_id=BOOK,
        kind=kw.get("kind", "scene"), rank="a0", title=kw.get("title", "S"),
        status=kw.get("status", "empty"), version=kw.get("version", 1),
    )


def _rule(**kw) -> CanonRule:
    return CanonRule(
        id=kw.get("id", uuid.uuid4()), created_by=TEST_USER, project_id=PROJECT,
        text=kw.get("text", "magic costs HP"), version=kw.get("version", 1),
    )


def _link() -> SceneLink:
    return SceneLink(id=uuid.uuid4(), created_by=TEST_USER, project_id=PROJECT,
                     from_node_id=uuid.uuid4(), to_node_id=uuid.uuid4())


class _Ctx:
    """Stand-in for the kit ToolContext (only `user_id` is read by handlers)."""
    def __init__(self, user_id=TEST_USER):
        self.user_id = user_id
        self.session_id = "sess-1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = _GOOD_TOKEN


@asynccontextmanager
async def _patched(*, grant_level=2, works_get=None, **repo_overrides):
    """Patch the server's `_ctx` (skip header parsing — wire tests cover it), the
    grant resolver (returns `grant_level`), and the repo constructors so handlers
    run against in-memory stubs with no DB/book-service. `grant_level`: 0=no
    access, 1=VIEW, 2=EDIT (loreweave_grants.GrantLevel ints)."""
    import app.mcp.server as srv

    if works_get is None:
        async def works_get(project_id):  # default: caller owns the Work
            return _work()

    works = AsyncMock()
    works.get = AsyncMock(side_effect=works_get)
    works.create = AsyncMock(return_value=_work())

    async def _resolve(book_id, user_id):
        return grant_level

    with patch.object(srv, "_ctx", side_effect=lambda ctx: ctx), \
         patch.object(srv, "_grant_resolver", return_value=_resolve), \
         patch.object(srv, "WorksRepo", return_value=works), \
         patch.object(srv, "get_pool", return_value=object()):
        stack = []
        for name, obj in repo_overrides.items():
            p = patch.object(srv, name, return_value=obj)
            p.start()
            stack.append(p)
        try:
            yield srv
        finally:
            for p in stack:
                p.stop()


async def test_get_work_owner_ok():
    import app.mcp.server as srv
    async with _patched(grant_level=1):
        res = await srv.composition_get_work(_Ctx(), project_id=str(PROJECT))
    assert res["project_id"] == str(PROJECT)


async def test_od8_public_key_owned_only():
    """OD-8 wiring: a public MCP key (ctx.mcp_key_id set) reaches a book ONLY as its
    OWNER — the kit's require_book_owner escalates the bar to OWNER. A caller holding
    a MANAGE share (allowed first-party) is denied for a public key. Proves the ctx
    flows into the guard so the escalation actually fires at composition's call site."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    public = _Ctx()
    public.mcp_key_id = "key-abc"  # marks the call as public → is_owner_only True

    async with _patched(grant_level=3):  # MANAGE — a share, below OWNER
        # First-party (no mcp_key_id) with the same MANAGE share → allowed.
        res = await srv.composition_get_work(_Ctx(), project_id=str(PROJECT))
        assert res["project_id"] == str(PROJECT)
        # Public key → OD-8 requires OWNER; MANAGE(3) < OWNER(4) → denied.
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_work(public, project_id=str(PROJECT))


async def test_get_work_missing_project_rejected():
    """25 PM-9: reads are bare-id + gated at the E0 book grant — a project with no
    Work row (works.get → None) yields the H13 uniform error (no existence oracle),
    regardless of caller. The book-grant DENY path is covered separately below."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async def no_work(project_id):
        return None

    async with _patched(works_get=no_work):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_work(_Ctx(OTHER_USER), project_id=str(PROJECT))


async def test_get_work_grant_denied_rejected():
    """Owns the Work row but holds NO book grant (level 0) → H13 uniform deny."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=0):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_work(_Ctx(), project_id=str(PROJECT))


# ── book_id → Work resolution (M-E live-caught: the agent knows book_id from the
# studio context but every composition tool keys on project_id; without this bridge
# the model retried the book_id AS a project_id and dead-ended) ────────────────


async def test_get_work_by_book_id_resolves_the_project():
    import app.mcp.server as srv

    async with _patched(grant_level=1) as s:
        works = s.WorksRepo(None)  # the patched constructor returns the shared stub
        works.resolve_by_book = AsyncMock(return_value=[_work()])
        res = await srv.composition_get_work(_Ctx(), book_id=str(BOOK))
    assert res["project_id"] == str(PROJECT)
    works.resolve_by_book.assert_awaited_once_with(BOOK)  # 25 PM-9: book-keyed, no user


async def test_get_work_by_book_id_no_marked_work_uniform_deny():
    """No marked Work for that book → H13 uniform deny (indistinguishable from 'not yours')."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async with _patched() as s:
        s.WorksRepo(None).resolve_by_book = AsyncMock(return_value=[])
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_work(_Ctx(), book_id=str(BOOK))


async def test_get_work_by_book_id_multiple_marked_returns_candidates():
    import app.mcp.server as srv

    w2 = _work()
    async with _patched() as s:
        s.WorksRepo(None).resolve_by_book = AsyncMock(return_value=[_work(), w2])
        res = await srv.composition_get_work(_Ctx(), book_id=str(BOOK))
    assert len(res["candidates"]) == 2


async def test_get_work_without_any_id_rejected():
    import app.mcp.server as srv

    async with _patched():
        with pytest.raises(ValueError, match="project_id or book_id"):
            await srv.composition_get_work(_Ctx())


# ── OQ2 (2026-07-07 discovery-hardening spec) — composition_create_work with NO
# project_id auto-resolves/auto-creates the book's default knowledge project. The
# external audit's #7 finding: kg_project_list returns empty for a fresh book, so a
# caller had no discoverable way to obtain a project_id at all. ────────────────


async def test_create_work_no_project_id_auto_creates_default_project():
    """No marked Work AND no pre-existing knowledge project for the book (§6.2
    status='none') — composition_create_work must bootstrap a knowledge project
    itself (via the SAME KnowledgeClient/service-bearer seam composition_get_prose
    already uses) and persist the Work bound to it, without the caller ever
    passing project_id."""
    import app.mcp.server as srv

    new_project_id = uuid.uuid4()

    async def no_existing_work(project_id):
        return None

    knowledge = AsyncMock()
    knowledge.list_projects_for_book = AsyncMock(return_value=[])  # no project yet
    knowledge.create_project = AsyncMock(return_value={"project_id": str(new_project_id)})
    book = AsyncMock()
    book.get_book = AsyncMock(return_value={"title": "My Book"})

    created_work = CompositionWork(
        project_id=new_project_id, created_by=TEST_USER, book_id=BOOK,
        id=new_project_id, version=1,
    )

    async with _patched(grant_level=2, works_get=no_existing_work) as s:
        works = s.WorksRepo(None)
        works.resolve_by_book = AsyncMock(return_value=[])  # no marked Work
        works.create = AsyncMock(return_value=created_work)
        with patch.object(srv, "get_knowledge_client", return_value=knowledge), \
             patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_create_work(_Ctx(), book_id=str(BOOK))

    assert res["project_id"] == str(new_project_id)
    knowledge.create_project.assert_awaited_once()
    works.create.assert_awaited_once_with(TEST_USER, new_project_id, BOOK)


async def test_create_work_no_project_id_second_call_is_idempotent():
    """A second composition_create_work(book_id=...) call (no project_id), once
    the book already has a marked Work (§6.2 status='found'), reuses the SAME
    project — it must NOT call knowledge.create_project again (no duplicate
    project/Work)."""
    import app.mcp.server as srv

    existing_project_id = uuid.uuid4()
    existing_work = CompositionWork(
        project_id=existing_project_id, created_by=TEST_USER, book_id=BOOK,
        id=existing_project_id, version=1,
    )

    async def works_get(project_id):
        if project_id == existing_project_id:
            return existing_work
        return None

    knowledge = AsyncMock()
    knowledge.create_project = AsyncMock(return_value={"project_id": str(uuid.uuid4())})

    async with _patched(grant_level=2, works_get=works_get) as s:
        s.WorksRepo(None).resolve_by_book = AsyncMock(return_value=[existing_work])
        with patch.object(srv, "get_knowledge_client", return_value=knowledge), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_create_work(_Ctx(), book_id=str(BOOK))

    assert res["project_id"] == str(existing_project_id)
    knowledge.create_project.assert_not_awaited()


async def test_create_work_no_project_id_knowledge_outage_degrades_to_pending():
    """A knowledge-service OUTAGE during auto-resolve (list_projects_for_book
    returns None — transport/5xx) must NOT surface as a tool failure — it
    degrades to a lazy null-project pending Work (mirrors the HTTP POST /work
    C16/WG-3 path), so authoring keeps working while knowledge is down."""
    import app.mcp.server as srv

    async def no_existing_work(project_id):
        return None

    pending_work = CompositionWork(
        project_id=None, created_by=TEST_USER, book_id=BOOK,
        id=uuid.uuid4(), pending_project_backfill=True, version=1,
    )

    knowledge = AsyncMock()
    knowledge.list_projects_for_book = AsyncMock(return_value=None)  # outage

    async with _patched(grant_level=2, works_get=no_existing_work) as s:
        works = s.WorksRepo(None)
        works.resolve_by_book = AsyncMock(return_value=[])
        works.get_pending_for_book = AsyncMock(return_value=None)
        works.create_pending = AsyncMock(return_value=pending_work)
        with patch.object(srv, "get_knowledge_client", return_value=knowledge), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_create_work(_Ctx(), book_id=str(BOOK))

    assert res["pending_project_backfill"] is True
    assert res["project_id"] is None
    works.create_pending.assert_awaited_once_with(TEST_USER, BOOK)


async def test_create_work_no_project_id_after_prior_outage_backfills_pending_row_not_duplicate():
    """HIGH-1 (/review-impl finding): a PRIOR knowledge-service outage left a lazy
    pending Work (project_id=NULL, pending_project_backfill=true) for this
    (user,book). Once knowledge recovers, a LATER composition_create_work(book_id)
    call (still no project_id) must backfill THAT SAME row — not mint a brand-new
    composition_work row (and a second knowledge project), which would orphan the
    pending row forever. Uses ONE `knowledge` mock across both calls so
    `create_project` awaited-once proves only ONE project was ever created."""
    import app.mcp.server as srv

    pending_id = uuid.uuid4()
    new_project_id = uuid.uuid4()

    pending_work = CompositionWork(
        project_id=None, created_by=TEST_USER, book_id=BOOK,
        id=pending_id, pending_project_backfill=True, version=1,
    )
    backfilled_work = CompositionWork(
        project_id=new_project_id, created_by=TEST_USER, book_id=BOOK,
        id=pending_id, pending_project_backfill=False, version=2,
    )

    knowledge = AsyncMock()
    # call 1: outage (transport/5xx → None); call 2: recovered, no project yet.
    knowledge.list_projects_for_book = AsyncMock(side_effect=[None, []])
    knowledge.create_project = AsyncMock(return_value={"project_id": str(new_project_id)})
    book = AsyncMock()
    book.get_book = AsyncMock(return_value={"title": "My Book"})

    async def no_existing_work(project_id):
        return None

    # ── call 1: knowledge DOWN → degrades to a lazy pending Work ──
    async with _patched(grant_level=2, works_get=no_existing_work) as s:
        works1 = s.WorksRepo(None)
        works1.resolve_by_book = AsyncMock(return_value=[])
        works1.get_pending_for_book = AsyncMock(return_value=None)
        works1.create_pending = AsyncMock(return_value=pending_work)
        with patch.object(srv, "get_knowledge_client", return_value=knowledge), \
             patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            first = await srv.composition_create_work(_Ctx(), book_id=str(BOOK))

    assert first["pending_project_backfill"] is True
    assert first["project_id"] is None
    knowledge.create_project.assert_not_awaited()

    # ── call 2: knowledge RECOVERED → resolve_work → status="none" (still no
    # marked Work, still no book-typed knowledge project) → create_project
    # succeeds → the PRIOR pending row must be backfilled, not duplicated. ──
    async def existing_work_lookup(project_id):
        # composition_create_work's idempotent-get (`works.get(user, pid)`) must
        # find the NOW-BACKFILLED row (its project_id == new_project_id).
        if project_id == new_project_id:
            return backfilled_work
        return None

    async with _patched(grant_level=2, works_get=existing_work_lookup) as s:
        works2 = s.WorksRepo(None)
        works2.resolve_by_book = AsyncMock(return_value=[])
        works2.get_pending_for_book = AsyncMock(return_value=pending_work)
        works2.backfill_project = AsyncMock(return_value=backfilled_work)
        with patch.object(srv, "get_knowledge_client", return_value=knowledge), \
             patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            second = await srv.composition_create_work(_Ctx(), book_id=str(BOOK))

    assert second["project_id"] == str(new_project_id)
    assert second["pending_project_backfill"] is False
    works2.backfill_project.assert_awaited_once_with(pending_id, new_project_id, created_by=TEST_USER)
    works2.create.assert_not_awaited()  # no SECOND composition_work row inserted
    knowledge.create_project.assert_awaited_once()  # exactly ONE project, across BOTH calls


async def test_create_work_auto_create_404_error_names_owner_only_reason():
    """MED-1 (/review-impl finding): a 404 from knowledge-service's project-create
    route means the caller is a non-owner EDIT-grantee (auto-provisioning a fresh
    knowledge project is OWNER-only) — the error must name the concrete reason +
    a fix pointer, not just 'status 404', so an agent acting for a collaborator
    doesn't retry a call that can never succeed."""
    import app.mcp.server as srv
    from app.clients.knowledge_client import KnowledgeContractError

    async def no_existing_work(project_id):
        return None

    knowledge = AsyncMock()
    knowledge.list_projects_for_book = AsyncMock(return_value=[])
    knowledge.create_project = AsyncMock(side_effect=KnowledgeContractError(404))
    book = AsyncMock()
    book.get_book = AsyncMock(return_value={"title": "My Book"})

    async with _patched(grant_level=2, works_get=no_existing_work) as s:
        s.WorksRepo(None).resolve_by_book = AsyncMock(return_value=[])
        with patch.object(srv, "get_knowledge_client", return_value=knowledge), \
             patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_create_work(_Ctx(), book_id=str(BOOK))

    assert res["success"] is False
    assert "only the book owner can auto-provision" in res["error"]
    assert "project_id" in res["error"]
    assert "composition_get_work" in res["error"]


async def test_create_work_still_accepts_explicit_project_id():
    """Back-compat: a caller that already knows project_id (unchanged behavior)."""
    import app.mcp.server as srv

    async with _patched(grant_level=2):
        res = await srv.composition_create_work(
            _Ctx(), book_id=str(BOOK), project_id=str(PROJECT),
        )
    assert res["project_id"] == str(PROJECT)


async def test_get_generation_job_owner_ok():
    """A generation job that belongs to the caller's Work+project is returned."""
    import app.mcp.server as srv
    from app.db.models import GenerationJob

    job_id = uuid.uuid4()
    job = GenerationJob(id=job_id, created_by=TEST_USER, project_id=PROJECT, book_id=BOOK,
                        operation="generate", status="completed")
    jobs = AsyncMock()
    jobs.get = AsyncMock(return_value=job)
    async with _patched(grant_level=1, GenerationJobsRepo=jobs):
        res = await srv.composition_get_generation_job(
            _Ctx(), project_id=str(PROJECT), job_id=str(job_id),
        )
    assert res["id"] == str(job_id)
    assert res["status"] == "completed"
    # 25 re-key: jobs.get is BARE-ID; the IDOR scope check is job.project_id == pid.
    jobs.get.assert_awaited_once_with(job_id)


async def test_get_generation_job_foreign_project_rejected():
    """A job_id the caller owns but under a DIFFERENT project is not readable here
    (no cross-Work leak) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError
    from app.db.models import GenerationJob

    job_id, other_project = uuid.uuid4(), uuid.uuid4()
    job = GenerationJob(id=job_id, created_by=TEST_USER, project_id=other_project, book_id=BOOK,
                        operation="generate", status="completed")
    jobs = AsyncMock()
    jobs.get = AsyncMock(return_value=job)
    async with _patched(grant_level=1, GenerationJobsRepo=jobs):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_generation_job(
                _Ctx(), project_id=str(PROJECT), job_id=str(job_id),
            )


async def test_get_generation_job_missing_rejected():
    """An unknown job_id (repo returns None — user-scoped miss) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    jobs = AsyncMock()
    jobs.get = AsyncMock(return_value=None)
    async with _patched(grant_level=1, GenerationJobsRepo=jobs):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_generation_job(
                _Ctx(), project_id=str(PROJECT), job_id=str(uuid.uuid4()),
            )


# ── composition_get_outline_node — the cheap single-node read's IDOR guard
# (T1 review MED-1: the security-load-bearing `node.project_id != pid` check must
# be proven by test, same discipline as get_generation_job above). ──────────────


async def test_get_outline_node_owner_ok():
    """A node in the caller's Work+project is returned with its version (the
    concurrency token the whole tool exists to hand back)."""
    import app.mcp.server as srv

    node_id = uuid.uuid4()
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_node(id=node_id, version=4))
    async with _patched(grant_level=1, OutlineRepo=outline):
        res = await srv.composition_get_outline_node(
            _Ctx(), project_id=str(PROJECT), node_id=str(node_id),
        )
    assert res["id"] == str(node_id)
    assert res["version"] == 4
    outline.get_node.assert_awaited_once_with(node_id)  # 25 PM-9: bare-id; IDOR via project_id


async def test_get_outline_node_foreign_project_rejected():
    """A node_id the caller owns but under a DIFFERENT Work/project is not readable
    through this project (no cross-Work leak) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    other_project = uuid.uuid4()
    foreign = OutlineNode(
        id=uuid.uuid4(), created_by=TEST_USER, project_id=other_project, book_id=BOOK,
        kind="scene", rank="a0", title="S", status="empty", version=1,
    )
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=foreign)
    async with _patched(grant_level=1, OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_outline_node(
                _Ctx(), project_id=str(PROJECT), node_id=str(foreign.id),
            )


async def test_get_outline_node_missing_rejected():
    """An unknown node_id (repo returns None — user-scoped miss) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=None)
    async with _patched(grant_level=1, OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_outline_node(
                _Ctx(), project_id=str(PROJECT), node_id=str(uuid.uuid4()),
            )


async def test_outline_node_create_returns_undo_hint():
    import app.mcp.server as srv

    outline = AsyncMock()
    created = _node(id=uuid.uuid4(), title="New scene")
    outline.create_node = AsyncMock(return_value=created)
    async with _patched(OutlineRepo=outline):
        res = await srv.composition_outline_node_create(
            _Ctx(), srv._NodeCreateArgs(project_id=str(PROJECT), kind="scene", title="New scene"),
        )
    undo = res["_meta"]["undo_hint"]
    assert undo["tool"] == "composition_outline_node_delete"
    assert undo["args"]["node_id"] == str(created.id)


async def test_canon_rule_create_returns_undo_hint():
    import app.mcp.server as srv

    canon = AsyncMock()
    rule = _rule(id=uuid.uuid4())
    canon.create = AsyncMock(return_value=rule)
    async with _patched(CanonRulesRepo=canon):
        res = await srv.composition_canon_rule_create(
            _Ctx(), srv._CanonRuleCreateArgs(project_id=str(PROJECT), text="magic costs HP"),
        )
    undo = res["_meta"]["undo_hint"]
    assert undo["tool"] == "composition_canon_rule_delete"
    assert undo["args"]["rule_id"] == str(rule.id)


async def test_scene_link_create_returns_undo_hint():
    import app.mcp.server as srv

    links = AsyncMock()
    link = _link()
    links.create = AsyncMock(return_value=link)
    async with _patched(SceneLinksRepo=links):
        res = await srv.composition_scene_link_create(
            _Ctx(),
            srv._SceneLinkCreateArgs(
                project_id=str(PROJECT),
                from_node_id=str(link.from_node_id), to_node_id=str(link.to_node_id),
            ),
        )
    assert res["_meta"]["undo_hint"]["tool"] == "composition_scene_link_delete"


def test_scene_link_create_kind_is_closed_set():
    """H5/IN-2: the MCP arg `kind` is a Literal (setup_payoff|custom), so a bad value from a
    weak model fails validation at the schema (422) instead of reaching the DB CHECK (500).
    Mirrors the REST mirror's LinkKind guard."""
    import app.mcp.server as srv
    from pydantic import ValidationError

    nid = str(PROJECT)  # any string id; only `kind` is under test here
    # Valid values construct cleanly.
    for k in ("setup_payoff", "custom"):
        srv._SceneLinkCreateArgs(project_id=str(PROJECT), from_node_id=nid, to_node_id=nid, kind=k)
    # A value outside the closed set is rejected at construction (Pydantic Literal → 422).
    with pytest.raises(ValidationError):
        srv._SceneLinkCreateArgs(project_id=str(PROJECT), from_node_id=nid, to_node_id=nid, kind="Setup")


async def test_outline_node_update_undo_none_when_prior_was_null():
    """SC4-UNDO regression: setting a NULLABLE SC4 field (value_shift) from NULL→value has
    no faithful single-op reverse — the sparse update patch treats None as leave-unchanged
    (no clear verb), so an `undo_hint` listing value_shift=null would silently no-op. The
    handler must emit undo_hint=None (honest) rather than a lying hint."""
    import app.mcp.server as srv

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_node(version=5))          # value_shift defaults None
    outline.update_node = AsyncMock(return_value=_node(version=6))
    async with _patched(OutlineRepo=outline):
        res = await srv.composition_outline_node_update(
            _Ctx(),
            srv._NodeUpdateArgs(
                project_id=str(PROJECT), node_id=str(_node().id),
                expected_version=5, value_shift=50,
            ),
        )
    assert res["_meta"]["undo_hint"] is None, "a null-prior SC4 edit must not emit a lying undo"


async def test_outline_node_update_undo_present_for_notnull_field():
    """The common case stays reversible: a NOT NULL field (title) has a non-None prior, so
    the undo_hint restores it."""
    import app.mcp.server as srv

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_node(version=5, title="old"))
    outline.update_node = AsyncMock(return_value=_node(version=6, title="new"))
    async with _patched(OutlineRepo=outline):
        res = await srv.composition_outline_node_update(
            _Ctx(),
            srv._NodeUpdateArgs(
                project_id=str(PROJECT), node_id=str(_node().id),
                expected_version=5, title="new",
            ),
        )
    undo = res["_meta"]["undo_hint"]
    assert undo is not None and undo["tool"] == "composition_outline_node_update"
    assert undo["args"]["title"] == "old"


async def test_outline_node_update_stale_version_is_conflict():
    """A stale expected_version → applied_conflict outcome (no blind clobber)."""
    import app.mcp.server as srv
    from app.db.repositories import VersionMismatchError

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_node(version=5, title="old"))
    outline.update_node = AsyncMock(side_effect=VersionMismatchError(_node(version=7)))
    async with _patched(OutlineRepo=outline):
        res = await srv.composition_outline_node_update(
            _Ctx(),
            srv._NodeUpdateArgs(
                project_id=str(PROJECT), node_id=str(uuid.uuid4()),
                expected_version=5, title="new",
            ),
        )
    assert res["success"] is False
    assert res["outcome"] == "applied_conflict"
    assert res["current_version"] == 7


# ── Fix 1 regression: by-id writes are project-scoped to the resolved Work ──────
#
# The Work gate resolves on the passed project_id (work.book_id is checked), but the
# node/rule/link repos filter on (user_id, id) only. A same-user caller could pass a
# project_id from Work-A with a node_id from their OWN Work-B (book B) — gating book
# A's grant tier instead of book B's. The handlers now assert the target row's
# project_id == the resolved Work's project_id, else H13 uniform not-accessible.

OTHER_PROJECT = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def _foreign_node(**kw) -> OutlineNode:
    """A node the caller owns but that lives in a DIFFERENT project (Work-B)."""
    return OutlineNode(
        id=kw.get("id", uuid.uuid4()), created_by=TEST_USER, project_id=OTHER_PROJECT, book_id=BOOK,
        kind="scene", rank="a0", title="foreign", status="empty",
        version=kw.get("version", 1),
    )


def _foreign_rule(**kw) -> CanonRule:
    return CanonRule(
        id=kw.get("id", uuid.uuid4()), created_by=TEST_USER, project_id=OTHER_PROJECT,
        text="foreign rule", version=kw.get("version", 1),
    )


async def test_outline_node_update_foreign_project_refused():
    """A node_id belonging to the caller's OTHER Work (project ≠ the passed
    project_id) is refused uniformly — the node is never mutated."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_foreign_node(version=1))
    outline.update_node = AsyncMock()
    async with _patched(OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_outline_node_update(
                _Ctx(),
                srv._NodeUpdateArgs(
                    project_id=str(PROJECT), node_id=str(uuid.uuid4()),
                    expected_version=1, title="new",
                ),
            )
    outline.update_node.assert_not_awaited()


async def test_outline_node_delete_foreign_project_refused():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_foreign_node())
    outline.archive_node = AsyncMock()
    async with _patched(OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_outline_node_delete(
                _Ctx(), project_id=str(PROJECT), node_id=str(uuid.uuid4()),
            )
    outline.archive_node.assert_not_awaited()


async def test_outline_node_restore_foreign_project_refused():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_foreign_node())
    outline.restore_node = AsyncMock()
    async with _patched(OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_outline_node_restore(
                _Ctx(), project_id=str(PROJECT), node_id=str(uuid.uuid4()),
            )
    outline.restore_node.assert_not_awaited()


async def test_canon_rule_update_foreign_project_refused():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    canon = AsyncMock()
    canon.get = AsyncMock(return_value=_foreign_rule(version=1))
    canon.update = AsyncMock()
    async with _patched(CanonRulesRepo=canon):
        with pytest.raises(NotAccessibleError):
            await srv.composition_canon_rule_update(
                _Ctx(),
                srv._CanonRuleUpdateArgs(
                    project_id=str(PROJECT), rule_id=str(uuid.uuid4()),
                    expected_version=1, text="new",
                ),
            )
    canon.update.assert_not_awaited()


async def test_canon_rule_delete_foreign_project_refused():
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    canon = AsyncMock()
    canon.get = AsyncMock(return_value=_foreign_rule())
    canon.archive = AsyncMock()
    async with _patched(CanonRulesRepo=canon):
        with pytest.raises(NotAccessibleError):
            await srv.composition_canon_rule_delete(
                _Ctx(), project_id=str(PROJECT), rule_id=str(uuid.uuid4()),
            )
    canon.archive.assert_not_awaited()


async def test_scene_link_delete_foreign_project_refused():
    """The repo WHERE clause is constrained by project_id, so a foreign-project
    edge matches 0 rows → delete returns False → uniform refusal. The handler
    passes the resolved Work's project_id into the repo delete."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    links = AsyncMock()
    # delete() returns False when the (project_id, id) pair matches nothing (25 PM-9).
    links.delete = AsyncMock(return_value=False)
    async with _patched(SceneLinksRepo=links):
        with pytest.raises(NotAccessibleError):
            await srv.composition_scene_link_delete(
                _Ctx(), project_id=str(PROJECT), link_id=str(uuid.uuid4()),
            )
    # The handler must constrain the repo delete by the resolved Work's project_id.
    # 25 PM-9: delete is bare (project_id, link_id) — project_id is the 1st positional.
    args, _ = links.delete.await_args
    assert args[0] == PROJECT


async def test_write_prose_stale_draft_version_rejected():
    """composition_write_prose surfaces a book-service 409 as applied_conflict —
    the MANDATORY expected_draft_version guards against a blind clobber."""
    import app.mcp.server as srv

    book = AsyncMock()
    book.get_draft = AsyncMock(return_value={"body": {"type": "doc", "content": []}, "draft_version": 3})
    book.patch_draft = AsyncMock(side_effect=BookClientError(409, "CHAPTER_DRAFT_CONFLICT"))
    async with _patched():
        with patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_write_prose(
                _Ctx(),
                srv._WriteProseArgs(
                    project_id=str(PROJECT), chapter_id=str(CHAPTER),
                    body={"type": "doc", "content": []}, expected_draft_version=2,
                ),
            )
    assert res["success"] is False
    assert res["outcome"] == "applied_conflict"


async def test_write_prose_ok_returns_undo_hint():
    import app.mcp.server as srv

    book = AsyncMock()
    prior_body = {"type": "doc", "content": [{"type": "paragraph"}]}
    book.get_draft = AsyncMock(return_value={"body": prior_body, "draft_version": 3})
    book.patch_draft = AsyncMock(return_value={"draft_version": 4, "body": {"type": "doc", "content": []}})
    async with _patched():
        with patch.object(srv, "get_book_client", return_value=book), \
             patch.object(srv, "mint_service_bearer", return_value="tok"):
            res = await srv.composition_write_prose(
                _Ctx(),
                srv._WriteProseArgs(
                    project_id=str(PROJECT), chapter_id=str(CHAPTER),
                    body={"type": "doc", "content": []}, expected_draft_version=3,
                ),
            )
    undo = res["_meta"]["undo_hint"]
    assert undo["tool"] == "composition_write_prose"
    # Undo restores the PRIOR body at the NEW version (4).
    assert undo["args"]["body"] == prior_body
    assert undo["args"]["expected_draft_version"] == 4


async def test_publish_mints_confirm_token_when_publishable():
    """Tier-W propose: a publishable chapter yields a confirm_token + descriptor;
    nothing is published yet (the confirm route is the only write path)."""
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    outline = AsyncMock()
    outline.chapter_scene_gate = AsyncMock(return_value={"can_publish": True, "scenes_total": 2, "scenes_done": 2})
    async with _patched(OutlineRepo=outline):
        res = await srv.composition_publish(_Ctx(), project_id=str(PROJECT), chapter_id=str(CHAPTER))
    assert res["descriptor"] == "composition.publish"
    assert res["domain"] == "composition"
    # Key-split: the confirm token is signed with the DEDICATED secret, NOT the
    # envelope gate token — verifying with internal_service_token would now FAIL.
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.user_id == TEST_USER
    assert claims.resource_id == CHAPTER
    assert claims.payload["chapter_id"] == str(CHAPTER)


async def test_publish_refused_when_not_publishable():
    import app.mcp.server as srv

    outline = AsyncMock()
    outline.chapter_scene_gate = AsyncMock(return_value={"can_publish": False, "scenes_total": 2, "scenes_done": 1})
    async with _patched(OutlineRepo=outline):
        res = await srv.composition_publish(_Ctx(), project_id=str(PROJECT), chapter_id=str(CHAPTER))
    assert res["success"] is False
    assert "confirm_token" not in res


# ── composition_generate (Tier-W propose: cost-gated cowrite engine) ───────────

MODEL_REF = uuid.UUID("11111111-2222-3333-4444-555555555555")


async def test_generate_chapter_mints_confirm_token():
    """A chapter target mints a verifiable composition.generate token whose payload
    captures the resolved spec; nothing is generated yet."""
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2):
        res = await srv.composition_generate(
            _Ctx(),
            srv._GenerateArgs(
                project_id=str(PROJECT), chapter_id=str(CHAPTER),
                model_source="user_model", model_ref=str(MODEL_REF), guide="dark tone",
            ),
        )
    assert res["descriptor"] == "composition.generate"
    assert res["domain"] == "composition"
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.user_id == TEST_USER
    assert claims.resource_id == CHAPTER
    assert claims.payload["target_kind"] == "chapter"
    assert claims.payload["target_id"] == str(CHAPTER)
    assert claims.payload["model_ref"] == str(MODEL_REF)
    assert claims.payload["guide"] == "dark tone"


async def test_generate_scene_mints_confirm_token():
    """A scene target validates the node belongs to the Work's project, then mints."""
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    scene = _node(id=uuid.uuid4(), kind="scene")
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=scene)
    async with _patched(grant_level=2, OutlineRepo=outline):
        res = await srv.composition_generate(
            _Ctx(),
            srv._GenerateArgs(
                project_id=str(PROJECT), outline_node_id=str(scene.id),
                model_source="user_model", model_ref=str(MODEL_REF),
            ),
        )
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.resource_id == scene.id
    assert claims.payload["target_kind"] == "scene"
    assert claims.payload["target_id"] == str(scene.id)


async def test_generate_requires_exactly_one_target():
    """Both targets, or neither, is a clean refusal (no token, no spend)."""
    import app.mcp.server as srv

    async with _patched(grant_level=2):
        both = await srv.composition_generate(
            _Ctx(),
            srv._GenerateArgs(
                project_id=str(PROJECT), chapter_id=str(CHAPTER),
                outline_node_id=str(uuid.uuid4()),
                model_source="user_model", model_ref=str(MODEL_REF),
            ),
        )
        neither = await srv.composition_generate(
            _Ctx(),
            srv._GenerateArgs(
                project_id=str(PROJECT), model_source="user_model", model_ref=str(MODEL_REF),
            ),
        )
    for res in (both, neither):
        assert res["success"] is False
        assert "confirm_token" not in res


async def test_generate_scene_foreign_project_refused():
    """A scene node in the caller's OTHER Work (project ≠ passed project_id) → H13."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=_foreign_node())
    async with _patched(grant_level=2, OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_generate(
                _Ctx(),
                srv._GenerateArgs(
                    project_id=str(PROJECT), outline_node_id=str(uuid.uuid4()),
                    model_source="user_model", model_ref=str(MODEL_REF),
                ),
            )


async def test_generate_grant_denied_refused():
    """No EDIT grant on the book → H13 uniform deny before any token mint."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=0):
        with pytest.raises(NotAccessibleError):
            await srv.composition_generate(
                _Ctx(),
                srv._GenerateArgs(
                    project_id=str(PROJECT), chapter_id=str(CHAPTER),
                    model_source="user_model", model_ref=str(MODEL_REF),
                ),
            )
