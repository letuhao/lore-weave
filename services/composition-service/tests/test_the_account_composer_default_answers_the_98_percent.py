"""DQ-T89 (b) — a book with no model of its own can still be written.

OWNER RULING 2026-09-02: "(b) ADD A `composer` CAPABILITY to user_default_models and fall back
to that." Not (c), my recommendation — the owner took the more explicit option.

🔴 THE DEFECT, MEASURED 2026-09-01. composition_generate's model_ref became optional (DQ-T35)
and resolves from the Work. But 0 of 664 Works carry the `model_roles` map and 13 carry the
legacy scalar, so the Work tier answers ~2% of books. On the other 98% the tool REFUSED, the
model retried, the loop breaker tripped after two identical failures, and the turn wrote prose
through `book_chapter_save_draft` instead. The most expensive tool on the platform was never
reached at all.

🔴 WHY NOT JUST FALL BACK TO 'chat', WHICH WAS FREE. Because choosing a model for conversation
is not consent to spend it on a long prose generation. The account tier is consulted ONLY for
the role the author explicitly set for prose.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.engine.model_roles import role_ref  # noqa: E402

WORK_MODEL = "01a04107-5b4a-789c-8b22-30f17c8abb00"
ACCOUNT_MODEL = "01a04107-5b4a-789c-8b22-30f17c8abb99"


class _Work:
    def __init__(self, settings):
        self.settings = settings


async def _resolve(work_settings, account_answer):
    """The cascade exactly as `composition_generate` runs it: Work roles, then account composer.

    Written as a faithful re-implementation rather than by importing the MCP handler, which
    needs a pool, a context and a live registry. `test_the_SHIPPED_cascade_matches_this` below
    pins this against the real source so the two cannot drift — without that, this file would
    be testing itself.
    """
    src, ref = (None, None)
    for role in ("composer", "prose", "chat"):
        src, ref = role_ref(work_settings, role)
        if ref and src:
            break
    if not (ref and src):
        acct = account_answer
        if acct:
            src, ref = "user_model", acct
    return src, ref


@pytest.mark.asyncio
async def test_a_book_with_NO_model_now_resolves_from_the_account():
    """THE FALSIFIER, on the 98%: an empty Work plus an account composer must resolve."""
    src, ref = await _resolve({}, ACCOUNT_MODEL)
    assert (src, ref) == ("user_model", ACCOUNT_MODEL), (
        "a Work with no model_roles still cannot resolve — this is the 98% of books the "
        "ruling exists to answer")


@pytest.mark.asyncio
async def test_the_BOOK_tier_still_WINS_over_the_account():
    """🔴 THE CASCADE ORDER IS THE RULING'S, and reversing it would be silent: both resolve, so
    nothing errors — the author's per-book voice choice would just stop being honoured."""
    settings = {"model_roles": {"composer": {"model_ref": WORK_MODEL,
                                             "model_source": "user_model"}}}
    src, ref = await _resolve(settings, ACCOUNT_MODEL)
    assert ref == WORK_MODEL, (
        "the ACCOUNT default overrode the WORK's own composer — a per-book choice is more "
        "specific than an account-wide one and must win")


@pytest.mark.asyncio
async def test_it_STILL_REFUSES_when_nothing_is_configured():
    """The refusal is the safety property, not a leftover. Every generation SPENDS, so with
    nothing set the runtime must not pick a model on the author's behalf."""
    src, ref = await _resolve({}, None)
    assert not ref and not src


@pytest.mark.asyncio
async def test_an_UNREACHABLE_registry_refuses_rather_than_guessing():
    """`resolve_default_model` returns None for a transport error AND for 'not set' alike, so
    the caller cannot tell them apart — and must therefore refuse. A fallback that substituted
    some other model on a network blip would spend the author's money on a choice they never
    made, which is the whole reason the ruling named a capability instead of borrowing one."""
    src, ref = await _resolve({}, None)      # None is what an unreachable registry returns
    assert not ref


@pytest.mark.asyncio
async def test_a_HALF_WRITTEN_work_setting_falls_through_to_the_account():
    """A role with a ref but no source is a half-written setting; `model_roles_from_settings`
    already drops it. It must not block the account tier."""
    settings = {"model_roles": {"composer": {}}}
    src, ref = await _resolve(settings, ACCOUNT_MODEL)
    assert (src, ref) == ("user_model", ACCOUNT_MODEL)


def test_the_SHIPPED_cascade_matches_this():
    """🔴 WITHOUT THIS, EVERY TEST ABOVE COULD PASS AGAINST A RE-IMPLEMENTATION THAT THE SHIPPED
    CODE NO LONGER RESEMBLES. Assert the real handler still does Work-roles-then-account-composer
    and still refuses when neither answers."""
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "mcp" / "server.py").read_text(encoding="utf-8")
    i = src.index('for _role in ("composer", "prose", "chat")')
    window = src[i:i + 1400]
    assert 'resolve_default_model(str(ctx.user_id), "composer")' in window, (
        "the account leg is gone, or no longer asks for the composer role")
    assert '"user_model", _acct' in window, "the account leg no longer names its model_source"
    assert '"success": False' in window, "the refusal that guards the author's money is gone"
    # The account leg must come AFTER the Work loop, or the book tier stops winning.
    assert window.index("for _role in") < window.index("resolve_default_model")


def test_the_capability_is_registered_in_provider_registry():
    """A capability the registry rejects is a fallback that always returns None — the build
    would look correct and answer nothing. This is the cross-service half of the same change."""
    go = (pathlib.Path(__file__).resolve().parents[2] / "provider-registry-service"
          / "internal" / "api" / "default_models_handler.go").read_text(encoding="utf-8")

    # 🔴 LINES, NOT SUBSTRINGS, AND THE FIRST VERSION OF THIS ASSERTION IS WHY. It read
    # `'"composer": true' in go`, and the red-proof commented the entry out as
    # `// INJECTED-DRIFT "composer": true,` — which still CONTAINS that substring, so the guard
    # stayed green while the capability was disabled. A guard that a comment marker defeats is
    # not a guard, and this loop has now been caught by a source-substring check twice in one
    # day. Requiring an uncommented line is the smallest fix that actually discriminates.
    def _live_line(prefix: str) -> bool:
        return any(ln.strip().startswith(prefix) and not ln.strip().startswith("//")
                   for ln in go.splitlines())

    assert _live_line('"composer": true'), (
        "composer is not a LIVE entry in defaultModelCapabilities (commented out, or absent) — "
        "the registry would reject every assignment and the account tier would always be empty")
    assert _live_line('capability == "planner"') or 'capability == "composer"' in go, (
        "composer is not validated against the 'chat' flag, so no chat model is assignable "
        "to it and every assignment would be rejected")
