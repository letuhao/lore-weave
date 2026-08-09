"""Glossary → :Passage producer, so authored lore is RETRIEVABLE, not just present.

Why this exists
---------------
`KNOWN_SOURCE_TYPES` has declared `"glossary"` since the passage repo was written —
with the comment "Add a member here first before writing a new source_type producer."
The producer was never written. The search filter accepted it, the facet count padded
it to 0, and nothing ever created one: measured across the whole dev graph, every
`:Passage` was `chapter` or `benchmark_entity`.

The consequence landed on the author, not the graph. The composition packer feeds a
scene prompt from two lore paths and BOTH were empty for a book that hasn't been
written yet:

  * `gather_present` renders a cast bio from `short_description` alone
  * `gather_lore` searches `:Passage` — and there was no glossary passage to find

So a glossary built BEFORE chapter 1 reached the drafting prompt as bare names. This
module closes the second path: one passage per glossary entity, carrying the authored
attribute values, embedded with the project's own model so the lore lens retrieves it
semantically.

Posture: WHOLLY best-effort. The `:Entity` sync (the SSOT→graph path) must never fail
because indexing did — a project with no embedding model, no Neo4j, or a provider
outage simply has un-indexed lore, and says so in the log.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.clients.embedding_client import EmbeddingClient, EmbeddingError
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.passages import (
    SUPPORTED_PASSAGE_DIMS,
    get_passage_content_hash,
    upsert_passage,
)

__all__ = ["render_glossary_passage", "sync_glossary_entity_passage"]

logger = logging.getLogger(__name__)

#: One entity is ONE chunk. A glossary entry is a bounded profile (the deep builder's
#: long-form sections are distilled into attributes before they reach the glossary), so
#: chunking would fragment a single coherent unit and hurt retrieval. Capped rather than
#: split; truncation is logged, never silent.
GLOSSARY_PASSAGE_CHUNK = 0
MAX_PASSAGE_CHARS = 4000


def _flatten(value: str, field_type: str) -> str:
    """A `tags` value is stored as a JSON-encoded array string. Embedding the literal
    `["a","b"]` would put brackets and escapes into the vector; render it as prose."""
    if field_type != "tags":
        return value.strip()
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return value.strip()
    if isinstance(parsed, list):
        return ", ".join(str(v).strip() for v in parsed if str(v).strip())
    return value.strip()


def render_glossary_passage(
    *, name: str, kind: str, aliases: list[str] | None,
    short_description: str | None, attributes: list[dict[str, Any]] | None,
) -> str:
    """The searchable document for ONE entity.

    Label-prefixed lines ("Vai trò: …") rather than a bare value dump: the label is
    part of what an author's query matches ("ai là người dẫn dắt Lâm Uyên" should reach
    a `mentor`/`role` line), and it costs a handful of tokens.
    """
    lines: list[str] = [f"{name} ({kind})" if kind else name]
    if aliases:
        joined = ", ".join(a.strip() for a in aliases if a and a.strip())
        if joined:
            lines.append(f"Aliases: {joined}")

    # short_description is never additive when attributes exist. It is either DERIVED
    # from the `description` attribute (a truncated copy — an equality check would not
    # even catch it) or, for a kind with no `description` field, a generated stub:
    # `terminology` rendered "Terminology: Luyện khí", pure restatement of the header.
    # So the authored attributes win outright, and the summary is the fallback for an
    # entity that has none.
    body: list[str] = []
    seen_values: set[str] = {name.strip()} if name.strip() else set()
    for attr in attributes or []:
        value = _flatten(str(attr.get("value") or ""), str(attr.get("field_type") or "text"))
        if not value:
            continue
        # Skip by VALUE, not by code. The identity field is not always `name` —
        # `terminology` calls it `term`, `item` uses `name` — and hardcoding a code
        # list is the same schema-blindness that put character fields on every kind.
        # Anything already said (the header name, an alias line, a repeat) is dropped.
        if value in seen_values:
            continue
        seen_values.add(value)
        label = str(attr.get("label") or attr.get("code") or "").strip()
        body.append(f"{label}: {value}" if label else value)

    if body:
        lines.extend(body)
    elif (short_description or "").strip():
        lines.append(short_description.strip())

    text = "\n".join(lines)
    if len(text) > MAX_PASSAGE_CHARS:
        logger.info(
            "glossary passage truncated: %s chars → %s (entity=%s)",
            len(text), MAX_PASSAGE_CHARS, name,
        )
        text = text[:MAX_PASSAGE_CHARS]
    return text


async def _current_hash(
    session: CypherSession, *, user_id: str, project_id: str, source_id: str,
) -> str | None:
    """The stored content hash, so a re-delivered event or a full backfill doesn't
    re-embed unchanged lore. glossary.entity_updated is at-least-once and a backfill
    walks every entity — without this, both pay a provider call per entity per run.

    The Cypher moved into the passages repo (plan T12); this stays as the thin
    binding that knows THIS module's source_type and chunk index."""
    return await get_passage_content_hash(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type="glossary",
        source_id=source_id,
        chunk_index=GLOSSARY_PASSAGE_CHUNK,
    )


async def sync_glossary_entity_passage(
    session: CypherSession,
    embedding_client: EmbeddingClient,
    *,
    user_id: str,
    project_id: str,
    glossary_entity_id: str,
    text: str,
    embedding_model: str | None,
    embedding_dim: int | None,
    model_source: str = "user_model",
    source_lang: str = "unknown",
) -> str:
    """Embed + upsert the entity's passage. Returns an outcome token for the caller
    to log/report — never raises for an expected degrade.

    Outcomes: `indexed` · `unchanged` · `no_embedding_model` · `unsupported_dim` ·
    `empty` · `embed_failed`. The caller reports these to the user rather than
    swallowing them: "your lore is not indexed" is a fact the author must be told,
    and an un-surfaced degrade here is exactly the silent no-op this whole track
    exists to remove.
    """
    if not text.strip():
        return "empty"
    if not embedding_model or not embedding_dim:
        logger.info(
            "glossary passage skipped — project %s has no embedding model configured",
            project_id,
        )
        return "no_embedding_model"
    if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
        logger.warning(
            "glossary passage skipped — embedding_dim %s not in %s (project %s)",
            embedding_dim, SUPPORTED_PASSAGE_DIMS, project_id,
        )
        return "unsupported_dim"

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if await _current_hash(
        session, user_id=user_id, project_id=project_id, source_id=glossary_entity_id,
    ) == content_hash:
        return "unchanged"

    try:
        result = await embedding_client.embed(
            user_id=user_id, model_source=model_source,
            model_ref=embedding_model, texts=[text],
        )
    except EmbeddingError:
        logger.warning(
            "glossary passage embed failed (entity=%s project=%s)",
            glossary_entity_id, project_id, exc_info=True,
        )
        return "embed_failed"

    vectors = result.embeddings or []
    if not vectors or not vectors[0]:
        return "embed_failed"
    vector = vectors[0]
    if len(vector) != embedding_dim:
        logger.warning(
            "glossary passage dim mismatch: got %s want %s (project %s)",
            len(vector), embedding_dim, project_id,
        )
        return "unsupported_dim"

    await upsert_passage(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type="glossary",
        source_id=glossary_entity_id,
        chunk_index=GLOSSARY_PASSAGE_CHUNK,
        text=text,
        embedding=vector,
        embedding_dim=embedding_dim,
        embedding_model=embedding_model,
        # Authored glossary content IS canon — unlike a draft chapter's prose, it is
        # the SSOT the author curates, so it belongs in a `surface=canon` read.
        canon=True,
        source_lang=source_lang or "unknown",
        content_hash=content_hash,
    )
    return "indexed"
