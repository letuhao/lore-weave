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
    "AnchorPreloadUnavailable",
    "ProjectionResult",
    "load_glossary_anchors",
    "project_glossary_entities_to_nodes",
]


class AnchorPreloadUnavailable(RuntimeError):
    """The glossary could not be READ, so we do not know what already exists.

    Distinct from an empty result, which is a real answer ("this book has no curated
    entities"). This is the absence of an answer, and the two must never be conflated:
    running extraction on an empty anchor index makes the resolver mint a fresh node
    for every name in the chapter, and those duplicates are not automatically
    reversible — a human has to merge them back by hand.

    A failed read is transient by nature; a retried chapter costs one LLM call, a
    silently un-anchored chapter costs manual cleanup. So this fails CLOSED.
    """



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
      - glossary_client returns None (circuit open / HTTP error) → raise
        `AnchorPreloadUnavailable`. This USED to return [] "so extraction still
        runs", which reads as resilience and is not: with no anchors the resolver
        mints a new node for every name in the chapter, and un-merging them is
        manual work. Retrying a chapter is cheap; hand-merging duplicates is not.
      - Empty list from glossary → return []. This means the book genuinely has no
        curated entries. It used to ALSO mean "it has entries, but none has been
        mentioned in two chapters yet" — a silent failure indistinguishable from the
        normal state, which is why the frequency gate below is now explicitly disabled.
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
    # D-ANCHOR-PRELOAD-FREQUENCY-GATE: `min_frequency` defaults to 2 in the client
    # (mirroring the Go handler's `HAVING COUNT(chapter_links) >= 2`), and this call
    # never overrode it — so an entity had to be MENTIONED IN TWO CHAPTERS before it
    # could become an anchor. For a book being written from scratch every curated entity
    # has zero chapter links, so the pre-load returned NOTHING and the extractor ran
    # blind against the author's own glossary. Live-measured on Mị Đế: 0 anchors at the
    # default, 12 at min_frequency=0.
    #
    # Frequency is the wrong signal here. It is a relevance heuristic for "what matters
    # in this book so far" (the chat intent gate's question). An anchor's job is the
    # opposite: tell the extractor THIS ALREADY EXISTS so it links instead of minting a
    # duplicate — and for that, existence IS the signal. The human curated the entry;
    # that is the strongest possible endorsement, and it is available before any prose
    # is written. Anchors become an in-memory name→kind index (pass2_orchestrator), not
    # prompt text, so the larger set costs no token budget, and the 60s TTL cache in
    # internal_extraction amortises the bigger read across a whole extraction job.
    page = await glossary_client.list_all_entities(
        book_id, status_filter=status_filter, min_frequency=0,
    )
    if page is None:
        raise AnchorPreloadUnavailable(
            f"glossary entity read failed for book={book_id} — refusing to extract "
            "un-anchored (the extractor would mint duplicates that need manual merge)"
        )
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


#: How many projected node ids the tool hands back. `entity_ids=None` projects a whole glossary,
#: so this is a payload bound, not a limit on the work: the projection still writes every node and
#: `nodes_truncated` reports that the id list is short. A caller that needs the rest names its
#: entity_ids explicitly, which is the same escape hatch `truncated` already documents.
NODES_RETURNED_CAP = 50


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
    #: 🔴 THE IDS, BECAUSE COUNTS CANNOT BE CHAINED. Measured 2026-08-23 over K=5: this projection
    #: is the documented prerequisite of `kg_propose_edge`, which REQUIRES source_entity_id and
    #: target_entity_id — and the tool returned only counts. The model, having created two nodes
    #: and been told "nodes_created: 2", had no id to pass, so it invented one and used it for
    #: BOTH endpoints (66966666-6666-6666-6666-666666666666). The platform's fabricated-id guard
    #: could not help: it tests SYNTAX, and a repdigit UUID parses fine.
    #:
    #: The loop already held each `Entity` and threw it away into `_`. BOUNDED at
    #: `NODES_RETURNED_CAP` because `entity_ids=None` projects the WHOLE glossary and an unbounded
    #: id list would be a payload the caller never asked for; `nodes_truncated` says so rather
    #: than silently returning a short list, the same discipline `truncated` already follows.
    nodes: tuple[dict, ...] = field(default_factory=tuple)
    nodes_truncated: bool = False
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
    projected: list[dict] = []
    for eid, name, kind, aliases in rows:
        try:
            _entity, was_created = await upsert_glossary_anchor_counted(
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
        # The id the SUCCESSOR needs. Appended after the counters so an upsert that raised
        # above cannot contribute an id for a node that was never written.
        if len(projected) < NODES_RETURNED_CAP:
            projected.append({"entity_id": _entity.id, "name": name, "kind": kind})

    logger.info(
        "WS-4B: projection complete — book=%s project=%s seen=%d created=%d "
        "existing=%d conflicted=%d skipped=%d truncated=%s",
        book_id, project_id, len(rows), created, existing, conflicted, skipped,
        truncated,
    )
    return ProjectionResult(
        created=created, existing=existing, seen=len(rows), skipped=skipped,
        truncated=truncated, conflicted=conflicted,
        nodes=tuple(projected),
        nodes_truncated=(created + existing) > len(projected),
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
