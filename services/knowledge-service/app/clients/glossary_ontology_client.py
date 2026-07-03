"""K2b — KG-side client for glossary-service's internal ontology read (D1).

Reads the **node-kind source** the KG ontology resolver/adopt-gate anchors to.
Two variants (contract `_deps/glossary-ontology-read.yaml`):

  * ``GET /internal/books/{book_id}/ontology?user_id=`` — node-kinds defined
    for a specific book (project has ``book_id``).
  * ``GET /internal/users/{user_id}/glossary-standards`` — the user's
    system∪user standards (project has NO book; translation/code/general).

**Glossary lane LG is not built yet** (the authoritative `/internal` handler
lands on the glossary branch). So this module ships a `Protocol` + a
`FakeGlossaryOntologyClient` returning a configurable kind set, letting the
resolver and tests run end-to-end without glossary. The real
`HttpGlossaryOntologyClient` follows the existing house pattern (long-lived
`httpx.AsyncClient`, `X-Internal-Token` header, graceful degradation).

No provider SDK is imported (provider-gateway invariant); this is a plain
server-to-server read.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.5, D1.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol, runtime_checkable
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.logging_config import trace_id_var

__all__ = [
    "OntologyKind",
    "OntologyKinds",
    "GlossaryOntologyClient",
    "HttpGlossaryOntologyClient",
    "FakeGlossaryOntologyClient",
]

logger = logging.getLogger(__name__)


class OntologyKind(BaseModel):
    """One glossary node-kind (mirror of `_deps` `Kind`)."""

    model_config = ConfigDict(extra="ignore")

    code: str
    name: str = ""
    # which tier the kind resolved from (system|user|book); advisory only.
    tier: str | None = None
    # KG-ML M5 (C4) — localized kind labels {language: label}. Empty ⇒ the
    # consumer falls back to the canonical `name`. Surfaced by the glossary
    # internal ontology read; tier-resolved (a user/book label shadows System).
    name_i18n: dict[str, str] = Field(default_factory=dict)


class OntologyKinds(BaseModel):
    """Glossary ontology read result (mirror of `_deps` `OntologyKinds`)."""

    model_config = ConfigDict(extra="ignore")

    source: str | None = None  # "book" | "user_standards"
    book_id: str | None = None
    kinds: list[OntologyKind] = Field(default_factory=list)

    def codes(self) -> set[str]:
        """The set of kind codes — the only thing the resolver/adopt-gate need."""
        return {k.code for k in self.kinds}

    def kind_labels(self, language: str | None) -> dict[str, str]:
        """KG-ML M5 (C7) — ``{kind_code: localized label}`` for ``language``.

        Only kinds that carry a non-empty label in the requested language's
        primary subtag are included; the caller falls back to the canonical
        name (or the raw code) for any kind not in the map. Empty/blank
        ``language`` ⇒ empty map (no localization)."""
        lang = re.split(r"[-_]", str(language or "").strip().lower(), maxsplit=1)[0]
        if not lang:
            return {}
        out: dict[str, str] = {}
        for k in self.kinds:
            label = (k.name_i18n or {}).get(lang)
            if label:
                out[k.code] = label
        return out


@runtime_checkable
class GlossaryOntologyClient(Protocol):
    """The injectable seam the resolver depends on (lets tests/LG swap impls)."""

    async def get_book_ontology(self, book_id: UUID, user_id: UUID) -> OntologyKinds | None:
        """Book-tier node-kinds, or None on failure (resolver degrades)."""

    async def get_user_standards(self, user_id: UUID) -> OntologyKinds | None:
        """User system∪user standards node-kinds, or None on failure."""

    async def adopt_book_kinds(
        self, book_id: UUID, user_id: UUID, kinds: list[str]
    ) -> bool:
        """Idempotently copy the given System node-kind codes into the book tier.
        Returns True on success, False on failure. Used by KG schema-adopt to
        auto-seed the kinds a template requires (no more silent NEEDS_GLOSSARY)."""


class HttpGlossaryOntologyClient:
    """Live httpx client for the two glossary internal-ontology routes.

    Long-lived `AsyncClient` (one per process, pooled), `X-Internal-Token`
    baked into headers like the existing GlossaryClient/BookClient. Graceful:
    every failure path returns ``None`` and logs a warning — a missing glossary
    read must never crash adopt/resolve (the resolver treats None as "source
    unavailable" and reports the cross-check as inconclusive, never inventing
    kinds).
    """

    def __init__(self, base_url: str, internal_token: str, timeout_s: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_book_ontology(self, book_id: UUID, user_id: UUID) -> OntologyKinds | None:
        url = f"{self._base_url}/internal/books/{book_id}/ontology"
        return await self._get(url, params={"user_id": str(user_id)})

    async def get_user_standards(self, user_id: UUID) -> OntologyKinds | None:
        url = f"{self._base_url}/internal/users/{user_id}/glossary-standards"
        return await self._get(url, params=None)

    async def adopt_book_kinds(
        self, book_id: UUID, user_id: UUID, kinds: list[str]
    ) -> bool:
        url = f"{self._base_url}/internal/books/{book_id}/ontology/adopt-kinds"
        tid = trace_id_var.get()
        try:
            resp = await self._http.post(
                url,
                params={"user_id": str(user_id)},
                json={"kinds": kinds},
                headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning("glossary adopt-kinds %s returned %d", url, resp.status_code)
                return False
            return True
        except httpx.HTTPError as exc:
            logger.warning("glossary adopt-kinds failed (%s): %s", url, exc)
            return False

    async def _get(self, url: str, *, params: dict | None) -> OntologyKinds | None:
        tid = trace_id_var.get()
        try:
            resp = await self._http.get(
                url, params=params, headers={"X-Trace-Id": tid} if tid else None,
            )
            if resp.status_code != 200:
                logger.warning("glossary ontology %s returned %d", url, resp.status_code)
                return None
            return OntologyKinds.model_validate(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("glossary ontology read failed (%s): %s", url, exc)
            return None


class FakeGlossaryOntologyClient:
    """In-process stand-in for tests + the no-glossary dev path (LG not built).

    Configure with the kind codes each source should return:
      * ``book_kinds`` keyed by ``book_id`` (str) — book-tier ontology;
      * ``user_kinds`` keyed by ``user_id`` (str) — user-standards ontology.
    Unknown ids resolve to an empty kind set (the realistic "book has no
    ontology yet" case). Pass ``unavailable=True`` to simulate glossary down
    (every call returns None).
    """

    def __init__(
        self,
        *,
        book_kinds: dict[str, list[str]] | None = None,
        user_kinds: dict[str, list[str]] | None = None,
        unavailable: bool = False,
        kind_labels: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._book_kinds = book_kinds or {}
        self._user_kinds = user_kinds or {}
        self._unavailable = unavailable
        # KG-ML M5 (C7) — optional localized labels keyed by kind code →
        # {language: label}, applied to whichever tier emits that code.
        self._kind_labels = kind_labels or {}
        # adopt_book_kinds call log (book_id, user_id, kinds).
        self.adopt_calls: list[tuple[str, str, list[str]]] = []

    def _kind(self, code: str, tier: str) -> OntologyKind:
        return OntologyKind(
            code=code, name=code, tier=tier, name_i18n=self._kind_labels.get(code, {})
        )

    async def get_book_ontology(self, book_id: UUID, user_id: UUID) -> OntologyKinds | None:
        if self._unavailable:
            return None
        codes = self._book_kinds.get(str(book_id), [])
        return OntologyKinds(
            source="book",
            book_id=str(book_id),
            kinds=[self._kind(c, "book") for c in codes],
        )

    async def get_user_standards(self, user_id: UUID) -> OntologyKinds | None:
        if self._unavailable:
            return None
        codes = self._user_kinds.get(str(user_id), [])
        return OntologyKinds(
            source="user_standards",
            kinds=[self._kind(c, "user") for c in codes],
        )

    async def adopt_book_kinds(
        self, book_id: UUID, user_id: UUID, kinds: list[str]
    ) -> bool:
        """Mirror the real endpoint: copy-down from System/User for catalogue codes
        AND directly create any residual code as a book-tier kind — so EVERY
        requested code lands on the book's kind set (the schema is authoritative
        about what it needs). Records the call; a subsequent get_book_ontology
        reflects the new kinds (realistic retry). Returns False only when the
        glossary is unavailable (transport/outage)."""
        if self._unavailable:
            return False
        existing = list(self._book_kinds.get(str(book_id), []))
        for c in kinds:
            if c not in existing:
                existing.append(c)
        self._book_kinds[str(book_id)] = existing
        self.adopt_calls.append((str(book_id), str(user_id), list(kinds)))
        return True
