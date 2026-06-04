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
    def __init__(self, base_url: str, timeout_s: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))

    async def aclose(self) -> None:
        await self._http.aclose()

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
        tid = trace_id_var.get()
        headers = {"Authorization": f"Bearer {bearer}"}
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            resp = await self._http.get(
                url, params={"book_id": str(book_id), "limit": "100"}, headers=headers,
            )
        except httpx.HTTPError as exc:
            logger.warning("knowledge unreachable: %s trace_id=%s", exc, tid)
            return None
        if resp.status_code != 200:
            logger.warning(
                "knowledge %s → %d trace_id=%s", url, resp.status_code, tid
            )
            return None
        try:
            return resp.json().get("items", [])
        except (ValueError, AttributeError) as exc:
            logger.warning("knowledge bad JSON: %s trace_id=%s", exc, tid)
            return None


def init_knowledge_client() -> KnowledgeClient:
    global _client
    if _client is None:
        _client = KnowledgeClient(settings.knowledge_internal_url)
    return _client


def get_knowledge_client() -> KnowledgeClient:
    return _client or init_knowledge_client()


async def close_knowledge_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
