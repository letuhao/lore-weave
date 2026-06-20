"""Thin shim → the shared ``loreweave_grants`` SDK (E0-4b adoption).

The client core (GrantClient / GrantLevel / parse_grant_level) lives in the shared
SDK; this module keeps campaign-service's singleton + settings wiring so call sites
use ``from app.grant_client import ...``. The re-exports preserve a single
GrantLevel identity across services.
"""

from loreweave_grants import GrantClient, GrantLevel, parse_grant_level

from .config import settings

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
        base_url=settings.book_service_internal_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.dispatch_timeout_s,
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
