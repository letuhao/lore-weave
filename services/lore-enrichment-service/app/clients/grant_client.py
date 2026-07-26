"""Thin shim → the shared ``loreweave_grants`` SDK (D-ENRICH-MCP-OWNER-GATE).

lore-enrichment had book/glossary/knowledge clients but NO grant client, so
``auto_enrich`` took ``book_id`` as a free arg with no tenancy check — any authed
caller could enqueue a caller-PAID enrichment grounded on another user's book.
This wires the same shared E0 grant authority every other Python service uses
(composition / knowledge / translation) so the enrich path can gate on a real
(user, book) grant. The singleton + settings wiring lives here; the call site
resolves a grant via ``get_grant_client``.

Fail-closed: a book-service outage resolves to ``GrantLevel.NONE`` (deny) — the
gate maps that to 404 (never an existence oracle).
"""

from __future__ import annotations

from loreweave_grants import GrantClient, GrantLevel, parse_grant_level

from app.config import settings
from app.logging_config import trace_id_var

__all__ = [
    "GrantLevel",
    "parse_grant_level",
    "GrantClient",
    "init_grant_client",
    "get_grant_client",
    "close_grant_client",
]

_client: GrantClient | None = None


def init_grant_client() -> GrantClient:
    global _client
    if _client is not None:
        return _client
    _client = GrantClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
        trace_id_provider=trace_id_var.get,
    )
    return _client


async def close_grant_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_grant_client() -> GrantClient:
    if _client is None:
        return init_grant_client()
    return _client
