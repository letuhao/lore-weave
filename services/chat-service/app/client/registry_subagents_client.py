"""HTTP client for agent-registry-service's /internal/subagents (P5 REG-P5-01).

Fetches the user's + book's enabled subagent personas so the chat-turn loop can
advertise `run_subagent` and run a scoped nested turn. Graceful degradation is the
contract (mirrors registry_hooks_client / registry_commands_client): any failure
returns NO subagents and the turn runs without the delegation tool — subagents are
an opt-in capability, never load-bearing for the turn to complete.

Response shape from /internal/subagents:
  { "catalog_version": <int>,
    "subagents": [{name, description, system_prompt, tool_scope, model_ref, tier}, ...] }
  # already higher-tier-shadowed by name (book ▷ user ▷ system) by the resolver.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "SubagentsClient",
    "init_subagents_client",
    "close_subagents_client",
    "get_subagents_client",
]


def _coerce_scope(raw) -> list[str]:
    """tool_scope arrives as a JSON array of globs (possibly a JSON string)."""
    if isinstance(raw, list):
        return [g for g in raw if isinstance(g, str) and g]
    if isinstance(raw, str) and raw:
        try:
            arr = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
        return [g for g in arr if isinstance(g, str) and g] if isinstance(arr, list) else []
    return []


class SubagentsClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 2.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_subagents(self, user_id: str, *, book_id: str = "") -> list[dict]:
        """GET /internal/subagents — returns the enabled subagent list, [] on ANY
        failure. Each entry is normalized: tool_scope → list[str]."""
        if not user_id:
            return []
        params = {"user_id": user_id}
        if book_id:
            params["book_id"] = book_id
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(
                f"{self._base_url}/internal/subagents", params=params, headers=headers
            )
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise into the turn
            logger.warning("subagents unavailable (no delegation): %s", type(exc).__name__)
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return []
        subs = data.get("subagents") if isinstance(data, dict) else None
        if not isinstance(subs, list):
            return []
        out: list[dict] = []
        for s in subs:
            if not isinstance(s, dict):
                continue
            name = s.get("name")
            prompt = s.get("system_prompt")
            if not isinstance(name, str) or not name or not isinstance(prompt, str) or not prompt:
                continue
            out.append({
                "name": name,
                "description": str(s.get("description") or ""),
                "system_prompt": prompt,
                "tool_scope": _coerce_scope(s.get("tool_scope")),
                "model_ref": str(s.get("model_ref") or ""),
                "tier": str(s.get("tier") or ""),
            })
        return out


_client: SubagentsClient | None = None


def init_subagents_client() -> SubagentsClient:
    global _client
    if _client is None:
        _client = SubagentsClient(
            base_url=settings.agent_registry_url,
            internal_token=settings.internal_service_token,
            timeout_s=settings.agent_registry_timeout_s,
        )
    return _client


async def close_subagents_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_subagents_client() -> SubagentsClient:
    return _client or init_subagents_client()
