import asyncpg

from app.clients.grant_client import GrantClient, get_grant_client
from app.db.pool import get_pool


async def get_db() -> asyncpg.Pool:
    return get_pool()


def get_grant_client_dep() -> GrantClient:
    """FastAPI dependency over the shared grant-client singleton — overridable in
    tests via ``dependency_overrides`` (D-ENRICH-MCP-OWNER-GATE)."""
    return get_grant_client()


__all__ = ["get_db", "get_grant_client_dep"]
