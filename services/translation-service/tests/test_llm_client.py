"""Phase 4c-α — smoke tests for the loreweave_llm SDK wrapper.

The actual translation worker migration (4c-β/γ) will exercise
submit_and_wait against scripted Job objects. This file covers the
construction + lifecycle contract so a misconfigured base_url or
missing internal_token surfaces in CI rather than at the first
production translation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.llm_client import (
    LLMClient,
    close_llm_client,
    get_llm_client,
    set_campaign_id,
)


class _FakeSubmit:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


def _fake_sdk():
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_FakeSubmit("job-1"))
    sdk.wait_terminal = AsyncMock(return_value=object())
    return sdk


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


@pytest.mark.asyncio
async def test_submit_and_wait_stamps_campaign_id_from_contextvar():
    """S4a — the central chokepoint: when a campaign is bound on this task, EVERY
    provider job's job_meta carries campaign_id (so no call site can drop
    attribution), and the caller's own job_meta keys are preserved."""
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    set_campaign_id("camp-123")
    try:
        await client.submit_and_wait(
            user_id="u", operation="translation",
            model_source="user_model", model_ref="m",
            input={"messages": []}, job_meta={"chunk_idx": 0},
        )
    finally:
        set_campaign_id(None)
    req = sdk.submit_job.call_args.args[0]
    assert req.job_meta["campaign_id"] == "camp-123"
    assert req.job_meta["chunk_idx"] == 0  # caller key preserved


@pytest.mark.asyncio
async def test_submit_and_wait_no_campaign_id_when_unset():
    """S4a — non-campaign work is unchanged: no campaign_id key is added when the
    contextvar is clear (default None)."""
    set_campaign_id(None)
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    await client.submit_and_wait(
        user_id="u", operation="translation",
        model_source="user_model", model_ref="m",
        input={}, job_meta={"endpoint": "x"},
    )
    req = sdk.submit_job.call_args.args[0]
    assert "campaign_id" not in (req.job_meta or {})


def test_submit_job_only_invoked_via_wrapper():
    """S4a drift guard (review-impl LOW-2): the campaign_id attribution merge lives
    in LLMClient.submit_and_wait AND LLMClient.submit_job (Phase 2b's fire-and-forget
    sibling). Both stamp campaign_id, so the safe path is the WRAPPER. The danger is
    a site calling the RAW SDK submit_job directly (bypassing attribution). Lock the
    invariant: the raw SDK `submit_job` (`_sdk.submit_job(` / `.sdk.submit_job(`) is
    invoked ONLY in llm_client.py. Calling the wrapper's `llm_client.submit_job(...)`
    from a decoupled worker is fine — it attributes."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if p.name != "llm_client.py"
        and ("_sdk.submit_job(" in p.read_text(encoding="utf-8")
             or ".sdk.submit_job(" in p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"raw SDK submit_job called outside the llm_client wrapper (bypasses "
        f"campaign attribution): {offenders}"
    )


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
