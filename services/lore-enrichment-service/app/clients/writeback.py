"""C13 — cross-service WRITE ports for the H0 write-back / promote / retract path.

These are the only places lore-enrichment-service issues writes to other
services. They honour the locked invariants:

  * **Q2 (glossary SSOT):** the entity anchor is written through glossary
    ``POST /internal/books/{book_id}/extract-entities``. Enriched dimension
    *facts* (which extract-entities cannot tag with a source_type) are admitted
    to the KG QUARANTINED via knowledge-service
    ``/internal/knowledge/enriched-writeback`` — a NON-canonical write, so Q2's
    "no direct canonical Neo4j write" is not breached.
  * **H0 (enriched ≠ canon):** write-back leaves facts ``source_type='enriched'``
    + ``pending_validation=true`` + ``confidence<1.0``; only :meth:`promote`
    canonizes them while RETAINING the permanent origin marker; :meth:`retract`
    soft-deletes (reversible) the glossary anchor (recycle-bin, M6) and the KG
    facts.
  * **Promotion authority:** :meth:`book_owner` reads the book-service projection
    (the TRUTH source) — promotion authorization never trusts a client-supplied
    user id.
  * **Defense-in-depth (deferred 050):** all proposal/LLM text is treated as
    DATA — every name/dimension/content value is injection-neutralized before it
    crosses a service boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from app.verify.sanitize import neutralize_proposal_text

__all__ = [
    "WritebackError",
    "WrittenFact",
    "BookOwner",
    "WritebackPorts",
]


class WritebackError(Exception):
    """A cross-service write failed. ``retryable`` distinguishes transient
    (timeout / 502 / 503 / 429) from a hard contract failure."""

    def __init__(
        self, message: str, *, retryable: bool = False, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class WrittenFact:
    """One enriched fact admitted to the KG (the response of write-back)."""

    fact_id: str
    edge_id: str
    dimension: str
    source_type: str
    confidence: float
    pending_validation: bool


@dataclass(frozen=True)
class BookOwner:
    book_id: UUID
    owner_user_id: UUID


def _safe(text: str | None) -> str:
    """Neutralize injection in untrusted proposal/LLM text before it crosses a
    service boundary (deferred 050 — treat enriched text as DATA, never
    instructions)."""
    safe, _hits = neutralize_proposal_text(text or "")
    return safe


class WritebackPorts:
    """All cross-service writes for the C13 write-back boundary, one client."""

    def __init__(
        self,
        *,
        glossary_base_url: str,
        knowledge_base_url: str,
        book_base_url: str,
        internal_token: str,
        timeout_s: float = 15.0,
    ) -> None:
        self._gloss = glossary_base_url.rstrip("/")
        self._know = knowledge_base_url.rstrip("/")
        self._book = book_base_url.rstrip("/")
        self._token = internal_token
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0))

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self._token}

    # ── book-service ownership (promotion-authority TRUTH source) ──────────────

    async def book_owner(self, *, book_id: UUID) -> BookOwner:
        """Read the book's owner from the book-service projection.

        This is the authoritative answer to "who is the author" — promotion
        authorization is decided against THIS, never against a client claim.
        """
        url = f"{self._book}/internal/books/{book_id}/projection"
        resp = await self._get(url)
        data = resp.json()
        owner = data.get("owner_user_id")
        if not owner:
            raise WritebackError(
                f"book {book_id} projection missing owner_user_id", status_code=502
            )
        return BookOwner(book_id=book_id, owner_user_id=UUID(str(owner)))

    # ── glossary SSOT write (Q2 — the entity anchor) ───────────────────────────

    async def write_entity_through_glossary(
        self,
        *,
        book_id: UUID,
        kind_code: str,
        name: str,
        attributes: dict[str, str],
        source_language: str = "zh",
    ) -> str:
        """Upsert the entity ANCHOR through the glossary SSOT (Q2).

        Returns the glossary ``entity_id``. This writes the entity IDENTITY
        (``name`` + any caller-supplied EAV attributes) via ``extract-entities``;
        the write-back path supplies ``attributes={}`` so the anchor is created
        identity-only (quarantine — H0 A1). The CANONICAL content
        (``short_description``) is written separately on PROMOTE via
        :meth:`set_glossary_canon_content`, because ``short_description`` is a
        glossary_entities COLUMN that ``extract-entities`` cannot set. All text
        is injection-neutralized first (deferred 050).
        """
        safe_attrs = {k: _safe(v) for k, v in attributes.items()}
        body: dict[str, Any] = {
            # de-bias C1 (#7): the book's language, not hardcoded zh (identity-only
            # anchor write, but the source_language should still match the book).
            "source_language": source_language or "zh",
            "attribute_actions": {
                kind_code: {code: "fill" for code in safe_attrs}
            },
            "entities": [
                {
                    "kind_code": kind_code,
                    "name": _safe(name),
                    "attributes": safe_attrs,
                    "evidence": "",
                    "chapter_links": [],
                }
            ],
        }
        url = f"{self._gloss}/internal/books/{book_id}/extract-entities"
        resp = await self._post(url, json=body)
        data = resp.json()
        ents = data.get("entities") or []
        if not ents or not ents[0].get("entity_id"):
            raise WritebackError(
                "glossary extract-entities returned no entity_id", status_code=502
            )
        return str(ents[0]["entity_id"])

    # ── knowledge-service KG quarantine write (the H0 carrier) ─────────────────

    async def writeback_enriched_facts(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None,
        proposal_id: UUID,
        glossary_entity_id: UUID,
        canonical_name: str,
        entity_kind: str,
        technique: str,
        facts: list[dict[str, Any]],
    ) -> list[WrittenFact]:
        """Admit the proposal's facts to the KG QUARANTINED (source_type=
        'enriched:<technique>', pending=true, confidence<1.0). Idempotent."""
        body = {
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id else None,
            "proposal_id": str(proposal_id),
            "glossary_entity_id": str(glossary_entity_id),
            "canonical_name": _safe(canonical_name),
            "entity_kind": entity_kind,
            "technique": technique,
            "facts": [
                {
                    "dimension": _safe(f["dimension"]),
                    "content": _safe(f["content"]),
                    "confidence": float(f["confidence"]),
                }
                for f in facts
            ],
        }
        url = f"{self._know}/internal/knowledge/enriched-writeback"
        resp = await self._post(url, json=body)
        data = resp.json()
        return [
            WrittenFact(
                fact_id=str(r["fact_id"]),
                edge_id=str(r["edge_id"]),
                dimension=str(r["dimension"]),
                source_type=str(r["source_type"]),
                confidence=float(r["confidence"]),
                pending_validation=bool(r["pending_validation"]),
            )
            for r in (data.get("facts") or [])
        ]

    async def promote_enriched_facts(
        self,
        *,
        user_id: UUID,
        proposal_id: UUID,
        promoted_by: UUID,
        promoted_at: datetime | None = None,
    ) -> int:
        """Flip this proposal's KG facts to canon (source_type='glossary',
        conf=1.0, pending=false) RETAINING the permanent origin marker."""
        ts = (promoted_at or datetime.now(timezone.utc)).isoformat()
        body = {
            "user_id": str(user_id),
            "proposal_id": str(proposal_id),
            "promoted_by": str(promoted_by),
            "promoted_at": ts,
        }
        url = f"{self._know}/internal/knowledge/enriched-promote"
        resp = await self._post(url, json=body)
        return int(resp.json().get("affected", 0))

    async def retract_enriched_facts(
        self, *, user_id: UUID, proposal_id: UUID
    ) -> int:
        """Soft-retract this proposal's KG facts (set valid_until; reversible)."""
        body = {"user_id": str(user_id), "proposal_id": str(proposal_id)}
        url = f"{self._know}/internal/knowledge/enriched-retract"
        resp = await self._post(url, json=body)
        return int(resp.json().get("affected", 0))

    # ── glossary enrichment SUPPLEMENT (B1 — the distinguished `dị bản`) ─────────

    async def upsert_enrichment_supplement(
        self,
        *,
        book_id: UUID,
        entity_id: UUID,
        proposal_id: UUID,
        technique: str,
        review_status: str,
        facts: list[dict[str, Any]],
        promoted_by: UUID | None = None,
        promoted_at: datetime | None = None,
    ) -> int:
        """Upsert this proposal's enrichment SUPPLEMENT rows on the canonical
        glossary entity (PO ruling B1 / F-C13-2).

        The supplement is a DISTINGUISHED variant (`dị bản`) of the original
        canon — written to its own ``entity_enrichments`` table, FK→the canonical
        entity, NEVER onto the entity's ``short_description`` (which stays
        original-authored canon). On write-back the rows are ``proposed``; on
        promote they are ``promoted`` with the permanent markers. The glossary
        endpoint forces ``origin='enrichment'`` and rejects canon confidence, so
        a supplement row can never masquerade as canon (H0).

        Idempotent: the endpoint upserts ON CONFLICT (entity, dimension,
        proposal_id), so a re-promote / re-write-back is safe. Returns the number
        of rows written. Internal-token (no user JWT). All text is
        injection-neutralized first (deferred 050)."""
        body: dict[str, Any] = {
            "proposal_id": str(proposal_id),
            "technique": technique,
            "review_status": review_status,
            "facts": [
                {
                    "dimension": _safe(f["dimension"]),
                    "content": _safe(f["content"]),
                    "confidence": float(f["confidence"]),
                }
                for f in facts
            ],
        }
        if promoted_by is not None:
            body["promoted_by"] = str(promoted_by)
            body["promoted_at"] = (
                promoted_at or datetime.now(timezone.utc)
            ).isoformat()
        url = f"{self._gloss}/internal/books/{book_id}/entities/{entity_id}/enrichments"
        resp = await self._post(url, json=body)
        return int(resp.json().get("written", 0))

    async def delete_enrichment_supplement(
        self, *, book_id: UUID, entity_id: UUID, proposal_id: UUID
    ) -> int:
        """Soft-delete a proposal's enrichment supplement rows via the INTERNAL
        token (the F-C13-1 fix).

        Retract un-canonizes the enrichment exactly the way promote canonized it
        — over the service-to-service internal token, with NO dependency on a
        user JWT (the old user-scoped recycle was structurally unreachable from
        the handler — F-C13-1). The canonical entity and its original canon are
        never touched; only the supplement rows get ``deleted_at``. Idempotent:
        a missing/already-retracted proposal returns ``soft_deleted=0``. Returns
        the soft-deleted row count."""
        url = f"{self._gloss}/internal/books/{book_id}/entities/{entity_id}/enrichments"
        try:
            resp = await self._http.delete(
                url, headers=self._headers, params={"proposal_id": str(proposal_id)}
            )
        except httpx.TimeoutException as exc:
            raise WritebackError(f"timeout deleting {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise WritebackError(f"connection error deleting {url}: {exc}", retryable=True)
        checked = self._check(resp, url)
        return int(checked.json().get("soft_deleted", 0))

    # ── transport ──────────────────────────────────────────────────────────────

    async def _post(self, url: str, *, json: dict[str, Any]) -> httpx.Response:
        try:
            resp = await self._http.post(url, headers=self._headers, json=json)
        except httpx.TimeoutException as exc:
            raise WritebackError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise WritebackError(f"connection error calling {url}: {exc}", retryable=True)
        return self._check(resp, url)

    async def _get(self, url: str) -> httpx.Response:
        try:
            resp = await self._http.get(url, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise WritebackError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise WritebackError(f"connection error calling {url}: {exc}", retryable=True)
        return self._check(resp, url)

    @staticmethod
    def _check(resp: httpx.Response, url: str) -> httpx.Response:
        if resp.status_code == 200:
            return resp
        retryable = resp.status_code in (502, 503, 429)
        raise WritebackError(
            f"{resp.request.method} {url} failed ({resp.status_code})",
            retryable=retryable,
            status_code=resp.status_code,
        )
