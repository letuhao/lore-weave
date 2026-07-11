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

from neo4j.exceptions import ConstraintError

from app.clients.glossary_client import GlossaryClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import (
    upsert_glossary_anchor,
    upsert_glossary_anchor_counted,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Anchor",
    "ProjectionResult",
    "load_glossary_anchors",
    "project_glossary_entities_to_nodes",
]


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
    status_filter: str | None = None,
) -> list[Anchor]:
    """Upsert glossary entries for `book_id` as canonical anchors.

    `status_filter` defaults to **None (no status filter)** — NOT "active". The
    handler historically ignored the `status` query param entirely, so every caller
    has always effectively received *all* statuses. Now that the param is honored
    (D-GLOSSARY-KNOWN-ENTITIES-STATUS-PARAM), defaulting to "active" here would have
    silently stopped anchoring draft entities and made extraction mint duplicates
    for them. Behavior is preserved; callers may now opt in to a real filter.

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
    # D-ANCHOR-PRELOAD-50-CAP: this used to call list_entities() with no `limit`,
    # inheriting the handler's silent default of 50 — so a book with 300 curated
    # entities pre-loaded only 50 anchors and let the extractor mint DUPLICATE
    # nodes for the other 250. Page the whole set instead.
    page = await glossary_client.list_all_entities(
        book_id, status_filter=status_filter,
    )
    if page is None:
        logger.warning(
            "K13.0: glossary list_all_entities failed for book=%s — "
            "skipping anchor pre-load (extractor will mint-on-no-match)",
            book_id,
        )
        return []
    raw, truncated = page
    if truncated:
        logger.warning(
            "K13.0: anchor pre-load read was TRUNCATED for book=%s (%d rows) — "
            "extraction may mint duplicates for the un-anchored remainder",
            book_id, len(raw),
        )

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


# ── WS-4B: kg_project_entities_to_nodes ────────────────────────────────


@dataclass(frozen=True)
class ProjectionResult:
    """Outcome of projecting glossary entities into graph nodes.

    `created` + `existing` are the nodes actually upserted (the
    `{nodes_created, nodes_existing}` the tool returns); `seen` is how many
    usable glossary rows were considered; `skipped` counts rows dropped as
    invalid (missing id/name) or on a per-row upsert error. `truncated` is True
    when the glossary read hit the server-side page cap, so the caller can tell
    the user that more entities remain (rather than silently under-projecting).
    """

    created: int = 0
    existing: int = 0
    seen: int = 0
    skipped: int = 0
    truncated: bool = False
    # Entities that could NOT be anchored because another node in the SAME
    # (user_id, project_id) already claims their `glossary_entity_id`. The Neo4j
    # constraint is `entity_glossary_fk_unique`, scoped per (user_id, project_id,
    # glossary_entity_id) — so a second knowledge project over the same book CAN now
    # anchor entities the first project already anchored (they carry a different
    # project_id). A conflict here therefore signals an unexpected duplicate WITHIN
    # one project, not the old cross-project clash. Counted separately from `skipped`
    # so the tool can explain a partial result instead of reporting "created N" as if
    # it were the whole glossary (was D-KG-GLOSSARY-FK-GLOBAL-UNIQUE, fixed 2026-07-10).
    conflicted: int = 0


async def project_glossary_entities_to_nodes(
    session: CypherSession,
    glossary_client: GlossaryClient,
    *,
    user_id: str,
    project_id: str,
    book_id: UUID,
    entity_ids: list[str] | None = None,
) -> ProjectionResult:
    """Deterministically project a book's glossary entities into the KG as
    canonical `:Entity` nodes (WS-4B / scenario S04 — "map how everything
    connects" from recorded lore, with no chapter prose).

    This is the tool-driven sibling of `load_glossary_anchors`: same
    idempotent `upsert_glossary_anchor` primitive, but it returns
    create-vs-existing counts and can target a SUBSET (`entity_ids`) or the
    whole active glossary (`entity_ids=None`).

    Degradation model mirrors `load_glossary_anchors`: a glossary read failure
    → return an all-zero result (the caller reports "nothing to project" rather
    than aborting); a per-row upsert error is logged and counted as skipped so
    one bad row can't poison the batch.
    """
    rows, truncated = await _load_projection_rows(glossary_client, book_id, entity_ids)
    created = existing = skipped = conflicted = 0
    for eid, name, kind, aliases in rows:
        try:
            _, was_created = await upsert_glossary_anchor_counted(
                session,
                user_id=user_id,
                project_id=project_id,
                glossary_entity_id=eid,
                name=name,
                kind=kind,
                aliases=aliases,
            )
        except ConstraintError:
            # `entity_glossary_fk_unique` is a per-(user_id, project_id,
            # glossary_entity_id) uniqueness constraint, so a conflict means another
            # node in THIS SAME project already claims this entity's FK — an
            # unexpected in-project duplicate (cross-project no longer clashes now that
            # the FK carries project_id). Counted separately so the caller can say WHY
            # the projection is partial rather than silently reporting a smaller
            # `nodes_created`.
            logger.warning(
                "WS-4B: entity=%s already anchored by another node in the same "
                "project=%s — cannot re-anchor (entity_glossary_fk_unique)",
                eid, project_id,
            )
            conflicted += 1
            continue
        except Exception:
            logger.exception(
                "WS-4B: project entity=%s failed for project=%s", eid, project_id,
            )
            skipped += 1
            continue
        if was_created:
            created += 1
        else:
            existing += 1

    logger.info(
        "WS-4B: projection complete — book=%s project=%s seen=%d created=%d "
        "existing=%d conflicted=%d skipped=%d truncated=%s",
        book_id, project_id, len(rows), created, existing, conflicted, skipped,
        truncated,
    )
    return ProjectionResult(
        created=created, existing=existing, seen=len(rows), skipped=skipped,
        truncated=truncated, conflicted=conflicted,
    )


async def _load_projection_rows(
    glossary_client: GlossaryClient,
    book_id: UUID,
    entity_ids: list[str] | None,
) -> tuple[list[tuple[str, str, str, list[str]]], bool]:
    """Normalize the two glossary read paths into `(entity_id, name, kind,
    aliases)` tuples plus a `truncated` flag. `entity_ids` given → fetch exactly
    those; else the whole glossary. Rows missing an id or name are dropped
    (unusable for a node).

    The whole-glossary read MUST override three `known-entities` handler defaults,
    or a prose-less book (WS-4B's whole point — scenario S04) projects NOTHING:
      * `min_frequency=0` — the default 2 requires ≥2 chapter-entity links; a book
        with no prose has none, so the default returns an empty list. (Even 1 would
        exclude an unlinked entity: the chapter join is a LEFT JOIN, COUNT=0.)
      * `include_dead=True` — the handler defaults to `alive=true`, and `alive` is a
        narrative dead/alive story flag, not a review status; a dead character is
        still a node whose connections we want.
      * paged reads (`list_all_entities`) — the handler's default limit is 50 and it
        caps at 500, so a larger glossary was silently truncated (D-ANCHOR-PRELOAD-50-CAP).
    """
    out: list[tuple[str, str, str, list[str]]] = []
    if entity_ids:
        ents = await glossary_client.fetch_entities_by_ids(
            book_id=book_id, entity_ids=entity_ids,
        )
        for e in ents:
            if not e.entity_id or not e.cached_name:
                continue
            out.append((
                str(e.entity_id),
                e.cached_name,
                e.kind_code or "unknown",
                list(e.cached_aliases or []),
            ))
        return out, False

    page = await glossary_client.list_all_entities(
        book_id,
        min_frequency=0,
        include_dead=True,
    )
    if page is None:
        logger.warning(
            "WS-4B: glossary list_all_entities failed for book=%s — nothing projected",
            book_id,
        )
        return out, False
    raw, truncated = page
    for entry in raw:
        eid = entry.get("entity_id")
        name = entry.get("name")
        if not eid or not name:
            continue
        out.append((
            str(eid),
            name,
            entry.get("kind_code") or "unknown",
            list(entry.get("aliases") or []),
        ))
    return out, truncated
