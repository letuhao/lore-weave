"""loreweave_internal_client — shared mechanics for internal (S2S) HTTP clients.

P3 SDK-first. The inventory found ~48 per-service internal HTTP clients that all share
the same construction (X-Internal-Token + JSON headers, per-request X-Trace-Id, an
httpx.Timeout, a 502/503/429-is-retryable rule) but re-typed it independently and drifted
(trace propagation present in some services, absent in others). This SDK owns the SHARED
MECHANICS so a client is reduced to its service-specific policy.

Design principle — COMPOSE, don't impose. The inventory showed fail-posture is
per-METHOD, not per-client (degrade / raise / swallow / verbatim-passthrough all coexist
in one class), so this SDK deliberately provides building blocks (a client factory, an
error base + retryable predicate, a shared resolver) and does NOT force a status check,
retry, or fail-posture. Each client keeps its load-bearing per-method semantics.

Reference shape: `sdks/python/loreweave_grants` (the already-extracted grant client) —
a shared client + settings-wired timeout + injectable trace_id_provider + thin per-service
shims.
"""
from __future__ import annotations

from ._errors import RETRYABLE_STATUSES, InternalClientError, is_retryable_status
from ._model_name import resolve_model_name
from ._transport import (
    HEADER_INTERNAL_TOKEN,
    HEADER_TRACE_ID,
    build_internal_client,
    build_timeout,
)

__all__ = [
    "HEADER_INTERNAL_TOKEN",
    "HEADER_TRACE_ID",
    "InternalClientError",
    "RETRYABLE_STATUSES",
    "build_internal_client",
    "build_timeout",
    "is_retryable_status",
    "resolve_model_name",
]
