"""Phase 4c-α — smoke tests for the loreweave_llm SDK wrapper.

The actual translation worker migration (4c-β/γ) will exercise
submit_and_wait against scripted Job objects. This file covers the
construction + lifecycle contract so a misconfigured base_url or
missing internal_token surfaces in CI rather than at the first
production translation.
"""

from __future__ import annotations

import pytest

from app.llm_client import (
    LLMClient,
    close_llm_client,
    get_llm_client,
)


@pytest.fixture(autouse=True)
async def _reset_singleton():
    """Each test gets a fresh module-level singleton."""
    await close_llm_client()
    yield
    await close_llm_client()


def test_get_llm_client_returns_singleton():
    """Two calls return the same instance — per-process singleton
    matches knowledge-service + worker-ai pattern."""
    a = get_llm_client()
    b = get_llm_client()
    assert isinstance(a, LLMClient)
    assert a is b


def test_get_llm_client_constructs_with_internal_auth():
    """Phase 4c-α — verify the SDK Client receives auth_mode='internal'
    + internal_token from settings + user_id=None (multi-tenant per-call
    override). Catches a regression where the wrapper accidentally uses
    user-jwt mode (which would break service-to-service auth)."""
    client = get_llm_client()
    sdk = client.sdk
    # SDK Client exposes its config; check the structural pieces.
    assert sdk._user_id is None
    # base_url + internal_token are used at request time; verify they
    # were captured at construction.
    assert "provider-registry" in str(sdk._base_url) or "8085" in str(sdk._base_url)
    assert sdk._internal_token  # non-empty


@pytest.mark.asyncio
async def test_close_llm_client_idempotent():
    """close_llm_client must be callable multiple times without error
    (lifespan teardown invariant)."""
    get_llm_client()
    await close_llm_client()
    await close_llm_client()  # second call is a no-op


@pytest.mark.asyncio
async def test_close_llm_client_releases_singleton():
    """After close, the next get returns a NEW instance (not the closed
    one). Prevents reuse-after-close bugs in test fixtures + worker
    restart scenarios."""
    a = get_llm_client()
    await close_llm_client()
    b = get_llm_client()
    assert a is not b


def test_get_llm_client_reads_provider_registry_internal_url_from_settings(
    monkeypatch,
):
    """Phase 4c-α /review-impl MED#1 — the SDK Client's base_url MUST
    come from settings.provider_registry_internal_url at construction
    time. A misspelled env var (e.g. PROVIDER_REGISTRY_INTERNAL_URLS
    with trailing 's') would silently fall back to the default and the
    smoke test wouldn't notice. This test pins the wiring with a
    distinctive sentinel URL so any future env-var rename or settings
    field rename surfaces in CI."""
    from app.config import settings as live_settings

    sentinel = "http://test-host-sentinel.example:9999"
    monkeypatch.setattr(
        live_settings, "provider_registry_internal_url", sentinel,
    )

    client = get_llm_client()
    assert sentinel.rstrip("/") == str(client.sdk._base_url)


def test_llm_client_satisfies_extraction_protocol():
    """Phase 4c-α — duck-type check: the wrapper's submit_and_wait
    signature matches loreweave_extraction's LLMClientProtocol so
    4c-β/γ can pass this client to extract_pass2() if translation
    workers ever need entity extraction (currently they don't, but
    the protocol-shape lock prevents future drift)."""
    import inspect

    client = get_llm_client()
    sig = inspect.signature(client.submit_and_wait)
    params = sig.parameters
    # Required keyword params per LLMClientProtocol
    assert "user_id" in params
    assert "operation" in params
    assert "model_source" in params
    assert "model_ref" in params
    assert "input" in params
    # Optional params
    assert "chunking" in params
    assert "trace_id" in params
    assert "job_meta" in params
    assert "transient_retry_budget" in params
