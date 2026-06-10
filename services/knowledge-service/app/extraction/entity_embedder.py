"""K17 — entity-embedding WRITE pipeline (producer).

Stamps ``:Entity.embedding_{dim}`` + ``embedding_model`` on anchored entities so
the mui#4 semantic glossary read path (``find_entities_by_vector`` /
``/internal/context/glossary-semantic``) works at scale instead of needing the
hand-stamped vectors used to live-smoke it (DEFERRED 061).

Mirrors the passage embedding pipeline
(``app/extraction/passage_ingester.ingest_chapter_passages``): one batch embed
via provider-registry, a dim-validated per-entity write, and every external
dependency soft-failed so a producer hiccup never blocks anything upstream.

**Trigger (PO 2026-06-08): batch-backfill + incremental (B).** Unlike passages
(chapter-scoped, ingested on ``chapter.published``), an entity is cross-chapter
— it accretes aliases/evidence across chapters — so embedding per-chapter would
redundantly re-embed and capture an entity before its aliases settle. Instead
this embeds anchored entities whose embedding is MISSING or STALE
(``find_entities_needing_embedding``: never embedded, model changed, or
``embedding_version < version``). One batch per call (``limit``); the caller
(internal backfill route / the incremental post-extraction hook) drains with a
per-run cap.

**Embed text** = name + aliases + short_description, sourced from the glossary
SSOT (``fetch_entities_by_ids`` by ``glossary_entity_id``) — the same fields the
read path's ``_estimate_entity_tokens`` ranks on. Falls back to the KG-local
name+aliases if the glossary read degrades (so a glossary blip still embeds,
just less richly).

**Scope** = anchored (``glossary_entity_id``) + active (not archived) entities —
exactly the set the read path can return, so we never embed an orphan KG node.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.clients.glossary_client import GlossaryClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import (
    SUPPORTED_VECTOR_DIMS,
    find_entities_needing_embedding,
    set_entity_embedding,
)

logger = logging.getLogger(__name__)

__all__ = ["EmbedEntitiesResult", "embed_project_entities", "build_embed_text"]


@dataclass
class EmbedEntitiesResult:
    """Stats from one ``embed_project_entities`` batch.

    ``candidates == limit`` is the "more remain" signal the drain loop reads.
    """

    embedded: int = 0
    skipped: int = 0
    candidates: int = 0
    embed_failed: bool = False


def build_embed_text(
    name: str | None, aliases: list[str] | None, short_description: str | None
) -> str:
    """Compose the embedding text: name + aliases + short_description (the same
    fields the read path's `_estimate_entity_tokens` ranks on). Empty parts are
    dropped; returns "" when nothing usable (caller skips such entities)."""
    parts: list[str] = []
    if name:
        parts.append(name)
    if aliases:
        parts.append(" ".join(a for a in aliases if a))
    if short_description:
        parts.append(short_description)
    return " ".join(p for p in parts if p and p.strip()).strip()


async def embed_project_entities(
    session: CypherSession,
    embedding_client: EmbeddingClient,
    glossary_client: GlossaryClient,
    *,
    user_id: UUID,
    project_id: UUID,
    book_id: UUID,
    embedding_model: str,
    embedding_dim: int,
    model_source: str = "user_model",
    limit: int = 200,
) -> EmbedEntitiesResult:
    """Embed ONE batch (≤ ``limit``) of anchored entities needing a (re)embed.

    Idempotent + degrade-safe: a glossary-read failure falls back to KG-local
    text; an embed failure skips the whole batch (no partial-vector writes);
    a per-entity write failure skips that entity. Returns counts; the caller
    drains by re-calling while ``candidates == limit``."""
    result = EmbedEntitiesResult()

    if embedding_dim not in SUPPORTED_VECTOR_DIMS:
        logger.warning(
            "K17: skip embed — embedding_dim %s not in %s",
            embedding_dim, SUPPORTED_VECTOR_DIMS,
        )
        return result

    # 1. Anchored entities missing/stale a current-model embedding.
    entities = await find_entities_needing_embedding(
        session,
        user_id=str(user_id),
        project_id=str(project_id),
        embedding_model=embedding_model,
        limit=limit,
    )
    result.candidates = len(entities)
    if not entities:
        return result

    # 2. Glossary SSOT text (name/aliases/short_description) by glossary FK.
    #    Degrade-safe: a glossary blip → KG-local name+aliases fallback.
    glossary_ids = [e.glossary_entity_id for e in entities if e.glossary_entity_id]
    gloss_by_id: dict[str, object] = {}
    if glossary_ids:
        try:
            rows = await glossary_client.fetch_entities_by_ids(
                book_id=book_id, entity_ids=glossary_ids,
            )
            gloss_by_id = {r.entity_id: r for r in rows}
        except Exception:  # noqa: BLE001 — best-effort enrichment
            logger.warning(
                "K17: glossary text fetch failed (project=%s) — KG-local fallback",
                project_id, exc_info=True,
            )

    # 3. Build embed text per entity; skip entities with no usable text.
    work: list[tuple[object, str]] = []
    for e in entities:
        g = gloss_by_id.get(e.glossary_entity_id) if e.glossary_entity_id else None
        if g is not None:
            text = build_embed_text(
                getattr(g, "cached_name", None) or e.name,
                getattr(g, "cached_aliases", None) or e.aliases,
                getattr(g, "short_description", None),
            )
        else:
            text = build_embed_text(e.name, e.aliases, None)
        if not text:
            result.skipped += 1
            continue
        work.append((e, text))

    if not work:
        return result

    # 4. One batch embed (the cost-dominant call — mirrors passage ingest).
    try:
        embed_result = await embedding_client.embed(
            user_id=user_id,
            model_source=model_source,
            model_ref=embedding_model,
            texts=[t for _, t in work],
        )
    except EmbeddingError:
        logger.warning(
            "K17: embed failed (project=%s) — skipping batch", project_id,
            exc_info=True,
        )
        result.embed_failed = True
        return result

    if len(embed_result.embeddings) != len(work):
        logger.warning(
            "K17: embed returned %d vectors for %d entities — skipping batch",
            len(embed_result.embeddings), len(work),
        )
        return result

    # 5. Stamp each entity (per-entity failure is isolated).
    for (e, _text), vector in zip(work, embed_result.embeddings):
        if len(vector) != embedding_dim:
            logger.warning(
                "K17: entity %s dim mismatch (got %d, expected %d) — skipping",
                e.id, len(vector), embedding_dim,
            )
            result.skipped += 1
            continue
        try:
            ok = await set_entity_embedding(
                session,
                user_id=str(user_id),
                entity_id=e.id,
                embedding=vector,
                embedding_dim=embedding_dim,
                embedding_model=embedding_model,
                embedding_version=e.version,
            )
            if ok:
                result.embedded += 1
            else:
                # MATCH found no row — the entity was archived/deleted between
                # the find and the set (a concurrent edit); not an error.
                result.skipped += 1
        except Exception:  # noqa: BLE001 — isolate one bad write
            logger.exception("K17: set_entity_embedding failed entity=%s", e.id)
            result.skipped += 1

    logger.info(
        "K17: embedded project=%s model=%s embedded=%d skipped=%d candidates=%d",
        project_id, embedding_model,
        result.embedded, result.skipped, result.candidates,
    )
    return result
