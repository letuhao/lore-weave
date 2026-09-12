"""T12 — an author must be able to SEE that their bible outgrew the cap.

A 2026-09-06 run wrote 8 steering rules and the model generated against 3 for the whole run; the 5
dropped included the locked arc outline and the corruption mechanics. Nothing in the UI said so.
Issue #223 raised the cap and explicitly deferred the disclosure. OUT-5: never silently truncate,
report the cap.

These cover the read endpoint that makes it visible — including the two things that make it safe
rather than merely useful: it authorizes the caller (the underlying steering fetch does NOT), and
it refuses to present an ambiguous empty result as a confident zero.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.client.grant_client import GrantLevel
from app.routers import steering_budget as mod


class _Grants:
    def __init__(self, level):
        self._level = level

    async def resolve_access(self, _book, _user):
        return self._level, "active"


class _Steering:
    def __init__(self, entries):
        self._entries = entries

    async def get_steering(self, _book_id):
        return self._entries


def _rule(name: str, words: int = 5) -> dict:
    return {"name": name, "body": "word " * words, "inclusion_mode": "always"}


from uuid import uuid4

BOOK, USER = uuid4(), uuid4()


@pytest.mark.asyncio
async def test_a_fitting_bible_reports_no_drop(monkeypatch):
    monkeypatch.setattr(mod, "get_grant_client", lambda: _Grants(GrantLevel.OWNER))
    monkeypatch.setattr(mod, "get_book_steering_client", lambda: _Steering([_rule("tone")]))

    out = await mod.read_steering_budget(BOOK, None, USER)
    assert out.total_entries == 1
    assert out.over_budget is False
    assert out.would_drop == 0
    assert out.total_tokens > 0
    assert out.cap_tokens > 0


@pytest.mark.asyncio
async def test_an_oversized_bible_names_what_would_be_dropped(monkeypatch):
    """The count alone is not actionable: "5 dropped" does not tell an author that the locked arc
    outline was one of them."""
    big = [_rule(f"rule{i}", words=4000) for i in range(6)]
    monkeypatch.setattr(mod, "get_grant_client", lambda: _Grants(GrantLevel.OWNER))
    monkeypatch.setattr(mod, "get_book_steering_client", lambda: _Steering(big))

    out = await mod.read_steering_budget(BOOK, None, USER)
    assert out.over_budget is True
    assert out.would_drop > 0
    assert len(out.would_drop_names) == out.would_drop
    assert all(n.startswith("rule") for n in out.would_drop_names)
    # The total must reflect what the AUTHOR wrote, not what survived the cap — otherwise the
    # number they are asked to reduce would already be the reduced one.
    assert out.total_tokens > out.cap_tokens


@pytest.mark.asyncio
async def test_a_caller_without_VIEW_gets_404_not_a_budget(monkeypatch):
    """The underlying steering fetch uses book-service's INTERNAL route and does not check the
    caller at all, so returning its result unguarded would leak another author's rule NAMES and
    rule COUNT to any authenticated user."""
    monkeypatch.setattr(mod, "get_grant_client", lambda: _Grants(GrantLevel.NONE))
    called = {"fetched": False}

    class _NeverCalled:
        async def get_steering(self, _b):
            called["fetched"] = True
            return [_rule("secret-rule")]

    monkeypatch.setattr(mod, "get_book_steering_client", lambda: _NeverCalled())

    with pytest.raises(HTTPException) as exc:
        await mod.read_steering_budget(BOOK, None, USER)
    assert exc.value.status_code == 404, "a stranger's book must not be distinguishable"
    assert called["fetched"] is False, "steering was fetched BEFORE the grant was checked"


@pytest.mark.asyncio
async def test_an_empty_result_is_reported_as_zero_but_not_as_over_budget(monkeypatch):
    """`get_steering` returns [] on ANY failure and never raises, so "no rules" and "book-service
    is down" arrive identically. The endpoint must not invent a confident budget from that."""
    monkeypatch.setattr(mod, "get_grant_client", lambda: _Grants(GrantLevel.OWNER))
    monkeypatch.setattr(mod, "get_book_steering_client", lambda: _Steering([]))

    out = await mod.read_steering_budget(BOOK, None, USER)
    assert out.total_entries == 0
    assert out.over_budget is False
    assert out.would_drop_names == []
    # …and the cap is still reported, so the panel can show the ceiling even with nothing in it.
    assert out.cap_tokens > 0


@pytest.mark.asyncio
async def test_the_cap_reported_scales_with_the_model_window(monkeypatch):
    """An author comparing their total against a hardcoded 8000 would draw the wrong conclusion on
    a large-window model, so the cap that WILL apply is reported rather than assumed."""
    monkeypatch.setattr(mod, "get_grant_client", lambda: _Grants(GrantLevel.OWNER))
    monkeypatch.setattr(mod, "get_book_steering_client", lambda: _Steering([_rule("tone")]))

    small = await mod.read_steering_budget(BOOK, None, USER)
    large = await mod.read_steering_budget(BOOK, 1_000_000, USER)
    assert large.cap_tokens >= small.cap_tokens
