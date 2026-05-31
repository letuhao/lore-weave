"""C1 DPS-B — read-only glossary client.

Reads entities + wiki for a book scope. WRITES NOTHING (Q2 LOCKED — enrichment
write-back is via glossary `extract-entities` SSOT in C11/C13, never here).

Scoping note (H2 finding, recorded in docs/raid/findings/C1-verifies.md):
glossary entities are keyed on `book_id` (table `glossary_entities`), NOT on a
`project_id`. The (user, project) scoping that knowledge-service uses bridges to
glossary via `book_id`. This client therefore scopes reads by `book_id`; the
`/internal/*` path is server-to-server (X-Internal-Token) and the `/v1/glossary`
path is user-scoped (JWT pass-through, ownership enforced upstream).

All entity/wiki text is passed through `neutralize_injection` (M4) on the way in
and is UTF-8/CJK-safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from app.clients.sanitize import neutralize_injection

__all__ = [
    "GlossaryEntity",
    "EntityCoverageRow",
    "WikiArticle",
    "GlossaryServiceError",
    "GlossaryClient",
]


class GlossaryServiceError(Exception):
    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class GlossaryEntity:
    entity_id: str
    name: str = ""
    kind: str = ""
    description: str = ""


@dataclass(frozen=True)
class EntityCoverageRow:
    """One entity's enrichment coverage (D1 gap-auto-detect input): the PROMOTED
    enrichment dimensions it already has + its mention_count (C6 ranking signal)."""

    entity_id: str
    canonical_name: str
    kind: str
    mention_count: int
    dimensions: tuple[str, ...]  # promoted-enrichment dimensions already present


@dataclass(frozen=True)
class WikiArticle:
    article_id: str
    title: str = ""
    body: str = ""


class GlossaryClient:
    def __init__(
        self,
        *,
        base_url: str,
        internal_token: str,
        timeout_s: float = 10.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0))

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── internal entity read (X-Internal-Token, book-scoped) ─────────────────

    async def list_entities(self, *, book_id: UUID, limit: int = 100) -> list[GlossaryEntity]:
        url = f"{self._base}/internal/books/{book_id}/entities"
        resp = await self._get(
            url,
            headers={"X-Internal-Token": self._internal_token},
            params={"limit": str(limit)},
        )
        rows = _as_rows(resp.json())
        return [
            GlossaryEntity(
                entity_id=str(r.get("id") or r.get("entity_id") or ""),
                name=neutralize_injection(r.get("name") or r.get("canonical_name")),
                kind=str(r.get("kind") or r.get("kind_name") or ""),
                description=neutralize_injection(r.get("description")),
            )
            for r in rows
        ]

    async def list_enrichment_coverage(
        self, *, book_id: UUID, limit: int = 200
    ) -> list[EntityCoverageRow]:
        """Read per-entity enrichment coverage for gap-auto-detection (D1).

        Returns each entity's canonical name, kind, mention_count, and the
        PROMOTED enrichment dimensions it already has. The caller builds
        EntityCoverage from this (present_dimensions = these dims) and runs the
        C7 gap engine. Internal-token, book-scoped."""
        url = f"{self._base}/internal/books/{book_id}/enrichment-coverage"
        resp = await self._get(
            url,
            headers={"X-Internal-Token": self._internal_token},
            params={"limit": str(limit)},
        )
        rows = _as_rows(resp.json())
        out: list[EntityCoverageRow] = []
        for r in rows:
            dims = r.get("dimensions") or []
            out.append(
                EntityCoverageRow(
                    entity_id=str(r.get("entity_id") or r.get("id") or ""),
                    canonical_name=neutralize_injection(r.get("canonical_name") or r.get("name")),
                    kind=str(r.get("kind") or "location"),
                    mention_count=int(r.get("mention_count") or 0),
                    dimensions=tuple(
                        neutralize_injection(d) for d in dims if isinstance(d, str)
                    ),
                )
            )
        return out

    # ── user-scoped wiki read (JWT pass-through) ─────────────────────────────

    async def list_wiki(self, *, jwt: str, book_id: UUID) -> list[WikiArticle]:
        url = f"{self._base}/v1/glossary/books/{book_id}/wiki"
        resp = await self._get(url, headers={"Authorization": f"Bearer {jwt}"})
        rows = _as_rows(resp.json())
        return [
            WikiArticle(
                article_id=str(r.get("id") or r.get("article_id") or ""),
                title=neutralize_injection(r.get("title")),
                body=neutralize_injection(r.get("body") or r.get("content")),
            )
            for r in rows
        ]

    # ── transport ────────────────────────────────────────────────────────────

    async def _get(
        self, url: str, *, headers: dict[str, str], params: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            resp = await self._http.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise GlossaryServiceError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise GlossaryServiceError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code == 200:
            return resp
        retryable = resp.status_code in (502, 503, 429)
        raise GlossaryServiceError(
            f"GET {url} failed ({resp.status_code})",
            retryable=retryable,
            status_code=resp.status_code,
        )


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    """Glossary list endpoints may return a bare list OR an envelope
    ({"entities": [...]} / {"items": [...]} / {"articles": [...]}). Normalize."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("entities", "items", "articles", "data", "results"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []
