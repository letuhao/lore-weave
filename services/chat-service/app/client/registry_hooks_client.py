"""HTTP client for agent-registry-service's /internal/hooks (P4 REG-P4-03).

Fetches the user's + book's declarative hooks so the chat-turn loop can evaluate them
at its seams. Graceful degradation is the contract (mirrors registry_commands_client):
any failure returns NO hooks and the turn runs unhooked — a hook is a guardrail the
user opted into, never load-bearing for the turn to complete.

Response shape from /internal/hooks:
  { "catalog_version": <int>,
    "hooks": [{on_event, match, action, priority, tier}, ...] }  # sorted priority DESC
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "HooksClient",
    "init_hooks_client",
    "close_hooks_client",
    "get_hooks_client",
]


class HooksClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_hooks(self, user_id: str, *, book_id: str = "") -> list[dict]:
        """GET /internal/hooks — returns the hook list, [] on ANY failure."""
        if not user_id:
            return []
        params = {"user_id": user_id}
        if book_id:
            params["book_id"] = book_id
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(f"{self._base_url}/internal/hooks", params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise into the turn
            logger.warning("hooks unavailable (unhooked turn): %s", type(exc).__name__)
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return []
        hooks = data.get("hooks") if isinstance(data, dict) else None
        return [h for h in hooks if isinstance(h, dict) and h.get("on_event")] if isinstance(hooks, list) else []


_client: HooksClient | None = None


def init_hooks_client() -> HooksClient:
    global _client
    if _client is None:
        _client = HooksClient(
            base_url=settings.agent_registry_url,
            internal_token=settings.internal_service_token,
            timeout_s=settings.agent_registry_timeout_s,
        )
    return _client


async def close_hooks_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_hooks_client() -> HooksClient:
    return _client or init_hooks_client()
