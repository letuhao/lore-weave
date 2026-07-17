"""Minimal auth-service preferences writer (D-DIVERGENCE-MCP-TOOLS · switch_active_work).

Composition owns the "which Work is active for a book" concept, but the preference is stored in
auth-service's `user_preferences` — the SAME store the FE reads via `/v1/me/preferences`. To set it
from an MCP tool we mint a short-lived USER bearer (the established cross-service on-behalf-of-user
pattern, same as book/knowledge calls) and PATCH the existing JWT route — no new auth-service route,
one source of truth (no drift with the FE).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.mcp.service_bearer import mint_service_bearer


class AuthPrefsError(Exception):
    """auth-service unreachable or non-2xx on the preference write."""


async def set_user_preference(user_id: UUID, key: str, value: Any) -> None:
    """Merge ``{key: value}`` into the user's preferences (auth-service does `prefs || $2`). A null
    value clears the key. Raises AuthPrefsError on transport failure or a non-2xx status."""
    bearer = mint_service_bearer(user_id, settings.jwt_secret, ttl=60)
    url = f"{settings.auth_internal_url.rstrip('/')}/v1/me/preferences"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.patch(
                url,
                headers={"Authorization": f"Bearer {bearer}"},
                json={"prefs": {key: value}},
            )
    except httpx.HTTPError as exc:
        raise AuthPrefsError(f"auth-service unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise AuthPrefsError(f"auth-service {resp.status_code}: {resp.text[:200]}")
