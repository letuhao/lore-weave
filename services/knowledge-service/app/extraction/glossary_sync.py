"""K15.11 — Glossary sync handler.

Merges a glossary entity into Neo4j as a high-confidence :Entity node.
User-curated glossary entities bypass quarantine (confidence=1.0,
source_type='glossary'). Called when:
  - A glossary.entity_updated event arrives (future K14 event pipeline)
  - Manual sync is triggered via an internal endpoint
  - Startup reconciler detects drift (K11.10)

The event subscriber wiring (K14) is deferred — this module provides
the sync logic as a callable function.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.canonical import canonicalize_entity_name, entity_canonical_id

__all__ = ["sync_glossary_entity_to_neo4j"]

logger = logging.getLogger(__name__)


async def sync_glossary_entity_to_neo4j(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    glossary_entity_id: str,
    name: str,
    kind: str,
    aliases: list[str] | None = None,
    short_description: str | None = None,
) -> dict[str, Any]:
    """Merge a glossary entity into Neo4j as a high-confidence node.

    Idempotent: uses MERGE on (user_id, glossary_entity_id). Creates
    the node if it doesn't exist, updates if it does. Glossary entities
    always have confidence=1.0 and source_type='glossary' — they are
    user-curated and bypass the quarantine pipeline.

    ON CREATE sets all fields including those from the standard Entity
    schema (id, canonical_version, source_types, anchor_score,
    evidence_count, mention_count, archived_at) for consistency with
    extraction-created entities.

    Returns a dict with the node id and whether it was created or updated.
    """
    canonical_name = canonicalize_entity_name(name)
    canonical_id = entity_canonical_id(user_id, project_id, name, kind)

    result = await session.run(
        """
        MERGE (e:Entity {user_id: $user_id, glossary_entity_id: $glossary_entity_id})
        ON CREATE SET
          e.id = $canonical_id,
          e.name = $name,
          e.canonical_name = $canonical_name,
          e.kind = $kind,
          e.aliases = $aliases,
          e.short_description = $short_description,
          e.project_id = $project_id,
          e.confidence = 1.0,
          e.source_type = 'glossary',
          e.source_types = ['glossary'],
          e.canonical_version = 1,
          e.anchor_score = 1.0,
          e.evidence_count = 0,
          e.mention_count = 0,
          e.archived_at = NULL,
          e.created_at = datetime(),
          e.updated_at = datetime()
        ON MATCH SET
          e.name = $name,
          e.canonical_name = $canonical_name,
          e.kind = $kind,
          e.aliases = $aliases,
          e.short_description = $short_description,
          e.confidence = 1.0,
          e.updated_at = datetime()
        RETURN e.glossary_entity_id AS id, e.created_at = e.updated_at AS created
        """,
        user_id=user_id,
        project_id=project_id or "global",
        glossary_entity_id=glossary_entity_id,
        canonical_id=canonical_id,
        name=name,
        canonical_name=canonical_name,
        kind=kind,
        aliases=aliases or [],
        short_description=short_description or "",
    )
    record = await result.single()
    created = record["created"] if record else False

    action = "created" if created else "updated"
    logger.info(
        "K15.11: glossary entity %s in Neo4j: %s (glossary_id=%s, name=%s)",
        action, glossary_entity_id, glossary_entity_id, name,
    )

    return {
        "glossary_entity_id": glossary_entity_id,
        "action": action,
        "canonical_name": canonical_name,
    }
