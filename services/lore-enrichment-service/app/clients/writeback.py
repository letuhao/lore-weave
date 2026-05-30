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
            "source_language": "zh",
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

    async def get_glossary_canon_content(
        self,
        *,
        book_id: UUID,
        entity_id: UUID,
    ) -> str | None:
        """Read the current canonical ``short_description`` of a glossary entity.

        Used by the promote self-heal (WARN-1): the idempotent re-promote branch
        reads this to decide whether a prior step-5 canon-content write actually
        landed. ``None``/empty means it did NOT (or the entity is missing) → the
        caller re-writes the canon content.

        Returns the current ``short_description`` string, or ``None`` when the
        column is NULL / the entity is not found (404). Network/contract errors
        propagate as :class:`WritebackError` so the self-heal can log + leave the
        re-promote retry surface intact.
        """
        url = f"{self._gloss}/internal/books/{book_id}/entities/{entity_id}/canon-content"
        try:
            resp = await self._http.get(url, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise WritebackError(f"timeout calling {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise WritebackError(f"connection error calling {url}: {exc}", retryable=True)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            retryable = resp.status_code in (502, 503, 429)
            raise WritebackError(
                f"GET {url} failed ({resp.status_code})",
                retryable=retryable,
                status_code=resp.status_code,
            )
        sd = resp.json().get("short_description")
        return str(sd) if sd is not None else None

    async def set_glossary_canon_content(
        self,
        *,
        book_id: UUID,
        entity_id: UUID,
        short_description: str,
    ) -> None:
        """Write the approved enriched content onto an EXISTING glossary
        entity's CANONICAL content (Q2 / DEFERRED-053).

        This is the glossary SSOT write the promote flow performs to set the
        entity's canonical ``short_description`` — the value glossary_sync (C4)
        then propagates to Neo4j as ``source_type='glossary'`` canon. Used
        instead of ``extract-entities`` for content, because ``short_description``
        is a glossary_entities COLUMN (not an EAV attribute_definition), so
        ``extract-entities`` silently no-ops on it.

        H0: only called on PROMOTE (after the author-only ownership check), never
        pre-promote — the anchor stays identity-only / quarantined until then.
        The content is injection-neutralized first (deferred 050). Capped at the
        glossary-side 500-rune limit defensively (the endpoint also enforces it).
        """
        safe = _safe(short_description)
        if len(safe) > 500:
            safe = safe[:500]
        url = f"{self._gloss}/internal/books/{book_id}/entities/{entity_id}/canon-content"
        await self._post(url, json={"short_description": safe})

    async def soft_delete_glossary_entity(
        self, *, book_id: UUID, entity_id: UUID, jwt: str
    ) -> bool:
        """Route a promoted/quarantined glossary entity to the recycle-bin (M6).

        Uses the user-scoped glossary DELETE (soft-delete → ``deleted_at``),
        reversible via the recycle-bin restore. Returns True on success/no-op.
        """
        url = f"{self._gloss}/v1/glossary/books/{book_id}/entities/{entity_id}"
        try:
            resp = await self._http.delete(
                url, headers={"Authorization": f"Bearer {jwt}"}
            )
        except httpx.TimeoutException as exc:
            raise WritebackError(f"timeout deleting {url}: {exc}", retryable=True)
        except httpx.HTTPError as exc:
            raise WritebackError(f"connection error deleting {url}: {exc}", retryable=True)
        # 204 (deleted) / 200 / 404 (already gone) are all acceptable for a
        # reversible retraction — the end state is "not in the active glossary".
        if resp.status_code in (200, 202, 204, 404):
            return True
        retryable = resp.status_code in (502, 503, 429)
        raise WritebackError(
            f"DELETE {url} failed ({resp.status_code})",
            retryable=retryable,
            status_code=resp.status_code,
        )

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
