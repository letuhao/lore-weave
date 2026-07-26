"""Shared async HTTP transport for internal service-to-service clients.

The inventory (P3 SDK-first) found ~48 clients that ALL build an `httpx.AsyncClient`
with `X-Internal-Token` + `Content-Type: application/json`, and MOST want a per-request
`X-Trace-Id` — but trace propagation was implemented in only some services (chat /
knowledge / composition) and forgotten in others (translation / lore-enrichment /
campaign / jobs / video), plus the composition grant shim forgot to wire it at all.

`build_internal_client` collapses that shared construction into one factory so trace
propagation becomes uniform (opt-in via `trace_id_provider`) and the token/JSON header
baseline stops being re-typed per service.

Deliberately MECHANICS-ONLY: it returns a plain `httpx.AsyncClient`. It does NOT impose
a status check, retry policy, or fail-posture — each client keeps its own per-method
semantics (degrade / raise / swallow / verbatim-passthrough), which the inventory showed
are load-bearing and NOT uniform.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

import httpx

# Header names — one spelling, shared, so a typo can't split the fleet.
HEADER_INTERNAL_TOKEN = "X-Internal-Token"
HEADER_TRACE_ID = "X-Trace-Id"


def build_timeout(timeout_s: float, connect_timeout_s: float | None = None) -> httpx.Timeout:
    """A uniform `httpx.Timeout`. When `connect_timeout_s` is given, the connect phase
    gets its own (usually shorter) bound — the pattern provider-registry + lore-enrichment
    clients used (`httpx.Timeout(t, connect=5.0)`); otherwise one bound for all phases."""
    if connect_timeout_s is None:
        return httpx.Timeout(timeout_s)
    return httpx.Timeout(timeout_s, connect=connect_timeout_s)


def build_internal_client(
    base_url: str,
    *,
    internal_token: str,
    timeout_s: float = 10.0,
    connect_timeout_s: float | None = None,
    trace_id_provider: Callable[[], str | None] | None = None,
    extra_headers: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build a long-lived `httpx.AsyncClient` for an internal (S2S) target.

    Args:
        base_url: the target service base (trailing slash tolerated — httpx joins).
        internal_token: the `X-Internal-Token` secret (from settings.internal_service_token).
        timeout_s / connect_timeout_s: see `build_timeout`.
        trace_id_provider: called PER REQUEST to get the current trace id; when it
            returns a non-empty string an `X-Trace-Id` header is injected. Wired via an
            httpx request event-hook so the id is fresh per request (not baked at
            construction). Pass the service's `lambda: current_trace_id()` / contextvar
            getter to make trace propagation uniform.
        extra_headers: additional static headers baked at construction (e.g. an
            `X-Admin-Token`); per-request/per-call headers stay the caller's job.
        transport: optional httpx transport override (tests inject `httpx.MockTransport`;
            production omits it).

    Returns a client the caller owns — it must `await client.aclose()` on shutdown.
    """
    headers: dict[str, str] = {
        HEADER_INTERNAL_TOKEN: internal_token,
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    event_hooks: dict[str, list] = {}
    if trace_id_provider is not None:
        async def _inject_trace(request: httpx.Request) -> None:
            tid = trace_id_provider()
            if tid:
                request.headers[HEADER_TRACE_ID] = tid

        event_hooks["request"] = [_inject_trace]

    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
        timeout=build_timeout(timeout_s, connect_timeout_s),
        event_hooks=event_hooks or None,
        transport=transport,
    )
