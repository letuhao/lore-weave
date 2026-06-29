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
    # ── W4 narrative-motif-library tools (register on the SAME server) ──
    # Tier R (motif)
    "composition_motif_search", "composition_motif_get",
    "composition_motif_suggest_for_chapter", "composition_arc_suggest",
    "composition_get_mine_job", "composition_motif_link_list",
    "composition_motif_book_list",
    # Tier A (motif)
    "composition_motif_create", "composition_motif_archive",
    "composition_motif_bind", "composition_motif_unbind",
    "composition_motif_link_create", "composition_motif_link_delete",
    # Tier W (motif)
    "composition_motif_adopt", "composition_motif_mine",
    "composition_arc_import_analyze", "composition_conformance_run",
}
TIER_R = {"composition_get_work", "composition_list_outline",
          "composition_get_prose", "composition_list_canon_rules",
          "composition_get_generation_job",
          "composition_motif_search", "composition_motif_get",
          "composition_motif_suggest_for_chapter", "composition_arc_suggest",
          "composition_get_mine_job", "composition_motif_link_list"}
TIER_W = {"composition_publish", "composition_generate",
          "composition_motif_adopt", "composition_motif_mine",
          "composition_arc_import_analyze", "composition_conformance_run"}


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
    return CompositionWork(project_id=PROJECT, user_id=user, book_id=BOOK, id=PROJECT, version=1)


def _node(**kw) -> OutlineNode:
    return OutlineNode(
        id=kw.get("id", uuid.uuid4()), user_id=TEST_USER, project_id=PROJECT,
        kind=kw.get("kind", "scene"), rank="a0", title=kw.get("title", "S"),
        status=kw.get("status", "empty"), version=kw.get("version", 1),
    )


def _rule(**kw) -> CanonRule:
    return CanonRule(
        id=kw.get("id", uuid.uuid4()), user_id=TEST_USER, project_id=PROJECT,
        text=kw.get("text", "magic costs HP"), version=kw.get("version", 1),
    )


def _link() -> SceneLink:
    return SceneLink(id=uuid.uuid4(), user_id=TEST_USER, project_id=PROJECT,
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
        async def works_get(user_id, project_id):  # default: caller owns the Work
            return _work(user_id) if user_id == TEST_USER else None

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


async def test_get_work_non_owner_rejected():
    """A caller with NO Work row (the repo filters on user_id) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    async def no_work(user_id, project_id):
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


async def test_get_generation_job_owner_ok():
    """A generation job that belongs to the caller's Work+project is returned."""
    import app.mcp.server as srv
    from app.db.models import GenerationJob

    job_id = uuid.uuid4()
    job = GenerationJob(id=job_id, user_id=TEST_USER, project_id=PROJECT,
                        operation="generate", status="completed")
    jobs = AsyncMock()
    jobs.get = AsyncMock(return_value=job)
    async with _patched(grant_level=1, GenerationJobsRepo=jobs):
        res = await srv.composition_get_generation_job(
            _Ctx(), project_id=str(PROJECT), job_id=str(job_id),
        )
    assert res["id"] == str(job_id)
    assert res["status"] == "completed"
    jobs.get.assert_awaited_once_with(TEST_USER, job_id)


async def test_get_generation_job_foreign_project_rejected():
    """A job_id the caller owns but under a DIFFERENT project is not readable here
    (no cross-Work leak) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError
    from app.db.models import GenerationJob

    job_id, other_project = uuid.uuid4(), uuid.uuid4()
    job = GenerationJob(id=job_id, user_id=TEST_USER, project_id=other_project,
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
        id=kw.get("id", uuid.uuid4()), user_id=TEST_USER, project_id=OTHER_PROJECT,
        kind="scene", rank="a0", title="foreign", status="empty",
        version=kw.get("version", 1),
    )


def _foreign_rule(**kw) -> CanonRule:
    return CanonRule(
        id=kw.get("id", uuid.uuid4()), user_id=TEST_USER, project_id=OTHER_PROJECT,
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
    # delete() returns False when the (user_id, id, project_id) triple matches nothing.
    links.delete = AsyncMock(return_value=False)
    async with _patched(SceneLinksRepo=links):
        with pytest.raises(NotAccessibleError):
            await srv.composition_scene_link_delete(
                _Ctx(), project_id=str(PROJECT), link_id=str(uuid.uuid4()),
            )
    # The handler must constrain the repo delete by the resolved Work's project_id.
    _, kwargs = links.delete.await_args
    assert kwargs.get("project_id") == PROJECT


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
