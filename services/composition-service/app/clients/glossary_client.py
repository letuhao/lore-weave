"""glossary-service client (composition-service, M3 — packer L0 lens).

Contract-verified 2026-06-04 (glossary server.go): both surfaces below are
**INTERNAL** (`X-Internal-Token`) and book-scoped only — they do NOT re-check the
user. So composition MUST verify book ownership (BookClient.owns_book) BEFORE
calling these (SEC2 chokepoint); the M4 packer is responsible for that gate.

Graceful degradation (the packer `_safe_*` pattern, §2.5/F1): every method
returns [] / None on any failure and never raises — a glossary outage degrades
the pack (thinner context), it does not 500 a generate. We cache the STABLE
glossary `entity_id` (never knowledge's rename-sensitive canonical_id, §13 DI3).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

_client: "GlossaryClient | None" = None


class GlossaryClientError(Exception):
    """Non-2xx or transport failure from glossary-service. Unlike this
    client's other methods (deliberately degrade-safe for read-time context
    assembly — a glossary outage should never 500 a generate), the
    PlanForge auto-bootstrap gate's `seed_entities_or_raise` needs the
    OPPOSITE contract: a mutation the gate is about to record as "applied"
    must surface its real failure, never silently look like success. `code`
    carries glossary-service's error code (e.g. GLOSS_BOOK_NOT_SCAFFOLDED
    when the book's ontology was never adopted — see book_adopt_handler.go)
    so the caller can give an actionable message instead of a bare 5xx."""

    def __init__(self, status: int, code: str | None, detail: str | None = None) -> None:
        super().__init__(f"glossary-service {status} {code or ''}".strip())
        self.status = status
        self.code = code
        self.detail = detail


class GlossaryClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        # W3: shared factory bakes X-Internal-Token + JSON + per-request X-Trace-Id.
        self._http = build_internal_client(
            base_url, internal_token=internal_token,
            timeout_s=timeout_s, trace_id_provider=trace_id_var.get,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def select_for_context(
        self, book_id: UUID, user_id: UUID, query: str, *,
        max_entities: int = 20, max_tokens: int = 1000,
        exclude_ids: list[str] | None = None,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        """L0/L1 glossary entities most relevant to `query` for this book.
        Returns the entities list (each carries the stable `entity_id`,
        `cached_name`, `cached_aliases`, `short_description`, `kind_code`,
        `tier`), or [] on any failure.

        KG-ML M7 (C6): `language` (the author's reader-language) augments each
        entity's aliases with that language's alias set (glossary S6
        `composePerLanguageAliases`), so the pack carries the names a vi author
        actually uses. Omitted → source-language aliases only (back-compat)."""
        url = f"{self._base_url}/internal/books/{book_id}/select-for-context"
        payload: dict[str, Any] = {
            "user_id": str(user_id), "query": query,
            "max_entities": max_entities, "max_tokens": max_tokens,
        }
        if exclude_ids:
            payload["exclude_ids"] = exclude_ids
        if language:
            payload["language"] = language
        try:
            resp = await self._http.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("glossary select-for-context → %d", resp.status_code)
                return []
            return resp.json().get("entities", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("glossary select-for-context unavailable: %s", exc)
            return []

    # NOTE: the book's full cast roster (the old `list_entities` → glossary
    # `/internal/books/{id}/entities`) moved to the KAL (`KalClient.roster`) under
    # INV-KAL — composition reads the cast through the knowledge-gateway, which
    # owns + drains that bounded-but-complete list (X1 / D4). The direct glossary
    # entity-list read was removed here so it can't be reintroduced as a bypass.


    async def seed_entities_or_raise(
        self, book_id: UUID, *, source_language: str, entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Same wire call as `seed_entities` (bulk create/upsert via
        `extract-entities`), but RAISES `GlossaryClientError` on any non-2xx
        instead of degrading to `[]` — for the PlanForge auto-bootstrap
        gate's apply() step (docs/specs/2026-07-06-planforge-auto-bootstrap.md
        §6 M2), which must never record a mutation as applied when it
        actually failed. Each returned item carries `entity_id`, `name`,
        `kind_code` (glossary-service's `entityResult`) so the caller can
        correlate back to its own request items without relying on
        response order."""
        if not entities:
            return []
        url = f"{self._base_url}/internal/books/{book_id}/extract-entities"
        actions: dict[str, dict[str, str]] = {}
        for e in entities:
            kc = e.get("kind_code") or "character"
            for ac in (e.get("attributes") or {}):
                actions.setdefault(kc, {})[ac] = "fill"
        payload: dict[str, Any] = {
            "source_language": source_language,
            "default_tags": ["ai-suggested"],
            "entities": [
                {"kind_code": e.get("kind_code") or "character", "name": e["name"],
                 "attributes": e.get("attributes") or {}}
                for e in entities if e.get("name")
            ],
        }
        if actions:
            payload["attribute_actions"] = actions
        try:
            resp = await self._http.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise GlossaryClientError(502, "GLOSSARY_SERVICE_UNAVAILABLE", str(exc)) from exc
        if not (200 <= resp.status_code < 300):
            code: str | None = None
            detail: str | None = None
            try:
                body = resp.json()
                code = body.get("error") or body.get("code")
                detail = body.get("message") or body.get("detail")
            except (ValueError, AttributeError):
                pass
            raise GlossaryClientError(resp.status_code, code, detail)
        return resp.json().get("entities", [])

    async def seed_entities(
        self, book_id: UUID, *, source_language: str, entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Bulk create/upsert glossary entities via the canonical write-through
        (`extract-entities`, the same path extraction uses). `entities` =
        [{kind_code, name, attributes?}] where `attributes` = {attr_code: value} (mapped
        to the kind's registered attr_defs; an UNMATCHED code is silently no-op'd by the
        glossary). An unknown kind is PARKED (the entity is still created), so a
        planning-time cast seed always lands. Returns the created entities (each with
        `entity_id`), or [] on failure.

        D-PLAN-CAST-ATTRS: `attribute_actions` (auto-built as `fill` for every attr code
        sent) declares the write so the glossary persists the cast's DEPTH (role,
        personality, relationships, description) — not just the name."""
        if not entities:
            return []
        url = f"{self._base_url}/internal/books/{book_id}/extract-entities"
        actions: dict[str, dict[str, str]] = {}
        for e in entities:
            kc = e.get("kind_code") or "character"
            for ac in (e.get("attributes") or {}):
                actions.setdefault(kc, {})[ac] = "fill"
        payload: dict[str, Any] = {
            "source_language": source_language,
            "default_tags": ["ai-suggested"],
            "entities": [
                {"kind_code": e.get("kind_code") or "character", "name": e["name"],
                 "attributes": e.get("attributes") or {}}
                for e in entities if e.get("name")
            ],
        }
        if actions:
            payload["attribute_actions"] = actions
        try:
            resp = await self._http.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("glossary seed-entities → %d", resp.status_code)
                return []
            return resp.json().get("entities", [])
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("glossary seed-entities unavailable: %s", exc)
            return []


def init_glossary_client() -> GlossaryClient:
    global _client
    if _client is None:
        _client = GlossaryClient(settings.glossary_internal_url, settings.internal_service_token)
    return _client


def get_glossary_client() -> GlossaryClient:
    return _client or init_glossary_client()


async def close_glossary_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
