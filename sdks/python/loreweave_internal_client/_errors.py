"""Shared error base for internal service-to-service clients.

The inventory (P3 SDK-first) found ~5 standalone exception classes across services
(`KalServiceError`, `GlossaryServiceError`, `KnowledgeServiceError`, `BookServiceError`,
two `EmbeddingError`s, worker-ai result dataclasses) that all independently encode the
SAME rule: a 502/503/429 is retryable, everything else is not. This unifies that one
rule so a caller can uniformly ask `.retryable` without every client re-deriving it.

This is deliberately MINIMAL — it does NOT impose a fail-posture. A client that
degrades-to-empty, swallows (fire-and-forget), passes status through verbatim, or
raises is free to keep doing so; this only provides the shared retryable-status
predicate + an optional typed error for the clients that DO raise.
"""
from __future__ import annotations

# The transient-status set every client's `retryable` flag independently re-derived.
# 502 Bad Gateway / 503 Service Unavailable / 429 Too Many Requests — a redelivery or
# retry can succeed. A 4xx (except 429) or a 5xx 500/501 is NOT retried (a bug/contract
# error won't fix itself).
RETRYABLE_STATUSES = frozenset({429, 502, 503})


def is_retryable_status(status_code: int | None) -> bool:
    """True iff a request that got `status_code` is worth retrying/redelivering."""
    return status_code in RETRYABLE_STATUSES


class InternalClientError(Exception):
    """Base for a typed internal-client failure (for clients that RAISE).

    Carries the upstream `status_code` (None on a transport error) and a `retryable`
    flag derived from it. Per-service clients that already raise typed errors should
    subclass this so callers get one uniform `.retryable`/`.status_code` surface;
    clients that degrade/swallow do not need it.
    """

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool | None = None):
        super().__init__(message)
        self.status_code = status_code
        # Explicit override wins (e.g. a transport error a client deems retryable);
        # otherwise derive from the status.
        self.retryable = is_retryable_status(status_code) if retryable is None else retryable
