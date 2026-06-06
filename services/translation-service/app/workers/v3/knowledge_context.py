"""V3 knowledge context brief (M4b, G4).

Turns the glossary's tiered entity selection + the knowledge layer's relation
neighbourhoods into a compact, sanitized **pronoun/honorific brief** injected
into the Translator and the LLM Verifier. This is the "killer feature" for
context-correct names (who outranks/relates to whom → 你/您, anh/em/ngài).

Pipeline (once per chapter):
  select-for-context (entity_id + bio)  →  parallel wiki-neighborhood per entity
  →  trust-laddered, token-bounded, sanitized brief string.

Trust ladder (§11.2): a confirmed/glossary-anchored relation is stated plainly;
a `pending_validation` / low-confidence one is labelled "(unconfirmed)" so the
model treats it cautiously. Every interpolated field is sanitized — this text
crosses a service boundary into an LLM prompt (§11.4 injection-defense).

Fully best-effort: any failure (glossary/knowledge down, feature off) yields an
empty brief — knowledge enrichment must never fail a translation.
"""
from __future__ import annotations

import asyncio
import logging
import re

from ..glossary_client import fetch_context_entities, ContextEntity
from ..knowledge_client import fetch_wiki_neighborhood, WikiNeighborhood
from ..chunk_splitter import estimate_tokens

log = logging.getLogger(__name__)

_MAX_ENTITIES = 20
_FETCH_CONCURRENCY = 8
_TOKEN_BUDGET = 600
_TRUST_CONFIDENCE = 0.8  # ≥ this and not pending_validation ⇒ stated as fact
_MAX_RELATIONS_PER_ENTITY = 4
_FIELD_MAX = 200

_HEADER = (
    "CHARACTER & RELATION CONTEXT — use the EXACT names below and let the "
    "relationships guide pronouns/honorifics; treat \"(unconfirmed)\" items as "
    "weak hints, not facts:"
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BLOCK_MARKER = re.compile(r"\[\s*block", re.IGNORECASE)


def _sanitize(text: str, max_len: int = _FIELD_MAX) -> str:
    """Make a cross-service string safe to embed in an LLM prompt.

    Collapses whitespace/newlines, strips control chars, neutralizes anything
    resembling a ``[BLOCK n]`` marker (so injected text can't impersonate the
    block protocol), and caps length.
    """
    if not text:
        return ""
    t = _CONTROL.sub(" ", text)
    t = _BLOCK_MARKER.sub("(block", t)
    t = " ".join(t.split())  # collapse all whitespace runs
    if len(t) > max_len:
        t = t[:max_len].rstrip() + "…"
    return t


def _is_trusted(rel) -> bool:
    return (not rel.pending_validation) and rel.confidence >= _TRUST_CONFIDENCE


def _format_entity(entity: ContextEntity, nb: WikiNeighborhood) -> str | None:
    """One brief line per entity: name (kind): bio · relations. None if empty."""
    name = _sanitize(entity.name)
    if not name:
        return None
    head = name
    if entity.kind:
        head += f" ({_sanitize(entity.kind, 40)})"
    parts = [head]
    bio = _sanitize(entity.short_description)
    if bio:
        parts.append(bio)

    rel_strs: list[str] = []
    for rel in nb.relations:
        # A 1-hop neighbourhood edge can have THIS entity as subject OR object,
        # so render the full triple — "{predicate} {object}" alone would reverse
        # the meaning of edges where the entity is the object.
        subj = _sanitize(rel.subject_name or "", 80)
        obj = _sanitize(rel.object_name or "", 80)
        pred = _sanitize(rel.predicate or "", 40)
        if not pred or not (subj or obj):
            continue
        triple = " ".join(x for x in (subj, pred, obj) if x)
        label = "" if _is_trusted(rel) else " (unconfirmed)"
        rel_strs.append(f"{triple}{label}")
        if len(rel_strs) >= _MAX_RELATIONS_PER_ENTITY:
            break
    if rel_strs:
        parts.append("relations: " + "; ".join(rel_strs))
    return " — ".join(parts)


async def _fetch_all_neighborhoods(
    user_id: str, entities: list[ContextEntity], concurrency: int,
) -> list[WikiNeighborhood]:
    """Fetch every entity's neighbourhood in parallel (bounded). Once per chapter."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(e: ContextEntity) -> WikiNeighborhood:
        async with sem:
            return await fetch_wiki_neighborhood(user_id, e.entity_id)

    return await asyncio.gather(*(_one(e) for e in entities))


async def build_context_brief(
    book_id: str,
    user_id: str,
    chapter_text: str,
    *,
    max_entities: int = _MAX_ENTITIES,
    concurrency: int = _FETCH_CONCURRENCY,
    token_budget: int = _TOKEN_BUDGET,
) -> str:
    """Build the per-chapter pronoun/honorific brief (empty string on no data)."""
    entities = await fetch_context_entities(book_id, user_id, chapter_text, max_entities)
    if not entities:
        return ""

    neighborhoods = await _fetch_all_neighborhoods(user_id, entities, concurrency)

    lines: list[str] = []
    used = estimate_tokens(_HEADER)
    for entity, nb in zip(entities, neighborhoods):
        line = _format_entity(entity, nb)
        if not line:
            continue
        cost = estimate_tokens(line) + 1
        if used + cost > token_budget and lines:
            break  # budget exhausted — drop the rest
        lines.append(line)
        used += cost

    if not lines:
        return ""
    log.info("knowledge_context: %d entities in brief, ~%d tokens", len(lines), used)
    return _HEADER + "\n" + "\n".join(f"- {ln}" for ln in lines)
