"""Thin shim → the shared ``loreweave_grants`` SDK (D-E0-4 extraction).

The client core (GrantClient / GrantLevel / parse_grant_level) now lives in the
shared SDK; this module keeps knowledge-service's singleton + settings + trace-id
wiring so existing ``from app.clients.grant_client import ...`` call sites are
unchanged. The re-exports preserve a single GrantLevel identity across services.
"""

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
        timeout_s=settings.book_client_timeout_s,
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
