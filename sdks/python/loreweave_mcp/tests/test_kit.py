"""Tests for the shared Python MCP kit (C-KIT-PY / S-KIT-PY DoD).

Covers:
  - build_tool_context header extraction (+ bad/missing token rejected, SEC-1)
  - all three guards: book / user / project — happy + denied + fail-closed (H15)
  - uniform_not_accessible (H13)
  - confirm mint->verify round-trip (+ expired + tampered rejected, INV-9)
  - the _meta validator rejection (C-TOOL)
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from loreweave_mcp import (
    ConfirmTokenExpired,
    ConfirmTokenInvalid,
    ForbidExtra,
    MetaValidationError,
    NotAccessibleError,
    ToolContext,
    build_tool_context,
    is_owner_only,
    make_stateless_fastmcp,
    mint_confirm_token,
    require_book_owner,
    require_meta,
    require_project,
    require_user_scope,
    uniform_not_accessible,
    validate_tool_meta,
    verify_confirm_token,
)

SECRET = "test-internal-token-not-a-real-secret"  # noqa: S105 — test fixture only
SIGNING_SECRET = "test-signing-secret-fixture"  # noqa: S105 — test fixture only


# ── fakes ─────────────────────────────────────────────────────────────


class _FakeHeaders:
    """Case-insensitive header bag mimicking starlette's Headers.get()."""

    def __init__(self, mapping: dict[str, str]):
        self._m = {k.lower(): v for k, v in mapping.items()}

    def get(self, key: str, default=None):
        return self._m.get(key.lower(), default)


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = _FakeHeaders(headers)


class _FakeRequestContext:
    def __init__(self, headers: dict[str, str]):
        self.request = _FakeRequest(headers)


class _FakeMCPContext:
    def __init__(self, headers: dict[str, str]):
        self.request_context = _FakeRequestContext(headers)


def _ctx(**overrides) -> _FakeMCPContext:
    headers = {
        "x-internal-token": SECRET,
        "x-user-id": str(uuid.uuid4()),
        "x-session-id": "sess-abc",
    }
    headers.update(overrides)
    return _FakeMCPContext(headers)


# ── make_stateless_fastmcp ─────────────────────────────────────────────


def test_make_stateless_fastmcp_wiring():
    srv = make_stateless_fastmcp("test-kit")
    assert srv.settings.stateless_http is True
    assert srv.settings.streamable_http_path == "/"


# ── build_tool_context (SEC-1) ─────────────────────────────────────────


def test_build_tool_context_happy():
    uid = uuid.uuid4()
    pid = uuid.uuid4()
    ctx = _ctx(
        **{
            "x-user-id": str(uid),
            "x-project-id": str(pid),
            "x-session-id": "sess-1",
            "x-trace-id": "trace-1",
        }
    )
    tc = build_tool_context(ctx, SECRET)
    assert isinstance(tc, ToolContext)
    assert tc.user_id == uid
    assert tc.project_id == pid
    assert tc.session_id == "sess-1"
    assert tc.trace_id == "trace-1"


def test_build_tool_context_optional_headers_absent():
    tc = build_tool_context(_ctx(), SECRET)
    assert tc.project_id is None
    assert tc.trace_id is None
    assert tc.mcp_key_id is None  # first-party call carries no public-key id
    assert tc.spend_cap_usd is None  # nor a per-key cap


def test_build_tool_context_lifts_spend_cap(monkeypatch):
    # A public-edge call may carry X-Mcp-Spend-Cap-Usd → lands on the ctx (H-K) AND
    # (universal hook) sets the loreweave_llm contextvar so a job this tool submits
    # carries it into job_meta. We spy on the soft-imported setter.
    import loreweave_mcp.context as ctxmod

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        ctxmod, "_set_llm_attribution",
        lambda key, cap: captured.update(key=key, cap=cap),
    )
    tc = build_tool_context(_ctx(**{"x-mcp-key-id": "key-xyz", "x-mcp-spend-cap-usd": "5.5"}), SECRET)
    assert tc.spend_cap_usd == 5.5
    assert captured == {"key": "key-xyz", "cap": 5.5}


def test_build_tool_context_malformed_cap_fails_open_to_none(monkeypatch):
    import loreweave_mcp.context as ctxmod

    captured: dict[str, object] = {}
    monkeypatch.setattr(ctxmod, "_set_llm_attribution", lambda key, cap: captured.update(key=key, cap=cap))
    # Garbage / negative cap → None (no per-key cap); a first-party call clears it.
    tc = build_tool_context(_ctx(**{"x-mcp-spend-cap-usd": "not-a-number"}), SECRET)
    assert tc.spend_cap_usd is None
    assert captured == {"key": None, "cap": None}  # cleared, never leaks a prior call's cap


def test_apply_public_key_attribution_headers_forwards_parsed(monkeypatch):
    # The non-tool-call carrier-lift (P4/Wave-C slice A) used by a REST confirm route.
    # It parses the cap header and forwards (key, cap) to the loreweave_llm setter.
    import loreweave_mcp.context as ctxmod
    from loreweave_mcp import apply_public_key_attribution_headers

    captured: dict[str, object] = {}
    monkeypatch.setattr(ctxmod, "_set_llm_attribution", lambda key, cap: captured.update(key=key, cap=cap))

    apply_public_key_attribution_headers("key-1", "5.0")
    assert captured == {"key": "key-1", "cap": 5.0}

    # An empty key + malformed cap → both None (treated as absent / fail-open).
    apply_public_key_attribution_headers("", "abc")
    assert captured == {"key": None, "cap": None}

    # The finally-clear path: (None, None) clears the contextvar.
    apply_public_key_attribution_headers(None, None)
    assert captured == {"key": None, "cap": None}


def test_apply_public_key_attribution_headers_noop_without_llm(monkeypatch):
    # A service without loreweave_llm installed (setter is None) → no-op, no crash.
    import loreweave_mcp.context as ctxmod
    from loreweave_mcp import apply_public_key_attribution_headers

    monkeypatch.setattr(ctxmod, "_set_llm_attribution", None)
    apply_public_key_attribution_headers("key-1", "5.0")  # must not raise


def test_build_tool_context_lifts_mcp_key_id():
    # A public-edge call carries X-Mcp-Key-Id → it lands on the ctx (H-C carrier)
    # and flips owner-only ON (OD-8).
    tc = build_tool_context(_ctx(**{"x-mcp-key-id": "key-xyz"}), SECRET)
    assert tc.mcp_key_id == "key-xyz"
    assert is_owner_only(tc) is True


def test_is_owner_only_false_for_first_party():
    tc = build_tool_context(_ctx(), SECRET)
    assert is_owner_only(tc) is False


def test_is_owner_only_duck_typed_on_foreign_ctx():
    # Works on any object exposing mcp_key_id (e.g. knowledge-service's richer
    # ToolContext, which composes its own dataclass).
    class _Foreign:
        mcp_key_id = "k1"

    class _Bare:
        pass

    assert is_owner_only(_Foreign()) is True
    assert is_owner_only(_Bare()) is False


def test_build_tool_context_missing_token_rejected():
    ctx = _FakeMCPContext({"x-user-id": str(uuid.uuid4()), "x-session-id": "s"})
    with pytest.raises(ValueError, match="missing required context header"):
        build_tool_context(ctx, SECRET)


def test_build_tool_context_bad_token_rejected():
    with pytest.raises(ValueError, match="invalid internal token"):
        build_tool_context(_ctx(**{"x-internal-token": "wrong"}), SECRET)


def test_build_tool_context_empty_configured_secret_rejected():
    # An empty server-side secret must never accept ANY caller token (fail closed):
    # even a caller that sends a non-empty token is rejected.
    with pytest.raises(ValueError, match="invalid internal token"):
        build_tool_context(_ctx(**{"x-internal-token": "anything"}), "")


def test_build_tool_context_missing_user_id_rejected():
    ctx = _FakeMCPContext({"x-internal-token": SECRET, "x-session-id": "s"})
    with pytest.raises(ValueError, match="x-user-id"):
        build_tool_context(ctx, SECRET)


def test_build_tool_context_bad_user_uuid_rejected():
    with pytest.raises(ValueError, match="not a valid UUID"):
        build_tool_context(_ctx(**{"x-user-id": "not-a-uuid"}), SECRET)


def test_build_tool_context_bad_project_uuid_rejected():
    with pytest.raises(ValueError, match="x-project-id is not a valid UUID"):
        build_tool_context(_ctx(**{"x-project-id": "nope"}), SECRET)


# ── ForbidExtra (INV-2) ────────────────────────────────────────────────


def test_forbid_extra_rejects_unknown_field():
    class Args(ForbidExtra):
        name: str

    Args(name="ok")  # happy
    with pytest.raises(Exception):  # pydantic ValidationError
        Args(name="ok", user_id="injected")


# ── uniform_not_accessible (H13) ───────────────────────────────────────


def test_uniform_not_accessible_is_tool_error_and_uniform():
    e1 = uniform_not_accessible()
    e2 = uniform_not_accessible(KeyError("missing row"))
    assert isinstance(e1, ToolError)
    assert isinstance(e1, NotAccessibleError)
    # Same message regardless of cause → no enumeration oracle.
    assert str(e1) == str(e2)
    assert e2.__cause__ is not None


# ── book-owner guard (H15) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_book_owner_guard_happy():
    async def resolver(book_id, user_id):
        return 4  # owner

    guard = require_book_owner(resolver, level=3)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    assert await guard(tc, uuid.uuid4()) == 4


@pytest.mark.asyncio
async def test_book_owner_guard_denied_low_level():
    async def resolver(book_id, user_id):
        return 1  # view only

    guard = require_book_owner(resolver, level=3)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    with pytest.raises(NotAccessibleError):
        await guard(tc, uuid.uuid4())


@pytest.mark.asyncio
async def test_book_owner_guard_fail_closed_on_resolver_error():
    async def resolver(book_id, user_id):
        raise RuntimeError("grant authority down")

    guard = require_book_owner(resolver, level=1)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    with pytest.raises(NotAccessibleError):
        await guard(tc, uuid.uuid4())


@pytest.mark.asyncio
async def test_book_owner_guard_caches_positive_only():
    calls = {"n": 0}

    async def resolver(book_id, user_id):
        calls["n"] += 1
        return 4

    guard = require_book_owner(resolver, level=1, cache_ttl_s=1000.0)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    book = uuid.uuid4()
    await guard(tc, book)
    await guard(tc, book)
    assert calls["n"] == 1  # second call served from positive cache


@pytest.mark.asyncio
async def test_book_owner_guard_does_not_cache_denials():
    state = {"level": 0}

    async def resolver(book_id, user_id):
        return state["level"]

    guard = require_book_owner(resolver, level=1, cache_ttl_s=1000.0)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    book = uuid.uuid4()
    with pytest.raises(NotAccessibleError):
        await guard(tc, book)
    # Grant just landed — must NOT be stale-denied (denials are never cached).
    state["level"] = 4
    assert await guard(tc, book) == 4


# ── book-owner guard OD-8 (owned-only for public MCP keys) ──────────────


@pytest.mark.asyncio
async def test_book_owner_guard_od8_public_key_denied_shared_book():
    """A public key (mcp_key_id set) holding only a SHARE (manage<owner) is denied
    even on a tool that nominally needs view — OD-8 escalates the bar to OWNER."""
    async def resolver(book_id, user_id):
        return 3  # manage — a collaboration grant, NOT owner

    guard = require_book_owner(resolver, level=1)  # view-tier tool
    book = uuid.uuid4()
    public = ToolContext(user_id=uuid.uuid4(), session_id="s", mcp_key_id="key-abc")
    with pytest.raises(NotAccessibleError):
        await guard(public, book)
    # The SAME grant is fine for a first-party call (no mcp_key_id) → grant path.
    first_party = ToolContext(user_id=uuid.uuid4(), session_id="s")
    assert await guard(first_party, book) == 3


@pytest.mark.asyncio
async def test_book_owner_guard_od8_public_key_owner_passes():
    async def resolver(book_id, user_id):
        return 4  # owner

    guard = require_book_owner(resolver, level=1)
    public = ToolContext(user_id=uuid.uuid4(), session_id="s", mcp_key_id="key-abc")
    assert await guard(public, uuid.uuid4()) == 4  # owner clears OD-8


# ── user-scope guard (H15) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_scope_guard_happy():
    uid = uuid.uuid4()

    async def owner_of(ctx, resource_id):
        return uid

    guard = require_user_scope(owner_of)
    tc = ToolContext(user_id=uid, session_id="s")
    assert await guard(tc, uuid.uuid4()) == uid


@pytest.mark.asyncio
async def test_user_scope_guard_denied_other_owner():
    async def owner_of(ctx, resource_id):
        return uuid.uuid4()  # someone else

    guard = require_user_scope(owner_of)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    with pytest.raises(NotAccessibleError):
        await guard(tc, uuid.uuid4())


@pytest.mark.asyncio
async def test_user_scope_guard_fail_closed_on_missing():
    async def owner_of(ctx, resource_id):
        raise LookupError("no such model row")

    guard = require_user_scope(owner_of)
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    with pytest.raises(NotAccessibleError):
        await guard(tc, uuid.uuid4())


@pytest.mark.asyncio
async def test_user_scope_guard_denied_zero_owner():
    # A row whose owner resolves to the zero UUID (a NULL/zero owner column) with
    # NO error MUST be denied — a zero owner can never grant access, even to a
    # zero-UUID caller. Mirrors the Go kit's explicit `owner == uuid.Nil` reject
    # ("nil owner with nil error denied — zero owns nothing").
    zero = uuid.UUID(int=0)

    async def owner_of(ctx, resource_id):
        return zero  # row exists but has a zero/NULL owner

    guard = require_user_scope(owner_of)

    # A normal caller is denied (falls out of owner != caller too, but the explicit
    # nil reject guarantees it independent of the match check).
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s")
    with pytest.raises(NotAccessibleError):
        await guard(tc, uuid.uuid4())

    # Even a zero-UUID caller must NOT match a zero owner — this is the case the
    # explicit nil reject closes (a bare owner != caller check would allow it).
    tc_zero = ToolContext(user_id=zero, session_id="s")
    with pytest.raises(NotAccessibleError):
        await guard(tc_zero, uuid.uuid4())


@pytest.mark.asyncio
async def test_user_scope_guard_accepts_sync_owner_of():
    uid = uuid.uuid4()

    def owner_of(ctx, resource_id):  # sync resolver
        return uid

    guard = require_user_scope(owner_of)
    tc = ToolContext(user_id=uid, session_id="s")
    assert await guard(tc, uuid.uuid4()) == uid


# ── project-scope guard (H15) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_project_guard_requires_envelope():
    guard = require_project()
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s", project_id=None)
    with pytest.raises(NotAccessibleError):
        await guard(tc)


@pytest.mark.asyncio
async def test_project_guard_happy_no_owner_check():
    pid = uuid.uuid4()
    guard = require_project()
    tc = ToolContext(user_id=uuid.uuid4(), session_id="s", project_id=pid)
    assert await guard(tc) == pid


@pytest.mark.asyncio
async def test_project_guard_membership_happy_and_denied():
    uid = uuid.uuid4()
    pid = uuid.uuid4()

    async def owner_ok(ctx, project_id):
        return uid

    async def owner_other(ctx, project_id):
        return uuid.uuid4()

    tc = ToolContext(user_id=uid, session_id="s", project_id=pid)
    assert await require_project(owner_ok)(tc) == pid
    with pytest.raises(NotAccessibleError):
        await require_project(owner_other)(tc)


@pytest.mark.asyncio
async def test_project_guard_fail_closed_on_error():
    async def owner_of(ctx, project_id):
        raise RuntimeError("membership lookup down")

    tc = ToolContext(user_id=uuid.uuid4(), session_id="s", project_id=uuid.uuid4())
    with pytest.raises(NotAccessibleError):
        await require_project(owner_of)(tc)


# ── confirm-token spine (INV-9) ────────────────────────────────────────


def test_confirm_token_round_trip():
    uid = uuid.uuid4()
    rid = uuid.uuid4()
    payload = {"action": "publish_batch", "chapters": [1, 2, 3]}
    tok = mint_confirm_token(SIGNING_SECRET, uid, rid, "book.publish_batch", payload)
    claims = verify_confirm_token(SIGNING_SECRET, tok)
    assert claims.user_id == uid
    assert claims.resource_id == rid
    assert claims.descriptor == "book.publish_batch"
    assert claims.payload == payload


def test_confirm_token_expired_rejected():
    uid, rid = uuid.uuid4(), uuid.uuid4()
    # Minted in the past with a tiny TTL.
    tok = mint_confirm_token(
        SIGNING_SECRET, uid, rid, "book.delete", {}, ttl=10, now=1_000.0
    )
    with pytest.raises(ConfirmTokenExpired):
        verify_confirm_token(SIGNING_SECRET, tok, now=2_000.0)


def test_confirm_token_tampered_payload_rejected():
    uid, rid = uuid.uuid4(), uuid.uuid4()
    tok = mint_confirm_token(SIGNING_SECRET, uid, rid, "book.delete", {"n": 1})
    payload_b64, sig_b64 = tok.split(".")
    # Flip a char in the payload — signature no longer matches.
    forged = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    with pytest.raises(ConfirmTokenInvalid):
        verify_confirm_token(SIGNING_SECRET, forged + "." + sig_b64)


def test_confirm_token_descriptor_tamper_evident():
    """Confused-deputy guard: the descriptor is inside the HMAC, so re-encoding the
    payload segment with a DIFFERENT descriptor — still valid JSON, still
    base64url — must break the signature. A token minted for "book.publish" can
    never be silently re-pointed at "book.delete"."""
    uid, rid = uuid.uuid4(), uuid.uuid4()
    tok = mint_confirm_token(SIGNING_SECRET, uid, rid, "book.publish", {"x": 1})
    payload_b64, sig_b64 = tok.split(".")

    pad = "=" * (-len(payload_b64) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
    assert claims["d"] == "book.publish"  # precondition
    claims["d"] = "book.delete"  # tamper the intent only
    forged_payload = (
        base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    # Reattach the ORIGINAL signature → well-formed token, only the descriptor changed.
    with pytest.raises(ConfirmTokenInvalid):
        verify_confirm_token(SIGNING_SECRET, forged_payload + "." + sig_b64)


def test_confirm_token_descriptor_bound_exactly():
    """A validly-minted descriptor round-trips EXACTLY, so a confirm route
    dispatching on claims.descriptor cannot be fooled into the wrong action."""
    uid, rid = uuid.uuid4(), uuid.uuid4()
    tok = mint_confirm_token(SIGNING_SECRET, uid, rid, "book.delete", None)
    claims = verify_confirm_token(SIGNING_SECRET, tok)
    assert claims.descriptor == "book.delete"


def test_confirm_token_wrong_secret_rejected():
    uid, rid = uuid.uuid4(), uuid.uuid4()
    tok = mint_confirm_token(SIGNING_SECRET, uid, rid, "book.delete", {})
    with pytest.raises(ConfirmTokenInvalid):
        verify_confirm_token("different-secret", tok)


def test_confirm_token_malformed_rejected():
    with pytest.raises(ConfirmTokenInvalid):
        verify_confirm_token(SIGNING_SECRET, "no-dot-here")


def test_confirm_token_mint_requires_secret_and_descriptor():
    uid, rid = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ConfirmTokenInvalid):
        mint_confirm_token("", uid, rid, "book.delete", {})
    with pytest.raises(ConfirmTokenInvalid):
        mint_confirm_token(SIGNING_SECRET, uid, rid, "   ", {})


def test_confirm_token_wire_format_matches_go_scheme():
    """Wire format = base64url(payload_json).base64url(hmac) with NO padding
    (Go base64.RawURLEncoding) — the cross-language interop contract."""
    uid, rid = uuid.uuid4(), uuid.uuid4()
    tok = mint_confirm_token(SIGNING_SECRET, uid, rid, "book.delete", {})
    assert tok.count(".") == 1
    payload_b64, sig_b64 = tok.split(".")
    # No '=' padding (RawURLEncoding); URL-safe alphabet only.
    assert "=" not in payload_b64 and "=" not in sig_b64
    assert "+" not in tok and "/" not in tok


# ── _meta validator (C-TOOL) ───────────────────────────────────────────


def test_require_meta_happy():
    meta = require_meta("W", "book", undo_hint={"tool": "book_delete"}, synonyms=["rm"])
    assert meta["tier"] == "W" and meta["scope"] == "book"


def test_validate_tool_meta_rejects_missing_meta():
    with pytest.raises(MetaValidationError):
        validate_tool_meta(None, tool_name="book_x")


def test_validate_tool_meta_rejects_missing_tier():
    with pytest.raises(MetaValidationError, match="tier"):
        validate_tool_meta({"scope": "book"}, tool_name="book_x")


def test_validate_tool_meta_rejects_missing_scope():
    with pytest.raises(MetaValidationError, match="scope"):
        validate_tool_meta({"tier": "R"}, tool_name="book_x")


def test_validate_tool_meta_rejects_bad_enum():
    with pytest.raises(MetaValidationError):
        validate_tool_meta({"tier": "Z", "scope": "book"})
    with pytest.raises(MetaValidationError):
        validate_tool_meta({"tier": "R", "scope": "galaxy"})


def test_validate_tool_meta_rejects_bad_undo_hint_and_synonyms():
    with pytest.raises(MetaValidationError):
        validate_tool_meta({"tier": "A", "scope": "book", "undo_hint": {"no_tool": 1}})
    with pytest.raises(MetaValidationError):
        validate_tool_meta({"tier": "R", "scope": "none", "synonyms": "notalist"})
