"""S-TRANSL — tests for the translation-service MCP server facade + the Tier-W
confirm spine + the cost-estimate (HIGH#1) + re-price-at-execution (H14).

Layers (mirrors the canonical S-JOBS test):

  1. **Wire path** (loopback uvicorn, real MCP streamable-HTTP): `tools/list`
     returns the translation catalog; every tool carries valid `_meta` (tier +
     scope book); no tool leaks a scope arg; auth failures (missing/wrong internal
     token, malformed user-id) are rejected as tool errors before any DB access.

  2. **Ownership / scope** (direct handler calls with a stubbed grant resolver): a
     non-owner is rejected with the uniform not-accessible error (H13).

  3. **Tiers** (catalog `_meta`): R/A/W present where the §4 catalog says; Tier-A
     handlers emit `_meta.undo_hint`; job_control splits cancel/pause=A,
     resume/retry=W.

  4. **Cost estimate** (pure): a known scope returns a token+money projection.

  5. **H14 re-price** (pure threshold + the confirm route): re-confirm triggers when
     actual > est×1.25 and when > est+$0.50, and does NOT within tolerance; the
     Tier-W confirm-token round-trips (mint → verify → execute).

The wire-path server runs in a daemon thread with its own loop (the StreamableHTTP
session manager is once-per-instance; pytest runs function-scoped loops under
`asyncio_mode = auto`).
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

_GOOD_TOKEN = "test_internal_token"  # matches conftest INTERNAL_SERVICE_TOKEN
TEST_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
BOOK = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CHAPTER = "dddddddd-dddd-dddd-dddd-dddddddddddd"

EXPECTED_TOOLS = {
    "translation_coverage", "translation_segment_status",
    "translation_list_versions", "translation_job_status",
    "translation_set_active_version", "translation_save_edited_version",
    "translation_patch_block", "translation_update_settings",
    "translation_start_job", "translation_retranslate_dirty",
    "translation_job_control", "translation_start_extraction",
}

# Per-tool expected tier (C-TOOL §4 S-TRANSL). job_control is declared W (its
# strictest path); cancel/pause execute as A inline at call time.
EXPECTED_TIER = {
    "translation_coverage": "R", "translation_segment_status": "R",
    "translation_list_versions": "R", "translation_job_status": "R",
    "translation_set_active_version": "A", "translation_save_edited_version": "A",
    "translation_patch_block": "A", "translation_update_settings": "A",
    "translation_start_job": "W", "translation_retranslate_dirty": "W",
    "translation_job_control": "W", "translation_start_extraction": "W",
}


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


async def test_tools_list_returns_the_translation_catalog(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    assert {t.name for t in listing.tools} == EXPECTED_TOOLS


async def test_every_tool_has_description(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    for tool in listing.tools:
        assert tool.description, f"tool {tool.name!r} missing description"


async def test_every_tool_carries_tier_and_book_scope(mcp_base_url):
    """C-TOOL: each tool declares its tier (per §4) + scope=book + synonyms."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    for tool in listing.tools:
        meta = tool.meta
        assert meta is not None, f"{tool.name}: no _meta"
        assert meta.get("tier") == EXPECTED_TIER[tool.name], (
            f"{tool.name}: tier {meta.get('tier')!r} != {EXPECTED_TIER[tool.name]!r}"
        )
        assert meta.get("scope") == "book", f"{tool.name}: expected scope book"
        syns = meta.get("synonyms")
        assert isinstance(syns, list) and syns, f"{tool.name}: missing synonyms"


async def test_no_tool_leaks_a_scope_arg(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    forbidden = {"user_id", "owner_user_id", "session_id", "ctx"}
    for tool in listing.tools:
        props = set(tool.inputSchema.get("properties", {}))
        leaked = props & forbidden
        assert not leaked, f"tool {tool.name!r} leaks scope args: {leaked}"


# ── Wire path: identity / auth from headers ───────────────────────────────────


async def test_rejects_missing_internal_token(mcp_base_url):
    async with _mcp_client(mcp_base_url, headers={}) as session:
        result = await session.call_tool("translation_coverage", {"book_id": BOOK})
    assert result.isError is True
    assert "x-internal-token" in _error_text(result)


async def test_rejects_wrong_internal_token(mcp_base_url):
    headers = {"X-Internal-Token": "nope", "X-User-Id": TEST_USER, "X-Session-Id": "s"}
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("translation_coverage", {"book_id": BOOK})
    assert result.isError is True
    assert "invalid internal token" in _error_text(result)


async def test_rejects_bad_user_id(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN, "X-User-Id": "nope", "X-Session-Id": "s"}
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("translation_coverage", {"book_id": BOOK})
    assert result.isError is True
    assert "x-user-id" in _error_text(result)


# ── Ownership / scope (direct handler calls with a stubbed grant resolver) ─────


@asynccontextmanager
async def _patched(*, grant_level, pool=None, est=None):
    """Patch the server's grant resolver + pool + (optionally) the estimate so a
    handler runs without a live book-service / Postgres. `build_tool_context` is
    bypassed → the envelope ctx is returned directly (the wire tests cover real
    header parsing)."""
    from loreweave_mcp import ToolContext
    import app.mcp.server as srv

    async def _resolver(book_id, user_id):
        return int(grant_level)

    def _ctx_from(ctx):
        return ctx  # ctx is already a ToolContext in these tests

    cms = [
        patch.object(srv, "_grant_resolver", _resolver),
        patch.object(srv, "build_tool_context", side_effect=lambda c, t: c),
    ]
    if pool is not None:
        cms.append(patch.object(srv, "get_pool", return_value=pool))
    if est is not None:
        cms.append(patch.object(srv, "estimate_job_cost", AsyncMock(return_value=est)))
    # _require_view / _require_edit captured the OLD resolver at import; rebuild them.
    from loreweave_mcp import require_book_owner
    from app.grant_client import GrantLevel
    cms.append(patch.object(srv, "_require_view",
                            require_book_owner(_resolver, int(GrantLevel.VIEW))))
    cms.append(patch.object(srv, "_require_edit",
                            require_book_owner(_resolver, int(GrantLevel.EDIT))))

    from contextlib import ExitStack
    with ExitStack() as stack:
        for cm in cms:
            stack.enter_context(cm)
        yield srv, ToolContext(user_id=UUID(TEST_USER), session_id="s")


async def test_non_owner_is_rejected():
    """A caller with NO grant on the book gets the uniform not-accessible error."""
    from app.grant_client import GrantLevel
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=GrantLevel.NONE, pool=AsyncMock()) as (srv, ctx):
        with pytest.raises(NotAccessibleError):
            await srv.translation_coverage(ctx, book_id=BOOK)


# ── Cost estimate (pure) ───────────────────────────────────────────────────────


async def test_estimate_returns_a_cost_for_a_known_scope():
    """A known chapter scope (segments summing to N source tokens) prices to a real
    money figure via the (stubbed) provider-registry oracle."""
    from app.mcp import estimate as e

    pool = AsyncMock()
    # effective settings → model + language
    pool.fetchrow = AsyncMock(side_effect=[
        {"book_id": UUID(BOOK), "owner_user_id": UUID(TEST_USER),
         "target_language": "en", "model_source": "user_model",
         "model_ref": UUID("11111111-1111-1111-1111-111111111111"),
         "updated_at": None},  # book_translation_settings row
        # _sum_chapter_tokens row
        {"toks": 1000, "segs": 4},
    ])

    async def _price(**kw):
        # Stand in for provider-registry: 1000 in + 1000 out → $0.20
        assert kw["input_tokens"] == 1000
        assert kw["output_tokens"] == 1000  # ratio 1.0
        return 0.20

    with patch.object(e, "_price_tokens", _price):
        est = await e.estimate_job_cost(
            pool, owner_user_id=TEST_USER, book_id=UUID(BOOK),
            chapter_ids=[UUID(CHAPTER)], scope=e.SCOPE_CHAPTERS,
        )
    assert est.priced is True
    assert est.cost_usd == 0.20
    assert est.input_tokens == 1000
    assert est.output_tokens == 1000
    assert est.segment_count == 4
    assert est.model_source == "user_model"


async def test_estimate_unpriced_when_no_model():
    """No model configured → token projection still returned, money is None (a
    caveat, not a crash)."""
    from app.mcp import estimate as e

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(side_effect=[
        None,  # no book settings
        None,  # no user prefs → hard defaults (model_ref None)
        {"toks": 500, "segs": 2},
    ])
    est = await e.estimate_job_cost(
        pool, owner_user_id=TEST_USER, book_id=UUID(BOOK),
        chapter_ids=[UUID(CHAPTER)], scope=e.SCOPE_CHAPTERS,
    )
    assert est.priced is False
    assert est.cost_usd is None
    assert est.input_tokens == 500


# ── H14 re-price threshold (pure) ──────────────────────────────────────────────


def test_reprice_triggers_on_multiplier():
    """actual > est×1.25 (and within the abs floor) → re-confirm."""
    from app.mcp.estimate import reprice_exceeds_threshold
    # est=10 → mult ceiling 12.50, abs ceiling 10.50. actual 13 > both → trip.
    assert reprice_exceeds_threshold(10.0, 13.0) is True
    # actual 12.0 ≤ 12.50 mult but > 10.50 abs → STILL trips on the abs floor.
    assert reprice_exceeds_threshold(10.0, 12.0) is True


def test_reprice_triggers_on_absolute_only():
    """A small est where the +$0.50 abs floor is the binding one."""
    from app.mcp.estimate import reprice_exceeds_threshold
    # est=0.10 → mult ceiling 0.125, abs ceiling 0.60. actual 0.65 > 0.60 → trip
    # (also > mult). Construct a case where ONLY the abs floor would be relevant:
    # est=1.00 → mult 1.25, abs 1.50. actual 1.40 ≤ mult? 1.40>1.25 yes → trips on mult.
    # To isolate abs: est large so mult ceiling huge but abs small relative. est=0.01:
    # mult 0.0125, abs 0.51. actual 0.40 > 0.0125 (mult) → already trips. The OR makes
    # either sufficient; assert the documented small-overspend case trips.
    assert reprice_exceeds_threshold(0.10, 0.65) is True


def test_reprice_within_tolerance_does_not_trigger():
    """actual ≤ est×1.25 AND ≤ est+$0.50 → run without re-confirm."""
    from app.mcp.estimate import reprice_exceeds_threshold
    # est=10 → mult 12.50, abs 10.50. actual 10.40 ≤ both → no trip.
    assert reprice_exceeds_threshold(10.0, 10.40) is False
    # exactly at est → no trip.
    assert reprice_exceeds_threshold(10.0, 10.0) is False


def test_reprice_no_actual_does_not_trigger():
    """Couldn't re-price (unpriced model) → never block a confirmed job."""
    from app.mcp.estimate import reprice_exceeds_threshold
    assert reprice_exceeds_threshold(10.0, None) is False
    assert reprice_exceeds_threshold(None, None) is False


def test_reprice_no_baseline_but_real_cost_triggers():
    """No estimate was shown but now there's a real cost → re-confirm."""
    from app.mcp.estimate import reprice_exceeds_threshold
    assert reprice_exceeds_threshold(None, 5.0) is True


def test_reprice_zero_baseline_boundary():
    """Fix 5: lock the est=0.0 (a real, free/zero baseline) boundary — DISTINCT from
    est=None (no baseline). With a non-positive baseline the degenerate relative
    ceiling (0.0×1.25=0.0) is skipped and ONLY the absolute floor (0.0+$0.50=$0.50)
    governs: a small drift over a $0.00 cost is tolerable, a drift past +$0.50
    re-confirms. Guards that 0.0 is NOT the None 'no-baseline' branch (which trips on
    ANY positive cost)."""
    from app.mcp.estimate import reprice_exceeds_threshold
    assert reprice_exceeds_threshold(0.0, 0.40) is False   # ≤ $0.50 abs floor
    assert reprice_exceeds_threshold(0.0, 0.60) is True    # > $0.50 abs floor


# ── Tier split: job_control cancel=A (runs now), resume=W (confirm) ────────────


async def test_job_control_cancel_is_tier_A_and_runs_now():
    """cancel executes immediately (Tier-A): the cancel core is invoked, no token."""
    from app.grant_client import GrantLevel
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "owner_user_id": UUID(TEST_USER), "book_id": UUID(BOOK),
        "status": "running", "chapter_ids": [UUID(CHAPTER)],
    })
    async with _patched(grant_level=GrantLevel.OWNER, pool=pool) as (srv, ctx):
        with patch.object(srv, "estimate_job_cost", AsyncMock()) as est_mock:
            with patch("app.routers.jobs._cancel_job_core",
                       new=AsyncMock()) as cancel_mock:
                res = await srv.translation_job_control(
                    ctx, job_id="99999999-9999-9999-9999-999999999999",
                    action="cancel",
                )
    cancel_mock.assert_awaited_once()
    est_mock.assert_not_called()  # Tier-A never prices
    assert res["status"] == "cancelled"
    assert res["success"] is True
    # cancel has no reverse → undo not available.
    assert res["_meta"]["undo_hint"] == {"available": False}


async def test_job_control_resume_is_tier_W_and_mints_a_token():
    """resume RE-SPENDS → returns a confirm token + estimate, runs NOTHING yet."""
    from app.grant_client import GrantLevel

    class _Est:
        def as_dict(self):
            return {"cost_usd": 0.5, "input_tokens": 100, "priced": True}

    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "owner_user_id": UUID(TEST_USER), "book_id": UUID(BOOK),
        "status": "paused", "chapter_ids": [UUID(CHAPTER)],
    })
    async with _patched(grant_level=GrantLevel.OWNER, pool=pool) as (srv, ctx):
        with patch.object(srv, "estimate_job_cost",
                          AsyncMock(return_value=_Est())):
            with patch("app.routers.jobs._resume_job_core",
                       new=AsyncMock()) as resume_mock:
                res = await srv.translation_job_control(
                    ctx, job_id="99999999-9999-9999-9999-999999999999",
                    action="resume",
                )
    resume_mock.assert_not_called()  # nothing runs until confirm
    assert res["needs_confirm"] is True
    assert res["confirm_token"]
    assert res["descriptor"] == "translation.job_resume"
    assert res["domain"] == "translation"


# ── Tier-A undo_hint present (set_active_version) ──────────────────────────────


async def test_set_active_version_emits_undo_hint():
    from app.grant_client import GrantLevel
    pool = AsyncMock()
    # version lookup, then prev-active fetchval
    pool.fetchrow = AsyncMock(return_value={
        "owner_user_id": UUID(TEST_USER), "book_id": UUID(BOOK),
        "target_language": "en", "status": "completed", "unresolved_high_count": 0,
    })
    pool.fetchval = AsyncMock(return_value=UUID("22222222-2222-2222-2222-222222222222"))
    pool.execute = AsyncMock()
    async with _patched(grant_level=GrantLevel.OWNER, pool=pool) as (srv, ctx):
        res = await srv.translation_set_active_version(
            ctx, book_id=BOOK, chapter_id=CHAPTER,
            version_id="33333333-3333-3333-3333-333333333333",
        )
    assert res["success"] is True
    undo = res["_meta"]["undo_hint"]
    assert undo["tool"] == "translation_set_active_version"
    # undo re-activates the PREVIOUSLY active version.
    assert undo["args"]["version_id"] == "22222222-2222-2222-2222-222222222222"


# ── Tier-W confirm-token round-trip (mint → verify → execute) ─────────────────


def _mint(descriptor, payload, *, user=TEST_USER, ttl=600, now=None):
    """Mint a confirm token with the DEDICATED confirm-signing secret (key-split
    from the envelope token — the confirm spine verifies with this same secret)."""
    from app.config import settings
    from loreweave_mcp import mint_confirm_token
    kw = {} if now is None else {"now": now}
    return mint_confirm_token(
        settings.confirm_token_signing_secret, UUID(user), UUID(BOOK),
        descriptor, payload, ttl, **kw,
    )


def _bound_est():
    from app.mcp.estimate import CostEstimate
    return CostEstimate(
        scope="chapters", target_language="en", chapter_count=1, segment_count=4,
        input_tokens=1000, output_tokens=1000, cost_usd=0.20, priced=True,
        model_source="user_model", model_ref="11111111-1111-1111-1111-111111111111",
    )


@asynccontextmanager
async def _confirm_patches(*, grant_level=None, chapters_bound=True):
    """Patch the confirm route's re-authorize + chapter-binding seams (Fix 1) so a
    confirm runs without a live book-service / grant-client. `grant_level` drives
    the re-authorize (default OWNER → pass); `chapters_bound` drives the chapter→
    book binding (default True → bound)."""
    from app.grant_client import GrantLevel
    from app.routers import actions

    lvl = GrantLevel.OWNER if grant_level is None else grant_level

    class _GC:
        async def resolve_grant(self, book_id, user_id):
            return lvl

    async def _owns(book_id, chapter_id):
        return chapters_bound

    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(patch.object(actions, "get_grant_client", lambda: _GC()))
        stack.enter_context(patch.object(actions, "book_owns_chapter", _owns))
        # _start_job_todo prices the to-do set; default: no skips (full set runs).
        stack.enter_context(patch.object(
            actions, "_start_job_todo",
            AsyncMock(side_effect=lambda db, cids, *a, **k: list(cids)),
        ))
        yield


async def test_confirm_token_round_trip_within_tolerance_starts_job():
    """A start_job confirm whose re-price is within tolerance actually starts the
    job (the confirm route is the only start path)."""
    from app.routers import actions
    from app.mcp.estimate import CostEstimate

    payload = {
        "action": "start_job", "title": "Translate 1 chapter(s)",
        "book_id": BOOK, "chapter_ids": [CHAPTER], "target_language": "en",
        "force_retranslate": False, "estimate": _bound_est().as_dict(),
    }
    token = _mint(actions.DESC_START_JOB, payload)

    fresh = CostEstimate(  # within tolerance: 0.22 ≤ 0.20×1.25 and ≤ 0.70
        scope="chapters", target_language="en", chapter_count=1, segment_count=4,
        input_tokens=1100, output_tokens=1100, cost_usd=0.22, priced=True,
        model_source="user_model", model_ref="11111111-1111-1111-1111-111111111111",
    )

    class _Job:
        job_id = UUID("44444444-4444-4444-4444-444444444444")
        status = "pending"

    pool = AsyncMock()
    async with _confirm_patches():
        with patch.object(actions, "estimate_job_cost", AsyncMock(return_value=fresh)):
            with patch.object(actions, "_resolve_and_create_job",
                              AsyncMock(return_value=_Job())) as create_mock:
                res = await actions.confirm_action(
                    actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
                )
    create_mock.assert_awaited_once()
    assert res["status"] == "action_done"
    assert res["job_id"] == "44444444-4444-4444-4444-444444444444"


async def test_confirm_reprices_against_bound_model_not_current_settings():
    """Fix 2 (model-binding): the confirm re-price must price the MODEL BOUND in the
    token (echoed into the estimate at propose), NOT whatever effective settings now
    resolve to. Assert the bound model_source/model_ref are passed through to the
    re-price."""
    from app.routers import actions
    from app.mcp.estimate import CostEstimate

    bound = _bound_est()  # model_ref 11111111-…
    payload = {
        "action": "start_job", "title": "t", "book_id": BOOK,
        "chapter_ids": [CHAPTER], "target_language": "en",
        "force_retranslate": False, "estimate": bound.as_dict(),
    }
    token = _mint(actions.DESC_START_JOB, payload)

    fresh = CostEstimate(
        scope="chapters", target_language="en", chapter_count=1, segment_count=4,
        input_tokens=1000, output_tokens=1000, cost_usd=0.20, priced=True,
        model_source="user_model", model_ref="11111111-1111-1111-1111-111111111111",
    )

    class _Job:
        job_id = UUID("44444444-4444-4444-4444-444444444444")
        status = "pending"

    est_mock = AsyncMock(return_value=fresh)
    pool = AsyncMock()
    async with _confirm_patches():
        with patch.object(actions, "estimate_job_cost", est_mock):
            with patch.object(actions, "_resolve_and_create_job",
                              AsyncMock(return_value=_Job())):
                await actions.confirm_action(
                    actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
                )
    # The re-price priced the model the user APPROVED (bound), not re-resolved.
    _, kwargs = est_mock.call_args
    assert kwargs["bound_model_source"] == "user_model"
    assert kwargs["bound_model_ref"] == "11111111-1111-1111-1111-111111111111"


async def test_confirm_reprice_over_threshold_refuses_and_does_not_start():
    """When the fresh cost drifts past est×1.25/+$0.50, confirm REFUSES (409
    reprice_required) and starts NOTHING."""
    from fastapi import HTTPException
    from app.routers import actions
    from app.mcp.estimate import CostEstimate

    payload = {
        "action": "start_job", "title": "t", "book_id": BOOK,
        "chapter_ids": [CHAPTER], "target_language": "en",
        "force_retranslate": False, "estimate": _bound_est().as_dict(),
    }
    token = _mint(actions.DESC_START_JOB, payload)
    fresh = CostEstimate(  # 0.90 > 0.20×1.25 (0.25) AND > 0.70 → trip
        scope="chapters", target_language="en", chapter_count=1, segment_count=4,
        input_tokens=4500, output_tokens=4500, cost_usd=0.90, priced=True,
        model_source="user_model", model_ref="11111111-1111-1111-1111-111111111111",
    )
    pool = AsyncMock()
    async with _confirm_patches():
        with patch.object(actions, "estimate_job_cost", AsyncMock(return_value=fresh)):
            with patch.object(actions, "_resolve_and_create_job",
                              AsyncMock()) as create_mock:
                with pytest.raises(HTTPException) as exc:
                    await actions.confirm_action(
                        actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
                    )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "TRANSL_REPRICE_REQUIRED"
    assert exc.value.detail["actual_cost_usd"] == 0.90
    create_mock.assert_not_called()  # nothing started


async def test_confirm_refuses_when_grant_revoked_in_ttl():
    """Fix 1 (re-authorize): a validly-signed token whose user NO LONGER holds the
    grant on the bound book is REFUSED at confirm (403) and starts NOTHING — a grant
    revoked inside the confirm TTL must not still spend."""
    from fastapi import HTTPException
    from app.grant_client import GrantLevel
    from app.routers import actions

    payload = {
        "action": "start_job", "title": "t", "book_id": BOOK,
        "chapter_ids": [CHAPTER], "target_language": "en",
        "force_retranslate": False, "estimate": _bound_est().as_dict(),
    }
    token = _mint(actions.DESC_START_JOB, payload)  # validly signed
    pool = AsyncMock()
    # grant_level=NONE → the live re-resolve says "no grant" even though the token
    # was minted when the user HAD it.
    async with _confirm_patches(grant_level=GrantLevel.NONE):
        with patch.object(actions, "estimate_job_cost", AsyncMock()) as est_mock:
            with patch.object(actions, "_resolve_and_create_job",
                              AsyncMock()) as create_mock:
                with pytest.raises(HTTPException) as exc:
                    await actions.confirm_action(
                        actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
                    )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "TRANSL_FORBIDDEN"
    est_mock.assert_not_called()      # refused BEFORE re-price
    create_mock.assert_not_called()   # nothing started


async def test_confirm_refuses_when_chapter_not_under_bound_book():
    """Fix 1 (chapter binding): a confirm payload whose chapter does NOT belong to
    the token-bound book is REFUSED (403) — a payload cannot retarget another book's
    chapters under a grant on the bound book."""
    from fastapi import HTTPException
    from app.routers import actions

    payload = {
        "action": "start_job", "title": "t", "book_id": BOOK,
        "chapter_ids": [CHAPTER], "target_language": "en",
        "force_retranslate": False, "estimate": _bound_est().as_dict(),
    }
    token = _mint(actions.DESC_START_JOB, payload)
    pool = AsyncMock()
    async with _confirm_patches(chapters_bound=False):  # chapter not under the book
        with patch.object(actions, "estimate_job_cost", AsyncMock()) as est_mock:
            with patch.object(actions, "_resolve_and_create_job",
                              AsyncMock()) as create_mock:
                with pytest.raises(HTTPException) as exc:
                    await actions.confirm_action(
                        actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
                    )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "TRANSL_FORBIDDEN"
    est_mock.assert_not_called()
    create_mock.assert_not_called()


async def test_confirm_rejects_expired_token():
    from fastapi import HTTPException
    from app.routers import actions

    # Mint already-expired (issued so that now+ttl is in the past).
    token = _mint(actions.DESC_START_JOB, {"estimate": {}}, ttl=1, now=1.0)
    pool = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await actions.confirm_action(
            actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
        )
    assert exc.value.status_code == 410
    assert exc.value.detail["code"] == "TRANSL_CONFIRM_EXPIRED"


async def test_confirm_rejects_forged_token():
    from fastapi import HTTPException
    from app.routers import actions

    pool = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await actions.confirm_action(
            actions.ConfirmRequest(confirm_token="garbage.token"), db=pool,
            caller_user_id=TEST_USER,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "TRANSL_CONFIRM_INVALID"


async def test_confirm_rejects_token_bound_to_a_different_user():
    """Seam fix (live-pass): the confirm route is now JWT-gated (reached by the FE
    confirm card carrying the user's JWT). The token's `u` claim must equal the
    JWT caller — a DIFFERENT signed-in user must not redeem someone else's token
    even with the string. Folded into the uniform 403 (anti-oracle)."""
    from fastapi import HTTPException
    from app.routers import actions

    payload = {
        "action": "start_job", "title": "t", "book_id": BOOK,
        "chapter_ids": [CHAPTER], "target_language": "en",
        "force_retranslate": False, "estimate": _bound_est().as_dict(),
    }
    token = _mint(actions.DESC_START_JOB, payload)  # bound to TEST_USER
    other_user = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    pool = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await actions.confirm_action(
            actions.ConfirmRequest(confirm_token=token), db=pool,
            caller_user_id=other_user,
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "TRANSL_FORBIDDEN"


async def test_confirm_rejects_token_signed_with_envelope_secret():
    """Key-split (Fix 4): a token signed with the ENVELOPE internal_service_token
    (not the dedicated confirm secret) must NOT verify — proves the two secrets are
    genuinely separate."""
    from fastapi import HTTPException
    from app.config import settings
    from loreweave_mcp import mint_confirm_token
    from app.routers import actions

    assert settings.confirm_token_signing_secret != settings.internal_service_token
    token = mint_confirm_token(
        settings.internal_service_token, UUID(TEST_USER), UUID(BOOK),
        actions.DESC_START_JOB, {"estimate": {}}, 600,
    )
    pool = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await actions.confirm_action(
            actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "TRANSL_CONFIRM_INVALID"


# ── preview reads the bound estimate (no re-price) ─────────────────────────────


async def test_preview_returns_bound_estimate():
    from app.routers import actions

    payload = {"title": "Translate 1 chapter(s)",
               "estimate": {"cost_usd": 0.20, "input_tokens": 1000}}
    token = _mint(actions.DESC_START_JOB, payload)
    res = await actions.preview_action(token=token, caller_user_id=TEST_USER)
    assert res.descriptor == actions.DESC_START_JOB
    assert res.title == "Translate 1 chapter(s)"
    assert res.estimate["cost_usd"] == 0.20


# ── M3: glossary chapter-extraction (translation_start_extraction) ─────────────


async def test_start_extraction_mints_a_confirm_token():
    """The extraction tool is priced Tier-W: it returns a confirm token + a token
    ESTIMATE and writes NOTHING (the confirm route is the only start path)."""
    from app.grant_client import GrantLevel

    profile = {"kinds": [{"code": "character", "attributes": [{"code": "name"}]}]}
    async with _patched(grant_level=GrantLevel.EDIT) as (srv, ctx):
        with patch.object(srv, "fetch_extraction_profile",
                          AsyncMock(return_value=profile)):
            res = await srv.translation_start_extraction(
                ctx, book_id=BOOK, chapter_ids=[CHAPTER],
                extraction_profile={"character": {"name": "fill"}},
            )
    assert res["needs_confirm"] is True
    assert res["confirm_token"]
    assert res["descriptor"] == "translation.start_extraction"
    assert res["domain"] == "translation"
    # The estimate is a token projection (no money) — present and structured.
    assert "estimated_total_tokens" in res["estimate"]


async def test_start_extraction_non_owner_rejected():
    """No EDIT grant on the book → the uniform not-accessible error, no token."""
    from app.grant_client import GrantLevel
    from loreweave_mcp import NotAccessibleError

    async with _patched(grant_level=GrantLevel.NONE) as (srv, ctx):
        with patch.object(srv, "fetch_extraction_profile", AsyncMock(return_value={})):
            with pytest.raises(NotAccessibleError):
                await srv.translation_start_extraction(
                    ctx, book_id=BOOK, chapter_ids=[CHAPTER],
                )


async def test_confirm_start_extraction_creates_job():
    """The DESC_START_EXTRACTION confirm branch re-authorizes + asserts the chapter
    binding, then runs the shared extraction core and returns the job handle."""
    from app.routers import actions

    payload = {
        "action": "start_extraction", "title": "Extract glossary from 1 chapter(s)",
        "book_id": BOOK, "chapter_ids": [CHAPTER],
        "extraction_profile": {"character": {"name": "fill"}},
        "model_source": "platform_model", "model_ref": None,
        "max_entities_per_kind": 30, "thinking_enabled": False,
        "estimate": {"estimated_total_tokens": 1234},
    }
    token = _mint(actions.DESC_START_EXTRACTION, payload)
    pool = AsyncMock()
    async with _confirm_patches():
        with patch.object(
            actions, "_create_extraction_job_core",
            AsyncMock(return_value={"job_id": "55555555-5555-5555-5555-555555555555",
                                    "status": "pending"}),
        ) as core_mock:
            res = await actions.confirm_action(
                actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
            )
    core_mock.assert_awaited_once()
    assert res["status"] == "action_done"
    assert res["job_id"] == "55555555-5555-5555-5555-555555555555"
    assert res["job_status"] == "pending"


async def test_confirm_start_extraction_refuses_chapter_not_under_bound_book():
    """A confirm payload cannot retarget a chapter under a DIFFERENT book than the
    re-authorized one → uniform 403, the extraction core never runs."""
    from fastapi import HTTPException
    from app.routers import actions

    payload = {
        "action": "start_extraction", "title": "t", "book_id": BOOK,
        "chapter_ids": [CHAPTER], "extraction_profile": {},
        "model_source": "platform_model", "model_ref": None,
        "estimate": {},
    }
    token = _mint(actions.DESC_START_EXTRACTION, payload)
    pool = AsyncMock()
    async with _confirm_patches(chapters_bound=False):
        with patch.object(actions, "_create_extraction_job_core",
                          AsyncMock()) as core_mock:
            with pytest.raises(HTTPException) as exc:
                await actions.confirm_action(
                    actions.ConfirmRequest(confirm_token=token), db=pool, caller_user_id=TEST_USER,
                )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "TRANSL_FORBIDDEN"
    core_mock.assert_not_called()
