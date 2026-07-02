"""HTTP client for agent-registry-service's /internal/skills endpoint (P1).

Fetches the user's + book's prompt-only skills so chat-service can inject them
alongside the built-in SYSTEM_SKILLS. Graceful degradation is the contract
(mirrors book_steering_client): EVERY failure path returns an EMPTY result and
never raises into the chat turn — user skills are an enrichment, so a
registry outage leaves the turn on the built-in skills only (REG-P1-05 fallback).

Response shape from /internal/skills:
  {
    "catalog_version": <int>,
    "skills": [{slug, description, body_md, l1_line, surfaces, tier, source}, ...],
    "system_overrides": {<system_slug>: false, ...},   # System slugs the user disabled
    "shadowed_system": [<slug>, ...]                    # System slugs a user skill overrides
  }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.middleware.trace_id import current_trace_id

logger = logging.getLogger(__name__)

__all__ = [
    "UserSkills",
    "UserSkillsClient",
    "init_user_skills_client",
    "close_user_skills_client",
    "get_user_skills_client",
]


@dataclass(frozen=True)
class UserSkills:
    """Resolved user/book skills for one turn. Empty = built-ins only (fallback)."""

    skills: list[dict] = field(default_factory=list)
    system_overrides: dict[str, bool] = field(default_factory=dict)
    shadowed_system: frozenset[str] = frozenset()

    def system_disabled(self, slug: str) -> bool:
        """True if the user explicitly disabled this System skill."""
        return self.system_overrides.get(slug) is False

    def shadows(self, slug: str) -> bool:
        """True if a user skill of this slug overrides the System one."""
        return slug in self.shadowed_system

    @property
    def l1_lines(self) -> list[str]:
        return [s["l1_line"] for s in self.skills if s.get("l1_line")]


_EMPTY = UserSkills()


class UserSkillsClient:
    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float = 2.0,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        kwargs: dict = {
            "timeout": httpx.Timeout(timeout_s),
            "headers": {"X-Internal-Token": internal_token},
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**kwargs)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_skills(self, user_id: str, *, book_id: str = "", surface: str = "") -> UserSkills:
        """GET /internal/skills — returns UserSkills on success, _EMPTY on ANY failure."""
        if not user_id:
            return _EMPTY
        params = {"user_id": user_id}
        if book_id:
            params["book_id"] = book_id
        if surface:
            params["surface"] = surface
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(f"{self._base_url}/internal/skills", params=params, headers=headers)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise
            logger.warning("user skills unavailable (fallback to constants): %s", type(exc).__name__)
            return _EMPTY
        if resp.status_code != 200:
            logger.warning("user skills %d (fallback to constants)", resp.status_code)
            return _EMPTY
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("user skills decode failure: %s", exc)
            return _EMPTY
        if not isinstance(data, dict):
            return _EMPTY
        skills = data.get("skills")
        if not isinstance(skills, list):
            skills = []
        overrides = data.get("system_overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        shadowed = data.get("shadowed_system")
        shadow_set = frozenset(shadowed) if isinstance(shadowed, list) else frozenset()
        # keep only well-formed skill dicts
        clean = [s for s in skills if isinstance(s, dict) and isinstance(s.get("slug"), str)]
        return UserSkills(skills=clean, system_overrides=overrides, shadowed_system=shadow_set)


_client: UserSkillsClient | None = None


def init_user_skills_client() -> UserSkillsClient:
    global _client
    if _client is not None:
        return _client
    _client = UserSkillsClient(
        base_url=settings.agent_registry_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.agent_registry_timeout_s,
    )
    return _client


async def close_user_skills_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_user_skills_client() -> UserSkillsClient:
    global _client
    if _client is None:
        return init_user_skills_client()
    return _client
