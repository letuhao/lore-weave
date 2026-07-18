"""Grant access check for chat-service — the shared ``loreweave_grants`` SDK.

Track C Phase 2 (/review-impl HIGH). The book-state probe fans a CLIENT-SUPPLIED
``book_id`` (from ``book_context.book_id`` in the request body) out to five internal
routes, four of which do not grant-check the caller. A user could therefore set
``book_context.book_id`` to another user's book and read its state — categories, cast,
chapters, plan counts, and (via the ontology read) its kind NAMES — straight into their rail
progress block. This is the exact class the LOCKED rule names: an internal route driven by a
session must grant-check.

The cheapest CORRECT fix closes all five sources with ONE check: verify the caller has at
least View access to the book BEFORE the probe runs. The SDK fails CLOSED (a book-service
blip → NONE) and caches positive grants for its TTL, so this adds one cached round trip per
turn, not five.
"""

from __future__ import annotations

from loreweave_grants import GrantClient, GrantLevel, parse_grant_level

from app.config import settings
from app.middleware.trace_id import trace_id_var

__all__ = [
    "GrantLevel",
    "parse_grant_level",
    "GrantClient",
    "get_grant_client",
    "close_grant_client",
]

_client: GrantClient | None = None


def get_grant_client() -> GrantClient:
    global _client
    if _client is None:
        _client = GrantClient(
            base_url=settings.book_service_url,
            internal_token=settings.internal_service_token,
            timeout_s=settings.book_steering_timeout_s,
            trace_id_provider=trace_id_var.get,
        )
    return _client


async def close_grant_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
