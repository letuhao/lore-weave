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

from app.clients.kal import KalClient, KalServiceError
from app.clients.sanitize import neutralize_injection

__all__ = [
    "GlossaryEntity",
    "EntityCoverageRow",
    "WikiArticle",
    "GlossaryServiceError",
    "GlossaryClient",
]


# Safety cap on the field-map drain: 500 pages × ≤200/page = 100k entities, far past any real
# book's cast — bounds a pathological never-null cursor without truncating a real cast.
_MAX_FIELDMAP_PAGES = 500


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
        kal_base_url: str | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._internal_token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0))
        # X2 (INV-KAL): when a KAL base URL is configured, the full-book CAST
        # enumeration (`list_entities`' id+name set) is read through the KAL
        # roster — drained to completion — instead of this service's own glossary
        # `/internal/.../entities` page. The KAL roster is projection-restricted to
        # id+name by its FROZEN contract, so the legacy `kind`/`short_description`
        # fields (which live on glossary's entity-list projection, NOT on the new
        # `entity_facts` substrate the KAL's facts/canonical reads surface) are
        # merged in from the glossary entity-list — see `list_entities` below.
        self._kal: KalClient | None = (
            KalClient(base_url=kal_base_url, internal_token=internal_token, timeout_s=timeout_s)
            if kal_base_url
            else None
        )

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._kal is not None:
            await self._kal.aclose()

    # ── internal entity read (X-Internal-Token, book-scoped) ─────────────────

    async def list_entities(self, *, book_id: UUID, limit: int = 100) -> list[GlossaryEntity]:
        """Full-book cast read.

        INV-KAL (X2): when a KAL is configured, the COMPLETE id+name cast is read
        through the KAL `roster` endpoint, DRAINED to completion (the contract's
        bounded-per-page / complete-in-aggregate read) — this fixes the prior
        silent `limit`-truncation of the cast. The KAL roster is projection-
        restricted to id+name by its frozen contract; the legacy `kind` +
        authored `short_description` fields are NOT on the KAL roster (nor on the
        new `entity_facts` substrate the KAL's facts/canonical reads surface — that
        substrate is sparse on the current corpus, so reading description from it
        would NOT be behavior-preserving). They are merged from glossary's own
        entity-list projection, keyed by entity_id, preserving every field the
        consumers (canon contradiction check, grounding canon provider, intent
        resolver hint) read today.

        With no KAL configured, falls back to the direct glossary entity-list
        (unchanged legacy behavior)."""
        # Legacy projection: glossary's entity-list still owns the authored
        # `short_description` + `kind` (not yet exposed by the KAL roster). Read it
        # for the field map regardless; it is the kind/description source.
        rows = await self._list_entities_glossary(book_id=book_id, limit=limit)
        if self._kal is None:
            return rows

        # KAL roster = the authoritative, COMPLETE, drained id+name cast.
        try:
            roster = await self._kal.roster(book_id=book_id, limit=200)
        except KalServiceError as exc:
            # KAL read failure must surface as a glossary read failure so the
            # caller's existing degrade path (verify_degraded / empty grounding)
            # fires — never a silent false-green.
            raise GlossaryServiceError(
                str(exc), retryable=exc.retryable, status_code=exc.status_code
            )

        fields_by_id: dict[str, GlossaryEntity] = {r.entity_id: r for r in rows if r.entity_id}
        out: list[GlossaryEntity] = []
        for entry in roster:
            extra = fields_by_id.get(entry.entity_id)
            out.append(
                GlossaryEntity(
                    entity_id=entry.entity_id,
                    # Prefer the roster's name (the KAL-authoritative projection);
                    # fall back to the glossary-projection name for parity.
                    name=neutralize_injection(entry.name) or (extra.name if extra else ""),
                    kind=(extra.kind if extra else "") or entry.kind,
                    description=(extra.description if extra else ""),
                )
            )
        return out

    async def _list_entities_glossary(
        self, *, book_id: UUID, limit: int
    ) -> list[GlossaryEntity]:
        """Direct glossary entity-list read (the legacy projection carrying `kind` + authored
        `short_description`), DRAINED to completion via the keyset cursor.

        The endpoint is bounded-per-page (server clamps `limit` ≤ 200) + cursor-paginated, so a
        single page would only carry the FIRST ~100-200 entities' fields — leaving the tail of a
        large cast with empty `kind`/`description` (the silent-truncation gap that re-introduces
        the bug the roster drain fixed: complete cast, but incomplete fields). We follow
        `next_cursor` to completion so the field map covers the WHOLE cast. `limit` becomes the
        page size; a safety cap bounds a pathological never-null cursor."""
        url = f"{self._base}/internal/books/{book_id}/entities"
        page_size = max(1, min(limit, 200))
        out: list[GlossaryEntity] = []
        cursor: str | None = None
        for _ in range(_MAX_FIELDMAP_PAGES):
            params = {"limit": str(page_size)}
            if cursor:
                params["cursor"] = cursor
            resp = await self._get(
                url,
                headers={"X-Internal-Token": self._internal_token},
                params=params,
            )
            payload = resp.json()
            for r in _as_rows(payload):
                out.append(
                    GlossaryEntity(
                        entity_id=str(r.get("id") or r.get("entity_id") or ""),
                        name=neutralize_injection(r.get("name") or r.get("canonical_name")),
                        kind=str(r.get("kind") or r.get("kind_code") or r.get("kind_name") or ""),
                        # The internal entities endpoint returns the authored canon under
                        # `short_description` (the column, F-C12-1) — fall back to the legacy
                        # `description` key. The contradiction check reads this.
                        description=neutralize_injection(
                            r.get("short_description") or r.get("description")
                        ),
                    )
                )
            nxt = payload.get("next_cursor") if isinstance(payload, dict) else None
            # Stop at the end, or if the server echoes the same cursor (stuck) — no re-fetch loop.
            if not nxt or nxt == cursor:
                break
            cursor = nxt
        return out

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
