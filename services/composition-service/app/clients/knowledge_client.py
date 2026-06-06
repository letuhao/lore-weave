"""knowledge-service client (composition-service, M2 — resolve slice only).

M2 pulls this ONE read forward from M3 to do the full §6.2 Work resolution:
list the knowledge projects linked to a book so resolve can tell
no-project / unmarked-single / candidates apart.

AUTH (contract-verified 2026-06-03): `GET /v1/knowledge/projects?book_id=` is
**JWT-only** — there is no internal-token variant. So this client FORWARDS the
caller's user `Authorization: Bearer`, NOT the internal service token. That is
the secure choice for resolve: knowledge derives user_id from the JWT `sub` and
filters every row by it, so a cross-user book_id returns an empty list — the
ownership check is enforced server-side by the forwarding itself. (The §2.5
internal-token ownership chokepoint applies to the M4 packer's /internal reads,
not here.)

Graceful degradation (mirrors knowledge-service's book_client): any transport
error / non-200 returns None so resolve can surface "knowledge unavailable"
rather than 500. The base URL is the in-cluster host (`knowledge_internal_url`);
the route it serves is the public `/v1/knowledge` prefix.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

_client: "KnowledgeClient | None" = None


class KnowledgeClient:
    def __init__(
        self, base_url: str, internal_token: str = "", timeout_s: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))

    async def aclose(self) -> None:
        await self._http.aclose()

    def _bearer_headers(self, bearer: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {bearer}"}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        return headers

    def _internal_headers(self) -> dict[str, str]:
        headers = {"X-Internal-Token": self._internal_token}
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        return headers

    async def list_projects_for_book(
        self, book_id: UUID, bearer: str
    ) -> list[dict[str, Any]] | None:
        """Projects linked to `book_id` for the JWT's user. Returns the items
        list, or None on any transport/HTTP failure (caller treats None as
        'knowledge unavailable'). `bearer` is the raw JWT (no 'Bearer ' prefix);
        we add the scheme. Empty header → return None (can't authenticate)."""
        if not bearer:
            logger.warning("knowledge resolve called without a bearer token")
            return None
        url = f"{self._base_url}/v1/knowledge/projects"
        try:
            resp = await self._http.get(
                url, params={"book_id": str(book_id), "limit": "100"},
                headers=self._bearer_headers(bearer),
            )
        except httpx.HTTPError as exc:
            logger.warning("knowledge unreachable: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning("knowledge %s → %d", url, resp.status_code)
            return None
        try:
            return resp.json().get("items", [])
        except (ValueError, AttributeError) as exc:
            logger.warning("knowledge bad JSON: %s", exc)
            return None

    async def create_project(
        self, book_id: UUID, name: str, bearer: str,
    ) -> dict[str, Any] | None:
        """Create a BOOK-typed knowledge project for this book (M8 POST /work).
        JWT-forward → knowledge scopes it to the user. Returns the created
        project dict (carries `project_id`) or None on failure."""
        if not bearer:
            return None
        url = f"{self._base_url}/v1/knowledge/projects"
        payload = {"name": name, "project_type": "book", "book_id": str(book_id)}
        try:
            resp = await self._http.post(url, json=payload, headers=self._bearer_headers(bearer))
            if resp.status_code not in (200, 201):
                logger.warning("knowledge create_project → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge create_project unavailable: %s", exc)
            return None

    # ── M4 packer lenses ────────────────────────────────────────────────
    # All return None/[] on any failure (the packer `_safe_*` degrade, F1) so a
    # knowledge outage thins the pack rather than 500-ing a generate.

    async def build_context(
        self, user_id: UUID, *, project_id: UUID | None, message: str = "",
        session_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """POST /internal/context/build (X-Internal-Token). The caller MUST have
        verified book/project ownership first (SEC2) — the internal endpoint
        trusts the token, not the user. Returns the context envelope
        (`context`/`stable_context`/`volatile_context`/`token_count`) or None."""
        url = f"{self._base_url}/internal/context/build"
        payload: dict[str, Any] = {"user_id": str(user_id), "message": message}
        if project_id is not None:
            payload["project_id"] = str(project_id)
        if session_id is not None:
            payload["session_id"] = str(session_id)
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
            if resp.status_code != 200:
                logger.warning("knowledge context/build → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge context/build unavailable: %s", exc)
            return None

    async def timeline(
        self, bearer: str, *, project_id: UUID, before_chronological: int | None = None,
        before_order: int | None = None, entity_id: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """L1b — in-world events for a project (JWT-forward). `project_id` is
        ALWAYS sent (A1/§12: omitting it widens to ALL the user's projects).
        `before_chronological` is the true in-world spoiler cutoff. Returns the
        events list (each carries `chronological_order`/`event_order`/`title`/
        `summary`/`participants`) or [] on failure."""
        params: dict[str, Any] = {"project_id": str(project_id), "limit": limit}
        if before_chronological is not None:
            params["before_chronological"] = before_chronological
        if before_order is not None:
            params["before_order"] = before_order
        if entity_id is not None:
            params["entity_id"] = entity_id
        return await self._jwt_get_list(
            "/v1/knowledge/timeline", params, bearer, key="events", label="timeline",
        )

    async def get_entity(self, bearer: str, entity_id: str) -> dict[str, Any] | None:
        """L1a — a single entity's current state + currently-valid relations
        (the detail endpoint filters `valid_until IS NULL` server-side).
        JWT-forward. Returns `{entity, relations, ...}` or None."""
        url = f"{self._base_url}/v1/knowledge/entities/{entity_id}"
        try:
            resp = await self._http.get(url, headers=self._bearer_headers(bearer))
            if resp.status_code != 200:
                logger.warning("knowledge entity %s → %d", entity_id, resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge entity unavailable: %s", exc)
            return None

    async def search_drawers(
        self, bearer: str, *, project_id: UUID, query: str, limit: int = 40,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """L4 — semantic search (JWT-forward). `project_id` is REQUIRED by the
        endpoint (cross-project unsupported). Each hit carries `source_id` +
        `chapter_index` (int|None — the packer's reading-order spoiler axis) +
        `raw_score` (NOT `score`). Returns hits or [] on failure."""
        params: dict[str, Any] = {
            "project_id": str(project_id), "query": query, "limit": limit,
        }
        if source_type is not None:
            params["source_type"] = source_type
        return await self._jwt_get_list(
            "/v1/knowledge/drawers/search", params, bearer, key="hits", label="drawers",
        )

    async def fact_for_check(
        self, *, project_id: UUID, at_order: int,
        glossary_entity_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """A2-S2/S3 — the canon snapshot (status@P + entities + relations +
        events≤P) for the SCORE symbolic guard. POST /internal/projects/{id}/
        fact-for-check (X-Internal-Token). The cast is composition's glossary
        entity ids (resolved server-side via the glossary_entity_id FK).
        Returns the snapshot dict or None on any failure (the guard degrades to
        advisory — a knowledge outage must never block a generate, F1)."""
        if not glossary_entity_ids and not entity_ids:
            return None
        url = f"{self._base_url}/internal/projects/{project_id}/fact-for-check"
        payload: dict[str, Any] = {"at_order": at_order}
        if glossary_entity_ids:
            payload["glossary_entity_ids"] = list(glossary_entity_ids)
        if entity_ids:
            payload["entity_ids"] = list(entity_ids)
        try:
            resp = await self._http.post(url, json=payload, headers=self._internal_headers())
            if resp.status_code != 200:
                logger.warning("knowledge fact-for-check → %d", resp.status_code)
                return None
            return resp.json()
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge fact-for-check unavailable: %s", exc)
            return None

    async def _jwt_get_list(
        self, path: str, params: dict[str, Any], bearer: str, *, key: str, label: str,
    ) -> list[dict[str, Any]]:
        url = f"{self._base_url}{path}"
        try:
            resp = await self._http.get(url, params=params, headers=self._bearer_headers(bearer))
            if resp.status_code != 200:
                logger.warning("knowledge %s → %d", label, resp.status_code)
                return []
            return resp.json().get(key, [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("knowledge %s unavailable: %s", label, exc)
            return []


def init_knowledge_client() -> KnowledgeClient:
    global _client
    if _client is None:
        _client = KnowledgeClient(
            settings.knowledge_internal_url, settings.internal_service_token,
        )
    return _client


def get_knowledge_client() -> KnowledgeClient:
    return _client or init_knowledge_client()


async def close_knowledge_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
