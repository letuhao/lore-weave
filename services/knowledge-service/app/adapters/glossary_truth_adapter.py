"""`TruthStore` over glossary-service's authored facts (plan T19).

Book-scoped truth: `entity_facts`, the bitemporal substrate Phase 1 taught to answer
`as_of`. It lives in another service, so this adapter is HTTP — reusing the glossary
client's existing internal-token plumbing rather than opening a second way to reach the
same service.

⚠️ **This is a NEW cross-service read for knowledge-service, and the reason it is allowed
here is worth stating.** INV-KAL says consumers reach glossary knowledge through the KAL.
knowledge-service cannot: the KAL (knowledge-gateway) calls knowledge-service, so routing
this through it would be a cycle. `scripts/knowledge-http-surface-gate.py` already exempts
`services/knowledge-service/` for that reason. Recorded because leaning on an exemption
without saying so is how an invariant quietly stops meaning anything.

**This adapter is temporary by design.** Phase 8 (T44–T46) merges the two truth stores —
the Go bitemporal machinery moves to Python and this HTTP hop disappears. Which is exactly
why consumers hold `ScopedTruthStore` and never this class: when the hop goes away, nothing
above the port changes.

⚠️ **Book truth is positioned on STORY ORDINALS.** A datetime `as_of` is rejected rather
than coerced — see the mirror-image check in `MemoryTruthAdapter`.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.ports.truth_store import TruthFact, TruthScope

logger = logging.getLogger(__name__)

__all__ = ["GlossaryTruthAdapter"]


class GlossaryTruthAdapter:
    """`http` is the shared internal client (`build_internal_client`) — the same one
    `GlossaryClient` holds, so the token, timeout and trace-id threading are configured in
    exactly one place."""

    def __init__(self, base_url: str, http: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http

    def _check(self, scope: TruthScope, as_of: int | datetime | None) -> None:
        if scope != "book":
            raise ValueError(
                f"GlossaryTruthAdapter serves book scope, not {scope!r} — "
                "project and global truth belong to MemoryTruthAdapter"
            )
        if isinstance(as_of, datetime):
            raise TypeError(
                "book truth is positioned on STORY ORDINALS; as_of must be an int chapter "
                f"position, got the datetime {as_of!r}. See T45."
            )

    async def facts_for_subject(
        self,
        *,
        scope: TruthScope,
        user_id: str,
        subject_id: str,
        book_id: str | None = None,
        project_id: str | None = None,
        as_of: int | datetime | None = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[TruthFact]:
        self._check(scope, as_of)
        if not book_id:
            raise ValueError("book-scoped truth requires a book_id")

        params: dict[str, object] = {}
        if as_of is not None:
            params["as_of"] = int(as_of)
        url = f"{self._base_url}/internal/books/{book_id}/entities/{subject_id}/facts"
        try:
            resp = await self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            # Degrade to empty rather than raising: truth is additive CONTEXT, and a
            # glossary blip must thin a prompt rather than fail the request that needed it.
            logger.warning("glossary truth unavailable for book %s: %s", book_id, exc)
            return []
        if resp.status_code != 200:
            logger.warning("glossary truth → %d for book %s", resp.status_code, book_id)
            return []
        try:
            items = resp.json().get("items", [])
        except (ValueError, AttributeError) as exc:
            logger.warning("glossary truth bad JSON for book %s: %s", book_id, exc)
            return []
        if not isinstance(items, list):
            logger.warning("glossary truth returned a non-list `items` for book %s", book_id)
            return []

        out = [
            TruthFact(
                fact_id=str(it.get("fact_id") or ""),
                subject_id=str(it.get("entity_id") or subject_id),
                # glossary calls it `attr_or_predicate`; the port calls it `attribute`. The
                # rename lives here so no consumer learns which store it came from.
                attribute=str(it.get("attr_or_predicate") or ""),
                value=str(it.get("value") or ""),
                scope="book",
                confidence=float(it.get("confidence") or 0.0),
                valid_from=it.get("valid_from_ordinal"),
                valid_to=it.get("valid_to_ordinal"),
                source_ref=it.get("source_episode_id"),
            )
            for it in items
            if isinstance(it, dict)
        ]
        if min_confidence > 0.0:
            # Filtered here because the glossary route has no confidence parameter. Doing
            # it after the fetch is honest about the cost: `limit` bounds the fetch, not
            # the filtered result.
            out = [f for f in out if f.confidence >= min_confidence]
        logger.debug(
            "truth facts_for_subject: backend=glossary as_of=%s hits=%d", as_of, len(out),
        )
        return out[:limit]

    async def search_facts(
        self,
        *,
        scope: TruthScope,
        user_id: str,
        query: str | None = None,
        book_id: str | None = None,
        project_id: str | None = None,
        as_of: int | datetime | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[TruthFact]:
        """NOT SUPPORTED, and it raises rather than returning `[]`.

        glossary exposes no free-text fact search — its fact routes are keyed by entity.
        Returning an empty list would be indistinguishable from "this book has no matching
        facts", so a caller would conclude the book is empty when the capability is simply
        absent. That is exactly the silent-success failure this repo keeps recording, so it
        fails loudly and names the alternative.
        """
        self._check(scope, as_of)
        raise NotImplementedError(
            "glossary exposes no free-text fact search; resolve the entity first and call "
            "facts_for_subject. (Phase 8 merges the stores and this gap closes with it.)"
        )
