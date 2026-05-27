"""K17.10 — Pytest config for opt-in golden-set quality eval.

The quality eval hits a real LLM (K17.4–K17.8 Pass 2 pipeline) and
so should NOT run in the default unit-test pass. Pass
``--run-quality`` to enable.

    cd services/knowledge-service
    pytest tests/quality/ --run-quality -v

Without the flag, tests marked ``@pytest.mark.quality`` are skipped
with a clear reason.

## Asyncio teardown fix (MED-8, session 2026-05-27 eval framework cycle)

Earlier sessions hit `RuntimeError: Event loop is closed` when running
test_judge_discriminates_fabricated_items followed by
test_llm_judge_extraction_quality in the same pytest invocation. Root
cause: the module-level `_client` singleton in
`app.clients.llm_client` was created against test 1's event loop, then
test 2's new event loop tried to use the now-disposed httpx transport.

Fix per MED-8: the `fresh_llm_client` function-scoped fixture below
resets the module-level singleton before each test + tears it down
after, guaranteeing each async test runs with a client bound to its
own event loop. Tests that use the legacy `get_llm_client()` directly
get the fix transparently via the autouse `_reset_llm_singleton`
fixture.

Closes D-JUDGE-EVAL-ASYNCIO-TEARDOWN.
"""

from __future__ import annotations

import pytest
import pytest_asyncio


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-quality",
        action="store_true",
        default=False,
        help="Run the K17.10 opt-in golden-set extraction quality eval.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-quality"):
        return
    skip = pytest.mark.skip(reason="opt-in K17.10 eval; pass --run-quality")
    for item in items:
        if "quality" in item.keywords:
            item.add_marker(skip)


# ── MED-8 asyncio teardown fix ───────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _reset_llm_singleton():
    """Reset the module-level `_client` singleton before AND after each test.

    The module-level singleton would otherwise leak across tests, binding
    the SDK Client (and its httpx connection pool) to the FIRST test's
    event loop. Subsequent tests' new event loops would crash with
    `Event loop is closed` on the next async I/O.

    Autouse → applies to every test under tests/quality/ without explicit
    parametrization. Pre-test reset ensures a clean slate (in case some
    prior test/import polluted the singleton); post-test reset closes
    the client cleanly per-test.

    Hands the test the freshly-initialized singleton via `get_llm_client()`
    semantics — tests don't need to know about the fixture.
    """

    # Import lazily so this fixture survives a state where the module
    # hasn't been touched yet (e.g., tests that don't use the client).
    from app.clients import llm_client as _llm_client_mod

    # PRE-test reset: clear any leaked instance from earlier modules
    if getattr(_llm_client_mod, "_client", None) is not None:
        try:
            await _llm_client_mod.close_llm_client()
        except Exception:
            # Ignore — old client's loop is dead anyway; just discard it
            _llm_client_mod._client = None

    yield

    # POST-test cleanup
    if getattr(_llm_client_mod, "_client", None) is not None:
        try:
            await _llm_client_mod.close_llm_client()
        except Exception:
            _llm_client_mod._client = None


@pytest_asyncio.fixture
async def fresh_llm_client():
    """Explicit per-test LLMClient — alternative to autouse singleton reset.

    Use this when a test needs to override client params (e.g., shorter
    timeouts, different base_url). Yields a fresh `LLMClient` instance and
    closes it on teardown — guarantees client lifetime is contained to
    the test's event loop. Closes D-JUDGE-EVAL-ASYNCIO-TEARDOWN.
    """

    from app.clients.llm_client import LLMClient
    from app.config import settings
    from loreweave_llm.client import Client as SDKClient

    sdk = SDKClient(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=None,
    )
    client = LLMClient(sdk)
    try:
        yield client
    finally:
        await client.aclose()
