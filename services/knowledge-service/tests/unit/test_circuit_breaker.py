"""Unit tests for K6.4 — glossary-client circuit breaker.

State machine under test:
  closed  →  N consecutive failures (N=3)  →  open
  open    →  cooldown elapsed              →  half-open (one probe)
  probe success → closed
  probe failure → re-open (clock resets)

Short-circuit: while open, select_for_context returns [] without
touching the HTTP client. We assert that by giving the client a
never-used MockTransport after the breaker is tripped.
"""
from __future__ import annotations

import time
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx

from app.clients.glossary_client import GlossaryClient


@pytest_asyncio.fixture
async def gc():
    client = GlossaryClient(
        base_url="http://glossary-service:8088",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=0,  # retries off so 1 call = 1 failure, simplifies counting
    )
    try:
        yield client
    finally:
        await client.aclose()


def _url_for(book_id: str) -> str:
    return f"http://glossary-service:8088/internal/books/{book_id}/select-for-context"


@pytest.mark.asyncio
async def test_breaker_opens_after_three_failures(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")

        # Three failing calls → breaker trips on the third.
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    assert gc._cb_opened_at is not None
    assert gc._cb_fail_count >= 3


@pytest.mark.asyncio
async def test_breaker_open_short_circuits_without_http_call(gc: GlossaryClient):
    book_id = uuid4()
    with respx.mock() as mock:
        route = mock.post(_url_for(str(book_id))).respond(503, text="down")
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )
        calls_after_open = route.call_count

        # Breaker is open now — the next call must NOT make an HTTP request.
        result = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )
        assert result == []
        assert route.call_count == calls_after_open, (
            "open breaker should short-circuit, no new HTTP call allowed"
        )


@pytest.mark.asyncio
async def test_breaker_half_open_probe_success_closes(gc: GlossaryClient, monkeypatch):
    """After cooldown, one probe is allowed through. Success → closed."""
    book_id = uuid4()

    # Trip the breaker with three 503s.
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    # Fast-forward monotonic clock past the cooldown.
    opened = gc._cb_opened_at
    assert opened is not None
    real_mono = time.monotonic
    offset = gc._CB_COOLDOWN_S + 1
    monkeypatch.setattr(
        "app.clients.glossary_client.time.monotonic",
        lambda: real_mono() + offset,
    )

    # Probe attempt returns 200 → breaker closes.
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(
            200, json={"entities": []}
        )
        result = await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert result == []  # empty list, but not short-circuited
    assert gc._cb_opened_at is None
    assert gc._cb_fail_count == 0


@pytest.mark.asyncio
async def test_breaker_half_open_probe_failure_reopens(gc: GlossaryClient, monkeypatch):
    """Probe failure → breaker stays open with a fresh cooldown."""
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    first_opened_at = gc._cb_opened_at
    assert first_opened_at is not None

    # Fast-forward past cooldown.
    real_mono = time.monotonic
    offset = gc._CB_COOLDOWN_S + 1
    monkeypatch.setattr(
        "app.clients.glossary_client.time.monotonic",
        lambda: real_mono() + offset,
    )

    # Probe fails → breaker re-opens with a new clock.
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="still down")
        await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert gc._cb_opened_at is not None
    assert gc._cb_opened_at > first_opened_at


@pytest.mark.asyncio
async def test_4xx_does_not_trip_breaker(gc: GlossaryClient):
    """4xx is a stable client error — upstream is healthy, breaker stays closed."""
    book_id = uuid4()
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(400, text="bad")
        for _ in range(5):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    assert gc._cb_opened_at is None
    assert gc._cb_fail_count == 0
