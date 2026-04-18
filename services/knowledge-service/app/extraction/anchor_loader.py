"""K13.0 — Pass 0 glossary anchor pre-loader.

Before an extraction job runs, load active glossary entries for the
target book and install them as canonical :Entity nodes in Neo4j
with `anchor_score=1.0`. Returns an in-memory `Anchor[]` index the
resolver can use to bias fuzzy matching toward existing anchors
instead of minting duplicate nodes.

This module is a thin orchestrator over two already-shipped primitives:
  - GlossaryClient.list_entities(book_id, status_filter)   (K11.10)
  - entities.upsert_glossary_anchor(session, ...)          (K11.5a)

Idempotency is inherited from upsert_glossary_anchor's MERGE-based
Cypher; re-running against the same book creates zero new nodes.

Reference: KSA §3.4.E (two-layer anchoring), §6.0.3 (resolver),
research basis arXiv:2404.16130 (GraphRAG), arXiv:2405.14831
(HippoRAG).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.clients.glossary_client import GlossaryClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import upsert_glossary_anchor

logger = logging.getLogger(__name__)

__all__ = ["Anchor", "load_glossary_anchors"]


@dataclass(frozen=True)
class Anchor:
    """Lightweight mirror of an upserted glossary-anchored :Entity.

    Returned by `load_glossary_anchors` so the resolver can build a
    name/alias → canonical_id index without re-querying Neo4j.
    """

    canonical_id: str
    glossary_entity_id: str
    name: str
    kind: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


async def load_glossary_anchors(
    session: CypherSession,
    glossary_client: GlossaryClient,
    *,
    user_id: str,
    project_id: str,
    book_id: UUID,
    status_filter: str = "active",
) -> list[Anchor]:
    """Upsert active glossary entries for `book_id` as canonical anchors.

    Degradation model:
      - glossary_client returns None (circuit open / HTTP error) → log
        at WARNING and return []. Extraction should still run without
        anchors rather than abort.
      - Empty list from glossary → return []. Normal state for a fresh
        book with no curated entries yet.
      - Per-entry upsert failure (bad data, driver hiccup) → log
        exception and skip that entry so one bad row doesn't poison
        the whole pre-load.

    Entries missing `entity_id` or `name` are skipped — they're
    unusable for anchoring.
    """
    raw = await glossary_client.list_entities(
        book_id, status_filter=status_filter,
    )
    if raw is None:
        logger.warning(
            "K13.0: glossary list_entities failed for book=%s — "
            "skipping anchor pre-load (extractor will mint-on-no-match)",
            book_id,
        )
        return []

    anchors: list[Anchor] = []
    skipped_invalid = 0
    skipped_error = 0
    for entry in raw:
        entity_id = entry.get("entity_id")
        name = entry.get("name")
        if not entity_id or not name:
            skipped_invalid += 1
            continue

        kind = entry.get("kind_code") or "unknown"
        aliases = entry.get("aliases") or []

        try:
            entity = await upsert_glossary_anchor(
                session,
                user_id=user_id,
                project_id=project_id,
                glossary_entity_id=str(entity_id),
                name=name,
                kind=kind,
                aliases=list(aliases),
            )
        except Exception:
            logger.exception(
                "K13.0: upsert_glossary_anchor failed for entry=%s", entity_id,
            )
            skipped_error += 1
            continue

        anchors.append(
            Anchor(
                canonical_id=entity.id,
                glossary_entity_id=entity.glossary_entity_id or str(entity_id),
                name=entity.name,
                kind=entity.kind,
                aliases=tuple(entity.aliases or ()),
            )
        )

    logger.info(
        "K13.0: anchor pre-load complete — book=%s project=%s "
        "loaded=%d invalid=%d errors=%d",
        book_id, project_id, len(anchors), skipped_invalid, skipped_error,
    )
    return anchors
