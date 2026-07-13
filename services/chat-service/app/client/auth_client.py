"""DBT-11 / D-R14 — resolve a user's timezone from auth-service, cached in-process.

The message-write path buckets ``chat_messages.local_date`` by the user's LOCAL day
(see ``app.services.local_date``). The timezone is a platform-wide per-user preference
(sealed T-1) stored in auth's ``user_preferences``; auth exposes it on its token-gated
internal profile endpoint. We cache it per-process with a TTL so a chat stream does not
re-fetch it every message, and DEGRADE to ``None`` (⇒ UTC day) on any failure — the
write must never block on auth.
"""

from __future__ import annotations

import logging
import time
from datetime import date

from loreweave_internal_client import build_internal_client

from app.config import settings
from app.middleware.trace_id import trace_id_var
from app.services.local_date import compute_local_date

logger = logging.getLogger(__name__)


class AuthClient:
    def __init__(self) -> None:
        self._base = settings.auth_service_url
        self._token = settings.internal_service_token
        # user_id -> (timezone_or_None, expiry_monotonic). A negative result
        # (no tz set) is cached too, so an all-UTC deployment doesn't hammer auth.
        self._cache: dict[str, tuple[str | None, float]] = {}

    async def get_user_timezone(self, user_id: str) -> str | None:
        now = time.monotonic()
        hit = self._cache.get(user_id)
        if hit is not None and hit[1] > now:
            return hit[0]

        tz: str | None = None
        try:
            async with build_internal_client(
                self._base, internal_token=self._token,
                timeout_s=settings.user_timezone_timeout_s,
                trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.get(f"{self._base}/internal/users/{user_id}/profile")
                if resp.status_code == 200:
                    val = resp.json().get("timezone")
                    tz = val if isinstance(val, str) and val else None
                else:
                    logger.debug("auth profile for tz returned %d", resp.status_code)
        except Exception as exc:  # noqa: BLE001 — degrade to UTC, never block the write
            logger.debug("get_user_timezone failed (degrading to UTC): %s", exc)

        self._cache[user_id] = (tz, now + settings.user_timezone_cache_ttl_s)
        return tz


_client: AuthClient | None = None


def get_auth_client() -> AuthClient:
    global _client
    if _client is None:
        _client = AuthClient()
    return _client


async def resolve_local_date(user_id: str) -> date:
    """The user's LOCAL calendar day right now (DBT-11) — the value stamped into
    ``chat_messages.local_date`` at write time. Degrades to the UTC day on any auth
    failure (compute_local_date treats None as UTC), so the message write is safe."""
    tz = await get_auth_client().get_user_timezone(user_id)
    return compute_local_date(tz)
