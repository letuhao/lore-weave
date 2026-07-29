"""`resolve_model_info` — the registry's own answer about what a `model_ref` is.

This exists because the reasoning classifier must not decide "is this a local model?" from a
client-supplied hint, and must be able to honour the per-model `capability_flags.reasoning_control`
override. Both facts live behind this one internal call, so its degradation behaviour is
load-bearing rather than cosmetic.
"""

from __future__ import annotations

import httpx
import pytest

from loreweave_internal_client import resolve_model_info, resolve_model_name

BASE = "http://registry.test"
REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"


def _client(monkeypatch, handler):
    """Patch httpx.AsyncClient so the call is exercised end-to-end without a socket."""
    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return handler(url, headers)

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


def _resp(status: int, payload: dict | None = None):
    return httpx.Response(status, json=payload if payload is not None else {},
                          request=httpx.Request("GET", BASE))


async def test_returns_kind_name_and_flags(monkeypatch):
    _client(monkeypatch, lambda url, headers: _resp(200, {
        "provider_kind": "lm_studio",
        "provider_model_name": "google/gemma-4-26b-a4b-qat",
        "capability_flags": {"reasoning_control": "effort", "vision": True},
    }))
    info = await resolve_model_info(BASE, "user_model", REF, internal_token="t")
    assert info == {
        "provider_kind": "lm_studio",
        "provider_model_name": "google/gemma-4-26b-a4b-qat",
        "capability_flags": {"reasoning_control": "effort", "vision": True},
    }


@pytest.mark.parametrize("flags", [None, "null", 3, [], "not-a-dict"])
async def test_non_object_flags_degrade_to_an_empty_mapping(monkeypatch, flags):
    """The column is nullable AND holds a bare JSON `null` on live rows. The caller must be able
    to treat this as a mapping without re-deriving that defence per language."""
    _client(monkeypatch, lambda url, headers: _resp(200, {
        "provider_kind": "lm_studio", "provider_model_name": "m", "capability_flags": flags,
    }))
    info = await resolve_model_info(BASE, "user_model", REF, internal_token="t")
    assert info is not None and info["capability_flags"] == {}


async def test_missing_flags_key_is_tolerated(monkeypatch):
    """An older registry predates the field; its absence must not lose the kind, which is the
    part the suppression decision hangs on."""
    _client(monkeypatch, lambda url, headers: _resp(200, {
        "provider_kind": "lm_studio", "provider_model_name": "m"}))
    info = await resolve_model_info(BASE, "user_model", REF, internal_token="t")
    assert info is not None
    assert info["provider_kind"] == "lm_studio" and info["capability_flags"] == {}


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_non_200_is_unverified_not_a_negative_answer(monkeypatch, status):
    """`None` means "could not ask", NOT "this model has no kind". A caller that conflates the
    two re-opens the bug this route was wired up to close."""
    _client(monkeypatch, lambda url, headers: _resp(status))
    assert await resolve_model_info(BASE, "user_model", REF, internal_token="t") is None


async def test_transport_failure_never_raises(monkeypatch):
    def boom(url, headers=None):
        raise httpx.ConnectError("registry down")
    _client(monkeypatch, boom)
    assert await resolve_model_info(BASE, "user_model", REF, internal_token="t") is None


async def test_missing_source_or_ref_short_circuits(monkeypatch):
    def must_not_call(url, headers=None):  # pragma: no cover - the assertion IS that it never runs
        raise AssertionError("should not have issued a request")
    _client(monkeypatch, must_not_call)
    assert await resolve_model_info(BASE, None, REF, internal_token="t") is None
    assert await resolve_model_info(BASE, "user_model", None, internal_token="t") is None


async def test_resolve_model_name_still_returns_just_the_name(monkeypatch):
    """The older single-purpose helper is now a projection of the richer one — its five existing
    callers must keep seeing exactly what they saw before."""
    _client(monkeypatch, lambda url, headers: _resp(200, {
        "provider_kind": "openai", "provider_model_name": "gpt-4o", "capability_flags": {}}))
    assert await resolve_model_name(BASE, "user_model", REF, internal_token="t") == "gpt-4o"
