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


# ── D-T2-05 half-open probe serialization ──────────────────────────────────


@pytest.mark.asyncio
async def test_half_open_serializes_concurrent_probes(
    gc: GlossaryClient, monkeypatch,
):
    """D-T2-05: when cooldown has elapsed, N concurrent callers must
    NOT all dog-pile the upstream. Exactly one gets to probe; the
    rest short-circuit to [] and observe no HTTP call.

    Without the `_cb_probe_in_flight` guard, every coroutine that
    reaches `_cb_enter` during the half-open window would see the
    breaker as "openable" and fire its own request — undoing the
    whole point of a circuit breaker under load."""
    import asyncio

    book_id = uuid4()

    # Trip the breaker.
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )
    assert gc._cb_opened_at is not None

    # Fast-forward past cooldown.
    real_mono = time.monotonic
    offset = gc._CB_COOLDOWN_S + 1
    monkeypatch.setattr(
        "app.clients.glossary_client.time.monotonic",
        lambda: real_mono() + offset,
    )

    # Upstream answer pauses long enough for concurrent callers to
    # arrive while the probe is still in flight.
    async def slow_200(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"entities": []})

    with respx.mock() as mock:
        route = mock.post(_url_for(str(book_id))).mock(side_effect=slow_200)

        # Fire 5 concurrent calls. Probe should serialize them.
        results = await asyncio.gather(*[
            gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )
            for _ in range(5)
        ])

    # Exactly ONE HTTP call fired — the claimed probe. Four others
    # short-circuited to [] via the "open" state.
    assert route.call_count == 1, (
        f"expected 1 probe call, got {route.call_count} — "
        "probe serialization guard missing"
    )
    # All results are empty lists (short-circuits return [], the
    # probe returned entities=[] too).
    assert all(r == [] for r in results)
    # Probe closed the breaker on success.
    assert gc._cb_opened_at is None
    # Probe slot released.
    assert gc._cb_probe_in_flight is False


@pytest.mark.asyncio
async def test_probe_slot_released_after_failure(
    gc: GlossaryClient, monkeypatch,
):
    """Probe fails → breaker re-opens AND `_cb_probe_in_flight`
    returns to False so the NEXT cooldown window can claim a fresh
    probe. Without the release, subsequent probes would be forever
    blocked by a stuck flag."""
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    # Fast-forward past cooldown (first window).
    real_mono = time.monotonic
    offset = gc._CB_COOLDOWN_S + 1
    monkeypatch.setattr(
        "app.clients.glossary_client.time.monotonic",
        lambda: real_mono() + offset,
    )

    # Probe fails.
    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="still down")
        await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    # Slot released even though the probe failed — next cooldown can
    # re-probe.
    assert gc._cb_probe_in_flight is False
    assert gc._cb_opened_at is not None  # still open


@pytest.mark.asyncio
async def test_probe_slot_released_after_http_exception(
    gc: GlossaryClient, monkeypatch,
):
    """An unexpected exception inside the retry loop must still
    release the probe slot (finally block). Simulate this by mocking
    httpx.AsyncClient.post to raise a surprise error."""
    book_id = uuid4()

    with respx.mock() as mock:
        mock.post(_url_for(str(book_id))).respond(503, text="down")
        for _ in range(3):
            await gc.select_for_context(
                user_id=uuid4(), book_id=book_id, query="q"
            )

    real_mono = time.monotonic
    offset = gc._CB_COOLDOWN_S + 1
    monkeypatch.setattr(
        "app.clients.glossary_client.time.monotonic",
        lambda: real_mono() + offset,
    )

    # Force a non-httpx exception mid-call (e.g. a typo-level
    # RuntimeError from some future refactor).
    from unittest.mock import AsyncMock as _AsyncMock

    async def raising_post(*args, **kwargs):
        raise RuntimeError("surprise!")

    monkeypatch.setattr(gc._http, "post", _AsyncMock(side_effect=raising_post))

    # The unexpected RuntimeError bubbles up — that's fine. What
    # matters is that the probe slot gets released so the next
    # cooldown window isn't blocked forever.
    with pytest.raises(RuntimeError):
        await gc.select_for_context(
            user_id=uuid4(), book_id=book_id, query="q"
        )

    assert gc._cb_probe_in_flight is False
