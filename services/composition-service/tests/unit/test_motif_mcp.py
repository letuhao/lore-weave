"""W4 — narrative-motif-library MCP tools + Tier-W confirm effects (motif library).

Three layers (mirrors test_mcp_server.py + test_mcp_actions.py):

  1. **Wire path** (loopback uvicorn, real streamable-HTTP): the motif tools are in
     the catalog; each carries valid `_meta`; no motif tool leaks a scope/identity
     arg; the closed Literal enums make a system/both-NULL/public-at-create row
     UNCONSTRUCTIBLE.

  2. **Handler shape + scope** (direct calls, stubbed repos): the read predicate /
     allow-list projection; per-tool IDOR (foreign motif / node / job); owner-stamp
     on create; the Tier-W propose mints a confirm token (no effect at propose).

  3. **Confirm-route** (FastAPI TestClient): adopt clones; mine enqueues 202;
     W-replay blocked by the ledger; the real billing precheck denies over-quota /
     fails closed on a billing outage; the import user-scope guard.

The §6 audit risk-guards (H-6/MCP-R1, MCP-R2, MCP-R4, S1, S2, B-2, B-4, W-replay)
are each a test here.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.py sets the required env BEFORE app import.

_GOOD_TOKEN = "test_token"  # matches tests/conftest.py INTERNAL_SERVICE_TOKEN
TEST_USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_USER = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BOOK = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PROJECT = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
NODE = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
OTHER_PROJECT = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

MOTIF_TOOLS = {
    "composition_motif_search", "composition_motif_get",
    "composition_motif_suggest_for_chapter", "composition_arc_suggest",
    "composition_get_mine_job",
    "composition_motif_create", "composition_motif_archive",
    "composition_motif_bind", "composition_motif_unbind",
    "composition_motif_adopt", "composition_motif_mine",
    "composition_arc_import_analyze", "composition_conformance_run",
}
MOTIF_USER_SCOPE = {
    "composition_motif_search", "composition_motif_get",
    "composition_motif_create", "composition_motif_archive",
    "composition_motif_adopt", "composition_arc_import_analyze",
}


# ── helpers to build stub Motif rows (uses the real F0 model) ─────────────────


def _motif(**kw):
    from app.db.models import Motif

    base = dict(
        id=kw.get("id", uuid.uuid4()),
        owner_user_id=kw.get("owner_user_id", TEST_USER),
        code=kw.get("code", "cultivation.fortuitous_encounter"),
        name=kw.get("name", "Fortuitous Encounter"),
        language="en", visibility=kw.get("visibility", "private"),
        kind="sequence", summary="a lucky meeting",
        genre_tags=kw.get("genre_tags", ["xianxia"]),
        embedding_model="platform-bge", status=kw.get("status", "active"), version=1,
    )
    return Motif(**base)


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1 — catalog + _meta + arg-shape (in-process list_tools — NO second loopback
# uvicorn: the live streamable-HTTP envelope path is covered by test_mcp_server.py;
# a SECOND module-scoped loopback server collides with FastMCP's once-per-instance
# session manager. Introspect the SAME mcp_server directly — same Tool objects
# (name/meta/inputSchema), no server lifecycle.)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
async def motif_tool_listing():
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    return {t.name: t for t in tools}


async def test_motif_tools_in_catalog(motif_tool_listing):
    names = set(motif_tool_listing)
    assert MOTIF_TOOLS <= names, f"missing motif tools: {MOTIF_TOOLS - names}"


async def test_motif_tools_meta_valid(motif_tool_listing):
    """Each motif tool: tier ∈ {R,A,W}, scope ∈ {book,user}, non-empty synonyms.
    The user-scope tools declare scope='user' (the MD-10 relaxation)."""
    for name in MOTIF_TOOLS:
        meta = motif_tool_listing[name].meta
        assert meta is not None, f"{name}: no _meta"
        assert meta.get("tier") in {"R", "A", "W"}, f"{name}: bad tier"
        assert meta.get("scope") in {"book", "user"}, f"{name}: bad scope"
        syns = meta.get("synonyms")
        assert isinstance(syns, list) and syns, f"{name}: missing synonyms"
    for name in MOTIF_USER_SCOPE:
        assert motif_tool_listing[name].meta.get("scope") == "user", f"{name}: expected user scope"


async def test_adopt_is_tier_W(motif_tool_listing):
    """H-6 / MCP-R1: adopt is Tier-W (confirm-token), NOT Tier-A auto-write."""
    assert motif_tool_listing["composition_motif_adopt"].meta.get("tier") == "W"


async def test_no_motif_tool_leaks_scope_arg(motif_tool_listing):
    """S2 (echo): identity ids are NEVER motif-tool params — owner from envelope."""
    forbidden = {"user_id", "owner_user_id", "session_id", "ctx", "internal_token"}
    for name in MOTIF_TOOLS:
        schema = motif_tool_listing[name].inputSchema
        names: set[str] = set(schema.get("properties", {}))
        for definition in (schema.get("$defs") or {}).values():
            names |= set(definition.get("properties", {}))
        leaked = names & forbidden
        assert not leaked, f"{name!r} leaks scope args: {leaked}"


def test_create_target_enum_rejects_book_and_system():
    """S2: target is a closed Literal['user'] → a both-NULL/system/book row is
    UNCONSTRUCTIBLE by the LLM (pydantic refuses at propose)."""
    from app.mcp.server import _MotifCreateArgs

    _MotifCreateArgs(target="user", code="x", name="X")  # valid
    for bad in ("book", "system", "public"):
        with pytest.raises(Exception):
            _MotifCreateArgs(target=bad, code="x", name="X")


def test_create_visibility_excludes_public():
    """S2: visibility is Literal['private','unlisted'] at create — 'public' is the
    separate publish path, not a create-time arg (a public-at-birth row would skip
    the publish gate)."""
    from app.mcp.server import _MotifCreateArgs

    _MotifCreateArgs(code="x", name="X", visibility="unlisted")  # valid
    with pytest.raises(Exception):
        _MotifCreateArgs(code="x", name="X", visibility="public")


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2 — handler shape + scope (direct calls, stubbed repos)
# ══════════════════════════════════════════════════════════════════════════════


class _Ctx:
    def __init__(self, user_id=TEST_USER):
        self.user_id = user_id
        self.session_id = "sess-1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = _GOOD_TOKEN


def _work(user=TEST_USER):
    from app.db.models import CompositionWork
    return CompositionWork(project_id=PROJECT, user_id=user, book_id=BOOK, id=PROJECT, version=1)


@asynccontextmanager
async def _patched(*, grant_level=2, works_get=None, **repo_overrides):
    """Patch the server `_ctx` (skip header parse), the grant resolver, and the repo
    constructors — same shape as test_mcp_server's _patched."""
    import app.mcp.server as srv

    if works_get is None:
        async def works_get(user_id, project_id):
            return _work(user_id) if user_id == TEST_USER else None

    works = AsyncMock()
    works.get = AsyncMock(side_effect=works_get)

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


async def test_search_applies_allow_list_projection():
    """The read predicate is in the repo SELECT; the handler returns the allow-list
    projection (no embedding key leaks in a list view)."""
    import app.mcp.server as srv

    repo = AsyncMock()
    repo.list_for_caller = AsyncMock(return_value=[_motif(), _motif(owner_user_id=OTHER_USER, visibility="public")])
    async with _patched(MotifRepo=repo):
        res = await srv.composition_motif_search(_Ctx(), srv._MotifSearchArgs(scope="all"))
    assert res["count"] == 2
    for m in res["motifs"]:
        assert "embedding" not in m and "embedding_model" not in m
        assert "owner_user_id" not in m


async def test_get_owner_full_vs_public_projection():
    """Owner sees the full row; a public-not-owned row is the allow-list projection."""
    import app.mcp.server as srv

    owned = _motif(owner_user_id=TEST_USER)
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=owned)
    async with _patched(MotifRepo=repo):
        res = await srv.composition_motif_get(_Ctx(), motif_id=str(owned.id))
    assert res["owner_user_id"] == str(TEST_USER)  # full dump includes owner

    public = _motif(owner_user_id=OTHER_USER, visibility="public")
    repo.get_visible = AsyncMock(return_value=public)
    async with _patched(MotifRepo=repo):
        res = await srv.composition_motif_get(_Ctx(), motif_id=str(public.id))
    assert "owner_user_id" not in res and "embedding_model" not in res


async def test_get_foreign_private_uniform():
    """S1: a foreign private id (get_visible → None) → H13 uniform error."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=None)
    async with _patched(MotifRepo=repo):
        with pytest.raises(NotAccessibleError):
            await srv.composition_motif_get(_Ctx(), motif_id=str(uuid.uuid4()))


async def test_suggest_foreign_node_uniform():
    """S1: a node with project_id != pid → H13 uniform error (per-tool IDOR)."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError
    from app.db.models import OutlineNode

    foreign = OutlineNode(id=NODE, user_id=TEST_USER, project_id=OTHER_PROJECT,
                          kind="chapter", rank="a0", title="C", status="empty", version=1)
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=foreign)
    async with _patched(grant_level=1, OutlineRepo=outline):
        with pytest.raises(NotAccessibleError):
            await srv.composition_motif_suggest_for_chapter(
                _Ctx(), project_id=str(PROJECT), node_id=str(NODE),
            )


async def test_create_stamps_owner_from_envelope():
    """B-2 (echo): MotifRepo.create is awaited with tc.user_id; no arg overrides it."""
    import app.mcp.server as srv

    created = _motif()
    repo = AsyncMock()
    repo.create = AsyncMock(return_value=created)
    async with _patched(MotifRepo=repo):
        res = await srv.composition_motif_create(
            _Ctx(), srv._MotifCreateArgs(code="x", name="X"),
        )
    awaited_user = repo.create.await_args.args[0]
    assert awaited_user == TEST_USER
    # honest undo target = the reverse-op archive tool.
    assert res["_meta"]["undo_hint"]["tool"] == "composition_motif_archive"


async def test_archive_user_scope_foreign_rejected():
    """S1: archiving a foreign/system motif (owner-resolver deny) → H13."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError

    repo = AsyncMock()
    # owner-resolver reads get_visible → a system row (owner None) is read-only.
    repo.get_visible = AsyncMock(return_value=_motif(owner_user_id=None, visibility="unlisted"))
    repo.archive = AsyncMock()
    async with _patched(MotifRepo=repo):
        with pytest.raises(NotAccessibleError):
            await srv.composition_motif_archive(_Ctx(), motif_id=str(uuid.uuid4()))
    repo.archive.assert_not_awaited()


class _FakeTxn:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return False


class _FakeConn:
    def transaction(self): return _FakeTxn()


class _FakePoolCM:
    async def __aenter__(self): return _FakeConn()
    async def __aexit__(self, *a): return False


class _FakePool:
    """A pool whose acquire()/transaction() are no-op async CMs — so the wired
    bind/unbind tools can run their `async with pool.acquire()/c.transaction()` blocks
    while the engine call itself is mocked."""
    def acquire(self): return _FakePoolCM()


def _swap_result(**kw):
    from types import SimpleNamespace
    base = dict(
        chapter_node_id=str(NODE), archived_scene_ids=["s-old"],
        new_scene_ids=["s-new-1", "s-new-2"], orphaned_thread_ids=[],
        new_motif_id=str(uuid.uuid4()),
        undo_token={"chapter_node_id": str(NODE), "archived_scene_ids": ["s-old"],
                    "new_scene_ids": ["s-new-1", "s-new-2"]},
    )
    base.update(kw)
    return SimpleNamespace(**base)


async def test_bind_wires_to_swap_engine_and_returns_undo_token():
    """D-MOTIF-MCP-BIND-WIRING (cleared): composition_motif_bind validates work/gate +
    the two IDOR checks, then calls W2's apply_motif_swap in one tx (the one-engine-two-
    entries seam) and returns the real swap result + the undo_token (the verified A-tier
    inverse via composition_motif_unbind)."""
    import app.mcp.server as srv
    from app.db.models import OutlineNode

    node = OutlineNode(id=NODE, user_id=TEST_USER, project_id=PROJECT,
                       kind="chapter", rank="a0", title="C", status="empty", version=1)
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=node)
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=_motif())
    swap = AsyncMock(return_value=_swap_result())
    async with _patched(OutlineRepo=outline, MotifRepo=repo):
        with patch.object(srv, "get_pool", return_value=_FakePool()), \
                patch("app.db.repositories.motif_application.MotifApplicationRepo", MagicMock()), \
                patch("app.engine.motif_select.apply_motif_swap", swap):
            res = await srv.composition_motif_bind(
                _Ctx(), srv._MotifBindArgs(
                    project_id=str(PROJECT), node_id=str(NODE), motif_id=str(uuid.uuid4()),
                    role_bindings={"protagonist": "ent-1"},
                ),
            )
    assert res["success"] is True
    assert res["new_scene_ids"] == ["s-new-1", "s-new-2"]
    assert res["undo_token"]["new_scene_ids"] == ["s-new-1", "s-new-2"]
    # the A-tier reversible contract: the undo_hint names the verified inverse tool.
    assert res["_meta"]["undo_hint"]["tool"] == "composition_motif_unbind"
    # the engine ran with new_motif set (a bind, not a clear) + the agent's role_bindings.
    swap.assert_awaited_once()
    _, kwargs = swap.call_args
    assert kwargs["new_motif"] is not None
    assert kwargs["binding"].role_bindings == {"protagonist": "ent-1"}
    repo.get_visible.assert_awaited_once()


async def test_bind_idor_foreign_motif_still_rejected():
    """The degrade does NOT relax the IDOR guard: a motif the caller can't see is
    rejected (uniform not-accessible) BEFORE the pending response."""
    import app.mcp.server as srv
    from app.db.models import OutlineNode
    from loreweave_mcp import NotAccessibleError

    node = OutlineNode(id=NODE, user_id=TEST_USER, project_id=PROJECT,
                       kind="chapter", rank="a0", title="C", status="empty", version=1)
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=node)
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=None)  # foreign/missing motif
    async with _patched(OutlineRepo=outline, MotifRepo=repo):
        with pytest.raises(NotAccessibleError):
            await srv.composition_motif_bind(
                _Ctx(), srv._MotifBindArgs(
                    project_id=str(PROJECT), node_id=str(NODE), motif_id=str(uuid.uuid4()),
                ),
            )


async def test_unbind_clears_chapter_when_no_token():
    """D-MOTIF-MCP-BIND-WIRING (cleared): unbind with no undo_token CLEARS the chapter's
    motif (apply_motif_swap with new_motif=None) — the HTTP twin's motif_id=null mode."""
    import app.mcp.server as srv
    from app.db.models import OutlineNode

    node = OutlineNode(id=NODE, user_id=TEST_USER, project_id=PROJECT,
                       kind="chapter", rank="a0", title="C", status="empty", version=1)
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=node)
    swap = AsyncMock(return_value=_swap_result(new_scene_ids=[], new_motif_id=None))
    async with _patched(OutlineRepo=outline):
        with patch.object(srv, "get_pool", return_value=_FakePool()), \
                patch("app.db.repositories.motif_application.MotifApplicationRepo", MagicMock()), \
                patch("app.engine.motif_select.apply_motif_swap", swap):
            res = await srv.composition_motif_unbind(
                _Ctx(), project_id=str(PROJECT), node_id=str(NODE),
            )
    assert res["success"] is True and res["cleared"] is True
    swap.assert_awaited_once()
    _, kwargs = swap.call_args
    assert kwargs["new_motif"] is None  # a CLEAR, not a bind


async def test_unbind_with_token_does_exact_inverse():
    """unbind WITH an undo_token runs undo_motif_swap (the exact inverse of a prior bind —
    restores the pre-bind scenes + prose)."""
    import app.mcp.server as srv
    from app.db.models import OutlineNode

    node = OutlineNode(id=NODE, user_id=TEST_USER, project_id=PROJECT,
                       kind="chapter", rank="a0", title="C", status="empty", version=1)
    outline = AsyncMock()
    outline.get_node = AsyncMock(return_value=node)
    undo = AsyncMock(return_value={"chapter_node_id": str(NODE),
                                   "restored_scene_ids": ["s-old"], "removed_scene_ids": ["s-new"]})
    token = {"chapter_node_id": str(NODE), "archived_scene_ids": ["s-old"],
             "new_scene_ids": ["s-new"]}
    async with _patched(OutlineRepo=outline):
        with patch.object(srv, "get_pool", return_value=_FakePool()), \
                patch("app.db.repositories.motif_application.MotifApplicationRepo", MagicMock()), \
                patch("app.engine.motif_select.undo_motif_swap", undo):
            res = await srv.composition_motif_unbind(
                _Ctx(), project_id=str(PROJECT), node_id=str(NODE), undo_token=token,
            )
    assert res["success"] is True and res["undone"] is True
    assert res["restored_scene_ids"] == ["s-old"]
    undo.assert_awaited_once()


async def test_adopt_propose_mints_token_no_clone():
    """H-6: adopt propose returns a confirm_token + tenancy preview; NO clone at
    propose (the effect is the only clone path)."""
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    motif = _motif(owner_user_id=OTHER_USER, visibility="public")
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=motif)
    repo.clone = AsyncMock()
    async with _patched(MotifRepo=repo):
        res = await srv.composition_motif_adopt(
            _Ctx(), srv._MotifAdoptArgs(motif_id=str(motif.id)),
        )
    assert res["descriptor"] == "composition.motif_adopt"
    assert res["preview"]["will_clone"] is True
    repo.clone.assert_not_awaited()
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.user_id == TEST_USER


async def test_mine_propose_mints_token_with_estimate():
    """MCP-R4: mine propose returns a token + a $ estimate; NO enqueue at propose."""
    import app.mcp.server as srv
    from loreweave_mcp import verify_confirm_token
    from app.config import settings

    async with _patched(grant_level=2):
        res = await srv.composition_motif_mine(
            _Ctx(), srv._MotifMineArgs(scope="book", book_id=str(BOOK)),
        )
    assert res["descriptor"] == "composition.motif_mine"
    assert res["estimate"]["estimated_usd"] > 0
    claims = verify_confirm_token(settings.confirm_token_signing_secret, res["confirm_token"])
    assert claims.payload["scope"] == "book"


async def test_mine_book_requires_book_id():
    import app.mcp.server as srv

    async with _patched(grant_level=2):
        res = await srv.composition_motif_mine(_Ctx(), srv._MotifMineArgs(scope="book"))
    assert res["success"] is False


async def test_get_mine_job_foreign_project_uniform():
    """S1: a job under a different project → H13 (the cloned cross-Work guard)."""
    import app.mcp.server as srv
    from loreweave_mcp import NotAccessibleError
    from app.db.models import GenerationJob

    job = GenerationJob(id=uuid.uuid4(), user_id=TEST_USER, project_id=OTHER_PROJECT,
                        operation="mine_motifs", status="pending")
    jobs = AsyncMock()
    jobs.get = AsyncMock(return_value=job)
    async with _patched(grant_level=1, GenerationJobsRepo=jobs):
        with pytest.raises(NotAccessibleError):
            await srv.composition_get_mine_job(
                _Ctx(), project_id=str(PROJECT), job_id=str(job.id),
            )


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3 — confirm-route (FastAPI TestClient) — adopt/mine + the W-replay ledger
# ══════════════════════════════════════════════════════════════════════════════

from fastapi.testclient import TestClient  # noqa: E402
from loreweave_mcp import mint_confirm_token  # noqa: E402
from app.config import settings as _settings  # noqa: E402

IMPORT_SOURCE = uuid.uuid4()


def _adopt_token(user=TEST_USER, motif_id=None, *, ttl=600, now=None):
    mid = motif_id or uuid.uuid4()
    return mint_confirm_token(
        _settings.confirm_token_signing_secret, user, mid, "composition.motif_adopt",
        {"motif_id": str(mid), "retag_genres": None}, ttl=ttl, now=now,
    )


def _mine_token(user=TEST_USER, *, scope="corpus", book_id=None, estimate=0.5, ttl=600, now=None):
    rid = book_id or user
    return mint_confirm_token(
        _settings.confirm_token_signing_secret, user, rid, "composition.motif_mine",
        {"scope": scope, "book_id": str(book_id) if book_id else None,
         "min_support": 2, "promote_to": "draft", "language": "en", "estimate_usd": estimate},
        ttl=ttl, now=now,
    )


def _import_token(user=TEST_USER, import_source_id=None, *, estimate=2.0, ttl=600, now=None):
    isid = import_source_id or IMPORT_SOURCE
    return mint_confirm_token(
        _settings.confirm_token_signing_secret, user, isid, "composition.arc_import",
        {"import_source_id": str(isid), "use_web": False, "arc_hint": None, "estimate_usd": estimate},
        ttl=ttl, now=now,
    )


@pytest.fixture
def client():
    """TestClient with the DB pool, grant, repos + the /mcp session manager stubbed
    (same shape as test_mcp_actions.client)."""
    @asynccontextmanager
    async def _noop_session_manager():
        yield

    _mcp_stub = MagicMock()
    _mcp_stub.session_manager.run = _noop_session_manager

    spy_pool = AsyncMock()

    with (
        patch("app.db.pool.create_pool", new_callable=AsyncMock),
        patch("app.db.pool.close_pool", new_callable=AsyncMock),
        patch("app.db.pool.get_pool", return_value=spy_pool),
        # D-W2-MCP-SESSION-ISOLATION: app.main does `from app.db.pool import create_pool`,
        # so the lifespan calls app.main.create_pool — a SEPARATE binding the app.db.pool
        # patch misses. Unpatched, the lifespan connects to the real DB host (postgres:5432)
        # → getaddrinfo fails when this file runs in a batch. Patch the app.main bindings too
        # (mirrors test_motif_sync.ctx, which never flaked because it already does this).
        patch("app.main.create_pool", new_callable=AsyncMock),
        patch("app.main.close_pool", new_callable=AsyncMock),
        patch("app.main.get_pool", return_value=spy_pool),
        patch("app.main.run_migrations", new_callable=AsyncMock),
        patch("app.main.mcp_server", _mcp_stub),
        patch("app.main.get_grant_client", MagicMock()),
    ):
        _settings.redis_url = ""
        _settings.job_reaper_sweep_secs = 0
        from app.main import app
        from app import deps

        works = AsyncMock()
        works.get = AsyncMock(side_effect=lambda u, p: _work() if u == TEST_USER else None)
        outline = AsyncMock()
        book = AsyncMock()
        grant = AsyncMock()
        from app.grant_client import GrantLevel
        grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)

        app.dependency_overrides[deps.get_works_repo] = lambda: works
        app.dependency_overrides[deps.get_outline_repo] = lambda: outline
        app.dependency_overrides[deps.get_book_client_dep] = lambda: book
        app.dependency_overrides[deps.get_grant_client_dep] = lambda: grant

        with TestClient(app, raise_server_exceptions=True) as c:
            c._pool = spy_pool
            yield c
        app.dependency_overrides.clear()


def _confirm(client, token, *, user=TEST_USER):
    return client.post(
        "/v1/composition/actions/confirm",
        params={"token": token},
        headers={"X-Internal-Token": _GOOD_TOKEN, "X-User-Id": str(user)},
    )


def test_adopt_confirm_clones(client):
    """The adopt effect clones into the caller's library (action_done + new id)."""
    clone = _motif()
    src = _motif(owner_user_id=OTHER_USER, visibility="public")
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=src)
    repo.list_for_caller = AsyncMock(return_value=[])
    repo.clone = AsyncMock(return_value=clone)
    ledger = AsyncMock()
    ledger.consume = AsyncMock(return_value=True)
    with (
        patch("app.db.repositories.motif_repo.MotifRepo", return_value=repo),
        patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
    ):
        resp = _confirm(client, _adopt_token(motif_id=src.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_done"
    assert body["motif_id"] == str(clone.id)
    repo.clone.assert_awaited_once()
    assert repo.clone.await_args.kwargs["target_owner"] == TEST_USER


def test_w_replay_blocked_by_ledger(client):
    """W-replay (the headline): confirming the SAME adopt token twice → first
    action_done, second → 409 already_consumed (the ledger consume returns False)."""
    src = _motif(owner_user_id=OTHER_USER, visibility="public")
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=src)
    repo.list_for_caller = AsyncMock(return_value=[])
    repo.clone = AsyncMock(return_value=_motif())
    ledger = AsyncMock()
    # First claim wins (True), the replay loses (False).
    ledger.consume = AsyncMock(side_effect=[True, False])
    token = _adopt_token(motif_id=src.id)
    with (
        patch("app.db.repositories.motif_repo.MotifRepo", return_value=repo),
        patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
    ):
        first = _confirm(client, token)
        second = _confirm(client, token)
    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert second.json()["detail"]["reason"] == "already_consumed"


def test_mine_confirm_enqueues_202(client):
    """MCP-R4: mine confirm enqueues a pending mine_motifs job (202 action_accepted),
    NOT in-process compute. The precheck passes; the worker compute is W8 (Wave 2)."""
    from app.db.models import GenerationJob

    job = GenerationJob(id=uuid.uuid4(), user_id=TEST_USER, project_id=uuid.uuid4(),
                        operation="mine_motifs", status="pending")
    jobs = AsyncMock()
    jobs.create = AsyncMock(return_value=(job, True))
    ledger = AsyncMock()
    ledger.consume = AsyncMock(return_value=True)
    billing = AsyncMock()
    billing.precheck = AsyncMock(return_value=True)
    enq = AsyncMock(return_value=True)
    with (
        patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
        patch("app.clients.billing_client.get_billing_client", return_value=billing),
        patch("app.db.repositories.generation_jobs.GenerationJobsRepo", return_value=jobs),
        patch("app.worker.events.enqueue_job", new=enq),
    ):
        resp = _confirm(client, _mine_token(scope="corpus"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_accepted"
    assert body["job_id"] == str(job.id)
    assert body["poll"] == "composition_get_mine_job"
    # The job is pending + carries the worker_op stamp; the precheck ran before enqueue.
    billing.precheck.assert_awaited_once()
    assert jobs.create.await_args.kwargs["operation"] == "mine_motifs"
    assert jobs.create.await_args.kwargs["input"]["worker_op"] == "mine_motifs"
    enq.assert_awaited_once()


def test_mine_precheck_denies_over_quota(client):
    """MCP-R4 / B-4: billing precheck returns False → 402 quota_exhausted; NO job
    enqueued (precheck runs before enqueue)."""
    jobs = AsyncMock()
    jobs.create = AsyncMock()
    ledger = AsyncMock()
    ledger.consume = AsyncMock(return_value=True)
    billing = AsyncMock()
    billing.precheck = AsyncMock(return_value=False)
    with (
        patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
        patch("app.clients.billing_client.get_billing_client", return_value=billing),
        patch("app.db.repositories.generation_jobs.GenerationJobsRepo", return_value=jobs),
    ):
        resp = _confirm(client, _mine_token(scope="corpus"))
    assert resp.status_code == 402
    assert resp.json()["detail"]["reason"] == "quota_exhausted"
    jobs.create.assert_not_awaited()


def test_billing_unavailable_fails_closed(client):
    """MD-8: the real BillingClient.precheck fails CLOSED on a transport error
    (returns False) → the confirm denies with quota_exhausted, no enqueue."""
    import httpx

    from app.clients.billing_client import BillingClient

    jobs = AsyncMock()
    jobs.create = AsyncMock()
    ledger = AsyncMock()
    ledger.consume = AsyncMock(return_value=True)
    real_billing = BillingClient()

    async def _boom(*a, **k):
        raise httpx.ConnectError("billing down")

    with (
        patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
        patch("app.clients.billing_client.get_billing_client", return_value=real_billing),
        patch("app.db.repositories.generation_jobs.GenerationJobsRepo", return_value=jobs),
        patch("httpx.AsyncClient.post", new=_boom),
    ):
        resp = _confirm(client, _mine_token(scope="corpus"))
    assert resp.status_code == 402
    jobs.create.assert_not_awaited()


def test_adopt_token_other_user_rejected(client):
    """A token minted for TEST_USER cannot be confirmed by OTHER (anti-impersonation,
    actions.py:135) — uniform action_error, no clone."""
    repo = AsyncMock()
    repo.clone = AsyncMock()
    with patch("app.db.repositories.motif_repo.MotifRepo", return_value=repo):
        resp = _confirm(client, _adopt_token(user=TEST_USER), user=OTHER_USER)
    assert resp.status_code == 400
    repo.clone.assert_not_awaited()


def test_import_user_scope_foreign_rejected(client):
    """S1: an import_source owned by another user → action_error at confirm (the
    user-scope re-check), no enqueue."""
    jobs = AsyncMock()
    jobs.create = AsyncMock()
    ledger = AsyncMock()
    ledger.consume = AsyncMock(return_value=True)
    # The confirm effect reads owner via get_pool().fetchval → a foreign owner.
    client._pool.fetchval = AsyncMock(return_value=OTHER_USER)
    with (
        patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
        patch("app.db.repositories.generation_jobs.GenerationJobsRepo", return_value=jobs),
    ):
        resp = _confirm(client, _import_token())
    assert resp.status_code == 400
    jobs.create.assert_not_awaited()


def test_adopt_quota_rejects(client):
    """B-4: the per-user adopt ceiling rejects past quota (402), no clone."""
    src = _motif(owner_user_id=OTHER_USER, visibility="public")
    repo = AsyncMock()
    repo.get_visible = AsyncMock(return_value=src)
    repo.list_for_caller = AsyncMock(return_value=[_motif(), _motif()])  # 2 owned
    repo.clone = AsyncMock()
    ledger = AsyncMock()
    ledger.consume = AsyncMock(return_value=True)
    _settings.motif_max_adopt = 2  # ceiling reached
    try:
        with (
            patch("app.db.repositories.motif_repo.MotifRepo", return_value=repo),
            patch("app.db.repositories.consumed_tokens.ConsumedTokenRepo", return_value=ledger),
        ):
            resp = _confirm(client, _adopt_token(motif_id=src.id))
    finally:
        _settings.motif_max_adopt = 0
    assert resp.status_code == 402
    repo.clone.assert_not_awaited()
