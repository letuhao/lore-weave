"""WS-4C Half A — post-turn canon auto-capture.

Spec: docs/specs/2026-07-10-ws4c-half-a-canon-auto-capture.md

Three things are worth pinning here, and they are exactly the three that have bitten this
repo before:
  1. the gate is CONSUMED and proven by effect — a setting that is stored but never read is
     a bug, so every off-switch gets a test that shows capture does not fire;
  2. capture fails CLOSED on every unset/degraded value (it spends the user's BYOK tokens);
  3. it is best-effort — no failure escapes into the turn, which has already finished
     streaming by the time capture runs.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.client.glossary_capture_client import CanonCaptureClient
from app.services.canon_capture import (
    CaptureContext,
    maybe_capture_canon,
    run_canon_capture,
    should_capture,
)

BOOK = "019ee969-0000-7000-8000-000000000001"
USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


def _gate(**over):
    kw = dict(
        deploy_allows=True,
        project_enables=True,
        grounding_enabled=True,
        book_id=BOOK,
        assistant_turn_count=4,
        exchange_chars=500,
        every_n_turns=4,
        min_chars=200,
    )
    kw.update(over)
    return should_capture(**kw)


# ── the gate ─────────────────────────────────────────────────────────────────

def test_fires_on_cadence_with_everything_enabled():
    d = _gate()
    assert d.fire is True and d.reason == "fire"


@pytest.mark.parametrize(
    "override,reason",
    [
        ({"deploy_allows": False}, "deploy_ceiling_off"),
        ({"project_enables": False}, "project_setting_off"),
        ({"grounding_enabled": False}, "grounding_disabled"),
        ({"book_id": None}, "no_book"),
        ({"book_id": ""}, "no_book"),
        ({"assistant_turn_count": None}, "no_turn_count"),
        ({"assistant_turn_count": 5}, "off_cadence"),
        ({"exchange_chars": 199}, "exchange_too_short"),
    ],
)
def test_every_off_switch_blocks_capture_and_names_itself(override, reason):
    """Each condition must (a) actually block the spend and (b) report WHICH one it was —
    the logged reason is the only thing telling a user why capture is silent."""
    d = _gate(**override)
    assert d.fire is False
    assert d.reason == reason


def test_deploy_ceiling_narrows_the_user_setting_it_never_widens_it():
    """effective = AND(deploy_allows, project_enables). The env flag is a ceiling: it can
    only turn capture OFF. A project with capture off must stay off no matter the ceiling."""
    assert _gate(deploy_allows=True, project_enables=False).fire is False
    assert _gate(deploy_allows=False, project_enables=True).fire is False
    assert _gate(deploy_allows=False, project_enables=False).fire is False
    assert _gate(deploy_allows=True, project_enables=True).fire is True


def test_zero_cadence_never_fires_rather_than_dividing_by_zero():
    """A misconfigured `every_n_turns=0` must be inert, not a ZeroDivisionError inside the
    post-turn block (where it would be swallowed and silently disable capture forever)."""
    d = _gate(every_n_turns=0)
    assert d.fire is False and d.reason == "off_cadence"


def test_cadence_counts_every_nth_turn():
    for turn, want in [(4, True), (8, True), (12, True), (1, False), (7, False)]:
        assert _gate(assistant_turn_count=turn).fire is want


# ── the client: degrade, never raise ─────────────────────────────────────────


def _client(handler) -> CanonCaptureClient:
    return CanonCaptureClient(
        base_url="http://glossary", internal_token="t",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_capture_posts_owner_and_text_and_returns_receipt():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Internal-Token")
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"created": [{"name": "Ilyana", "kind": "character",
                                                      "entity_id": "e1"}],
                                         "skipped": 1, "failed": 0})

    c = _client(handler)
    try:
        out = await c.capture(book_id=BOOK, owner_user_id=USER, source_text="Ilyana appears.",
                              model_ref="m1")
    finally:
        await c.aclose()

    assert out is not None and out["created"][0]["name"] == "Ilyana"
    assert seen["url"] == f"http://glossary/internal/books/{BOOK}/capture-canon"
    assert seen["token"] == "t"
    # owner_user_id must ride the request — glossary grant-checks on it. Sending the write
    # without naming a user would make the internal token itself the authorization.
    assert seen["body"]["owner_user_id"] == USER
    assert seen["body"]["model_ref"] == "m1"


@pytest.mark.asyncio
async def test_capture_omits_model_ref_when_absent():
    import json as _json
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"created": [], "skipped": 0, "failed": 0})

    c = _client(handler)
    try:
        await c.capture(book_id=BOOK, owner_user_id=USER, source_text="hi")
    finally:
        await c.aclose()
    # An explicit null would make glossary try to resolve a model named "None".
    assert "model_ref" not in seen["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 409, 500, 502, 401])
async def test_capture_returns_none_on_any_non_200(status):
    c = _client(lambda _r: httpx.Response(status, json={"code": "X"}))
    try:
        assert await c.capture(book_id=BOOK, owner_user_id=USER, source_text="x") is None
    finally:
        await c.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,expect_in_log",
    [
        ("GLOSS_NO_KINDS", "no entity kinds"),
        ("GLOSS_BOOK_INVALID_LIFECYCLE", "not in an editable state"),
        (None, "unknown"),
    ],
)
async def test_409_is_diagnosed_by_code_not_by_status(code, expect_in_log, caplog):
    """glossary returns 409 for TWO different conditions — no ontology, and a trashed book.
    Reading only the status attributes a trashed book to "no entity kinds", sending whoever
    reads the log to fix the wrong thing."""
    body = {"code": code} if code else {"message": "something else"}
    c = _client(lambda _r: httpx.Response(409, json=body))
    try:
        with caplog.at_level("INFO"):
            assert await c.capture(book_id=BOOK, owner_user_id=USER, source_text="x") is None
    finally:
        await c.aclose()
    assert expect_in_log in caplog.text


@pytest.mark.asyncio
async def test_409_with_undecodable_body_does_not_raise():
    """The diagnostic read runs inside a client whose whole contract is 'never raise'."""
    c = _client(lambda _r: httpx.Response(409, content=b"<html>nginx</html>"))
    try:
        assert await c.capture(book_id=BOOK, owner_user_id=USER, source_text="x") is None
    finally:
        await c.aclose()


# ── the kctx wire: BuiltContext → ContextBuildResponse → KnowledgeContext ────
#
# The toggle crosses two services via `model_validate(from_attributes)`. Rename the field
# on either side and it silently falls back to the default — capture goes permanently,
# silently OFF and no test reds. The live smoke calls glossary directly and never
# exercises this path, so these are the only guards it has.


def test_knowledge_context_parses_the_capture_toggle_off_the_wire():
    from app.client.knowledge_client import KnowledgeContext

    on = KnowledgeContext.model_validate(
        {"mode": "full", "context": "", "recent_message_count": 1,
         "token_count": 0, "canon_capture_enabled": True}
    )
    assert on.canon_capture_enabled is True

    off = KnowledgeContext.model_validate(
        {"mode": "full", "context": "", "recent_message_count": 1,
         "token_count": 0, "canon_capture_enabled": False}
    )
    assert off.canon_capture_enabled is False


def test_knowledge_context_fails_closed_when_the_field_is_absent():
    """An older knowledge-service, or a renamed field, must NOT be read as consent to spend."""
    from app.client.knowledge_client import KnowledgeContext

    ctx = KnowledgeContext.model_validate(
        {"mode": "full", "context": "", "recent_message_count": 1, "token_count": 0}
    )
    assert ctx.canon_capture_enabled is False


@pytest.mark.asyncio
async def test_capture_returns_none_on_transport_error():
    def boom(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("glossary is down")

    c = _client(boom)
    try:
        assert await c.capture(book_id=BOOK, owner_user_id=USER, source_text="x") is None
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_capture_returns_none_on_undecodable_or_non_dict_body():
    for body in (b"not json", b"[1,2,3]"):
        c = _client(lambda _r, b=body: httpx.Response(200, content=b,
                                                      headers={"content-type": "application/json"}))
        try:
            assert await c.capture(book_id=BOOK, owner_user_id=USER, source_text="x") is None
        finally:
            await c.aclose()


@pytest.mark.asyncio
async def test_capture_short_circuits_on_missing_inputs_without_calling_glossary():
    called = False

    def handler(_r: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    c = _client(handler)
    try:
        assert await c.capture(book_id="", owner_user_id=USER, source_text="x") is None
        assert await c.capture(book_id=BOOK, owner_user_id="", source_text="x") is None
        assert await c.capture(book_id=BOOK, owner_user_id=USER, source_text="   ") is None
    finally:
        await c.aclose()
    assert called is False


# ── the task: best-effort, never raises into the turn ────────────────────────


@pytest.mark.asyncio
async def test_run_canon_capture_swallows_client_failure():
    """It runs after RUN_FINISHED. An exception here would be an unretrieved task exception
    at best, and a crashed post-turn block at worst."""
    with patch("app.services.canon_capture.get_canon_capture_client") as gc:
        gc.return_value.capture = AsyncMock(side_effect=RuntimeError("boom"))
        await run_canon_capture(user_id=USER, book_id=BOOK,
                                user_message="u", assistant_message="a")  # must not raise


@pytest.mark.asyncio
async def test_run_canon_capture_tolerates_none_receipt():
    with patch("app.services.canon_capture.get_canon_capture_client") as gc:
        gc.return_value.capture = AsyncMock(return_value=None)
        await run_canon_capture(user_id=USER, book_id=BOOK,
                                user_message="u", assistant_message="a")


@pytest.mark.asyncio
async def test_run_canon_capture_caps_each_side_and_labels_the_speakers():
    """The extractor must be able to tell who said what (a name the USER coins and a name
    the ASSISTANT coins are both canon), and neither side may blow the prompt."""
    captured: dict = {}

    async def _cap(**kw):
        captured.update(kw)
        return {"created": [], "skipped": 0, "failed": 0}

    from app.config import settings
    cap = settings.canon_capture_max_chars_per_side
    with patch("app.services.canon_capture.get_canon_capture_client") as gc:
        gc.return_value.capture = AsyncMock(side_effect=_cap)
        await run_canon_capture(user_id=USER, book_id=BOOK,
                                user_message="Ω" * (cap + 500),
                                assistant_message="Δ" * (cap + 500))

    text = captured["source_text"]
    assert text.startswith("User:\n")
    assert "\n\nAssistant:\n" in text
    # Sentinel chars that cannot occur in the "User:"/"Assistant:" labels themselves.
    assert text.count("Ω") == cap
    assert text.count("Δ") == cap
    assert captured["owner_user_id"] == USER
    assert captured["book_id"] == BOOK


# ── the spawn: decision → task ───────────────────────────────────────────────
#
# maybe_capture_canon is the single seam stream_service's post-turn block calls, so this is
# where "the gate is wired to something" gets proven. A gate that decides correctly and then
# spawns nothing is the silent-no-op bug class; so is one that spawns unconditionally.


def _ctx(**over) -> CaptureContext:
    kw = dict(book_id=BOOK, project_enables=True, grounding_enabled=True)
    kw.update(over)
    return CaptureContext(**kw)


@pytest.mark.asyncio
async def test_maybe_capture_canon_spawns_the_task_when_the_gate_fires():
    ran = asyncio.Event()

    async def _fake(**kw):
        ran.set()
        _fake.kwargs = kw

    with patch("app.services.canon_capture.run_canon_capture", _fake):
        decision = maybe_capture_canon(
            ctx=_ctx(), user_id=USER, assistant_turn_count=4,
            user_message="u" * 300, assistant_message="a" * 300, model_ref="m1",
        )
        assert decision.fire is True
        await asyncio.wait_for(ran.wait(), timeout=1)

    assert _fake.kwargs["book_id"] == BOOK
    assert _fake.kwargs["user_id"] == USER
    assert _fake.kwargs["model_ref"] == "m1"


async def _assert_no_spawn(*, expect_reason: str, **call_kw):
    spawned = False

    async def _fake(**_kw):
        nonlocal spawned
        spawned = True

    with patch("app.services.canon_capture.run_canon_capture", _fake):
        d = maybe_capture_canon(
            user_id=USER, assistant_turn_count=4,
            user_message="u" * 300, assistant_message="a" * 300, model_ref=None, **call_kw,
        )
        assert d.fire is False and d.reason == expect_reason
        await asyncio.sleep(0)  # give any (wrongly) spawned task a chance to run
    assert spawned is False, f"{expect_reason}: gate said no but a capture task was spawned"


@pytest.mark.asyncio
async def test_maybe_capture_canon_spawns_nothing_when_the_project_opts_out():
    """The user's own opt-out must actually stop the spend, not just the log line."""
    await _assert_no_spawn(ctx=_ctx(project_enables=False), expect_reason="project_setting_off")


@pytest.mark.asyncio
async def test_maybe_capture_canon_spawns_nothing_on_a_multi_project_turn():
    """No single book ⇒ no capture target. Never guess one."""
    await _assert_no_spawn(ctx=_ctx(book_id=None), expect_reason="no_book")


@pytest.mark.asyncio
async def test_maybe_capture_canon_fails_closed_without_a_capture_context():
    """The RESUME path rebuilds no knowledge context and passes ctx=None. An unresolved
    context must never be read as 'capture into whatever book'."""
    await _assert_no_spawn(ctx=None, expect_reason="no_capture_context")


@pytest.mark.asyncio
async def test_maybe_capture_canon_honors_the_deploy_ceiling():
    """The env kill-switch must reach the spawn, not just the returned decision."""
    from app.config import settings
    with patch.object(settings, "canon_capture_enabled", False):
        await _assert_no_spawn(ctx=_ctx(), expect_reason="deploy_ceiling_off")


@pytest.mark.asyncio
async def test_maybe_capture_canon_keeps_a_strong_task_reference_until_done():
    """asyncio holds only a WEAK reference to a running task. Capture runs for up to 90s, so
    a bare create_task() could be GC'd mid-flight — silently, and only under memory pressure.
    The strong ref must exist while it runs and be released when it finishes (no leak)."""
    from app.services import canon_capture as cc

    release = asyncio.Event()

    async def _slow(**_kw):
        await release.wait()

    assert not cc._pending
    with patch("app.services.canon_capture.run_canon_capture", _slow):
        maybe_capture_canon(
            ctx=_ctx(), user_id=USER, assistant_turn_count=4,
            user_message="u" * 300, assistant_message="a" * 300, model_ref=None,
        )
        await asyncio.sleep(0)
        assert len(cc._pending) == 1, "in-flight capture task is not strongly referenced"
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    assert not cc._pending, "completed capture task was never released (leak)"
