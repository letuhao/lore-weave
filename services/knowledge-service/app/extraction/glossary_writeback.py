"""KG→glossary writeback (mui #1).

Propose discovered, unanchored, sufficiently-confident entities back to the
glossary SSOT as reviewable drafts (status='draft', tag 'ai-suggested'). The
human reviews/promotes in the glossary AI-suggestions inbox; promotion closes
the loop (glossary.entity_updated → KG MERGE sets glossary_entity_id).

Best-effort by contract: a failure here must never block extraction — the
canon writes (Neo4j + Postgres) have already committed, and the next job
re-proposes (glossary dedups by name + the ai-rejected tombstone, so
re-proposal is safe/idempotent). Default OFF; enabled per-env.

Quality gate (SP1, the only one pre-K18 validator): mention_count floor (in
find_gap_candidates' Cypher) + confidence floor (applied here). Values are
config, not hardcoded — see ADJ-1 (PO 2026-06-06): start mention>=10 & conf>=0.7.

Architecture: docs/03_planning/GLOSSARY_AI_PIPELINE_V2_ARCHITECTURE.md
Spec:         docs/specs/2026-06-06-glossary-kg-writeback.md
"""
from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import TypedDict

from app.clients.glossary_client import GlossaryClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import Entity, find_gap_candidates
from app.extraction.entity_resolver import normalize_kind_for_anchor_lookup

logger = logging.getLogger(__name__)

# Tag stamped on every entity created by this loop. Mirrors the glossary
# constant `tagAISuggested`; the FE lists ?status=draft&tags=ai-suggested.
WRITEBACK_TAG = "ai-suggested"


class WritebackConfig(TypedDict):
    enabled: bool
    min_mentions: int
    confidence_floor: float
    limit: int


def _load_writeback_config() -> WritebackConfig:
    """Read the KG→glossary writeback env config. Default: disabled.

    Envs (all optional):
        KNOWLEDGE_GLOSSARY_WRITEBACK_ENABLED: "true"/"1"/"yes"/"on" enables.
        KNOWLEDGE_GLOSSARY_WRITEBACK_MIN_MENTIONS: int floor (default 10).
        KNOWLEDGE_GLOSSARY_WRITEBACK_CONFIDENCE_FLOOR: float (default 0.7).
        KNOWLEDGE_GLOSSARY_WRITEBACK_LIMIT: int cap per job (default 100).
    """
    enabled = os.environ.get(
        "KNOWLEDGE_GLOSSARY_WRITEBACK_ENABLED", "false"
    ).strip().lower() in ("true", "1", "yes", "on")

    def _int(env: str, default: int) -> int:
        try:
            return int(os.environ.get(env, "").strip() or default)
        except ValueError:
            return default

    def _float(env: str, default: float) -> float:
        try:
            return float(os.environ.get(env, "").strip() or default)
        except ValueError:
            return default

    return {
        "enabled": enabled,
        "min_mentions": max(0, _int("KNOWLEDGE_GLOSSARY_WRITEBACK_MIN_MENTIONS", 10)),
        "confidence_floor": _float("KNOWLEDGE_GLOSSARY_WRITEBACK_CONFIDENCE_FLOOR", 0.7),
        "limit": max(1, _int("KNOWLEDGE_GLOSSARY_WRITEBACK_LIMIT", 100)),
    }


WRITEBACK_CONFIG: WritebackConfig = _load_writeback_config()


def build_writeback_entities(
    candidates: Sequence[Entity], *, confidence_floor: float
) -> list[dict]:
    """Filter discovered entities by confidence and map them to the glossary
    `extractedEntity` payload shape.

    mention_count is already floored by find_gap_candidates' Cypher; the
    confidence floor has no Cypher equivalent, so it is applied here. The
    extractor `kind` is normalised to a glossary kind_code (person→character,
    place→location, …); a glossary-aligned kind passes through unchanged.
    """
    entities: list[dict] = []
    for c in candidates:
        if c.confidence < confidence_floor:
            continue
        attributes: dict = {}
        # alias variants the extractor folded onto this entity; drop the
        # canonical name itself to avoid a redundant alias row.
        aliases = [a for a in c.aliases if a and a != c.canonical_name]
        if aliases:
            attributes["aliases"] = aliases
        entities.append(
            {
                "kind_code": normalize_kind_for_anchor_lookup(c.kind),
                "name": c.canonical_name,
                "attributes": attributes,
            }
        )
    return entities


async def writeback_discovered_entities(
    session: CypherSession,
    glossary_client: GlossaryClient,
    *,
    user_id: str,
    project_id: str,
    book_id: object,
    config: WritebackConfig = WRITEBACK_CONFIG,
) -> int:
    """Propose discovered-but-unanchored entities to glossary as ai-suggested
    drafts. Returns the count proposed (0 if none). Caller wraps best-effort.
    """
    candidates = await find_gap_candidates(
        session,
        user_id=user_id,
        project_id=project_id,
        min_mentions=config["min_mentions"],
        limit=config["limit"],
    )
    entities = build_writeback_entities(
        candidates, confidence_floor=config["confidence_floor"]
    )
    if not entities:
        return 0
    await glossary_client.propose_entities(
        book_id,
        entities=entities,
        default_tags=[WRITEBACK_TAG],
        park_unknown_kinds=False,
    )
    return len(entities)
