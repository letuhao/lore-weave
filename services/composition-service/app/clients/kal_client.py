"""KAL (knowledge-gateway) client — the single versioned knowledge READ boundary.

INV-KAL (spec §12.5.5): composition-service does NOT read the glossary EAV or the
KG directly, and does NOT call the owning services' ``/internal/*`` knowledge
routes for data the KAL exposes. Those reads (roster, facts, canonical, search,
timeline, neighborhood) go through this client → the knowledge-gateway typed
contract (``contracts/api/knowledge-gateway/kal.v1.yaml``).

Auth (mirrors the gateway's ``InternalTokenGuard`` + ``downstream.ts``): every call
presents ``X-Internal-Token`` (service-to-service) and forwards the caller's
``X-User-Id`` for tenancy. Composition must still verify book ownership upstream
(SEC2 chokepoint) before reaching these book-scoped reads — the internal token
trusts the caller, not the user.

v1 semantics == today's current projection (latest-valid facts), so this migration
is BEHAVIOR-PRESERVING: ``roster`` wraps the exact glossary
``/internal/books/{id}/entities`` list the old ``GlossaryClient.list_entities``
hit, projected to ``{entity_id, name}``. The one real fix here (D4 / §12.5.2):
``roster`` is *bounded-per-page, complete-in-aggregate* — we DRAIN ``next_cursor``
to completion so the cast list is no longer silently truncated at one page.

Graceful degradation (the planner ``_cast_roster`` contract): any transport error /
non-200 yields the partial-so-far (or empty) result and never raises — a KAL
outage thins the roster, it does not 500 a /decompose.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

# Safety cap on the keyset drain (§12.5.2: the roster is a snapshot as-of drain-start
# with a monotonic-id cursor). A bounded cap prevents an infinite loop on a
# pathological/never-null cursor; 200 pages × the 200/page server default (max 500)
# covers tens of thousands of entities — far past any real book's cast.
_ROSTER_MAX_PAGES = 200
_ROSTER_PAGE_LIMIT = 200

_client: "KalClient | None" = None


class KalClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self, user_id: UUID | str | None) -> dict[str, str]:
        headers = {"X-Internal-Token": self._internal_token}
        if user_id is not None:
            headers["X-User-Id"] = str(user_id)
        tid = trace_id_var.get()
        if tid:
            headers["X-Trace-Id"] = tid
        return headers

    async def roster(
        self, book_id: UUID, *, user_id: UUID | str | None = None,
    ) -> list[dict[str, Any]]:
        """The book's full cast — ``[{entity_id, name}, ...]`` — drained across the
        keyset cursor to completion (D4 fix: the old ``list_entities`` path read only
        the first page and ignored ``next_cursor``, truncating the cast).

        Bounded-but-complete (§12.5.2): each page is bounded; we follow ``next_cursor``
        until it is null (or the safety cap). Degrades to the partial-so-far list on
        any transport/HTTP failure — never raises (the planner tolerates a thin/empty
        roster: commit-time entity validation degrades to skip rather than false-reject).
        """
        url = f"{self._base_url}/v1/kal/books/{book_id}/roster"
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(_ROSTER_MAX_PAGES):
            params: dict[str, Any] = {"limit": _ROSTER_PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await self._http.get(url, params=params, headers=self._headers(user_id))
            except httpx.HTTPError as exc:
                logger.warning("kal roster unavailable (partial drain): %s", exc)
                return out
            if resp.status_code != 200:
                logger.warning("kal roster → %d (partial drain)", resp.status_code)
                return out
            try:
                data = resp.json()
            except (ValueError, AttributeError) as exc:
                logger.warning("kal roster bad JSON: %s", exc)
                return out
            items = data.get("items", []) if isinstance(data, dict) else []
            for e in items:
                eid, name = e.get("entity_id"), e.get("name")
                if eid and name:
                    out.append({"entity_id": str(eid), "name": name})
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not cursor:
                return out
        logger.warning(
            "kal roster drain hit the %d-page safety cap for book %s (cast may be incomplete)",
            _ROSTER_MAX_PAGES, book_id,
        )
        return out


def init_kal_client() -> KalClient:
    global _client
    if _client is None:
        _client = KalClient(settings.knowledge_gateway_url, settings.internal_service_token)
    return _client


def get_kal_client() -> KalClient:
    return _client or init_kal_client()


async def close_kal_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
