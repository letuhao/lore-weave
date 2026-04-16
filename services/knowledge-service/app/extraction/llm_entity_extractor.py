"""K17.4 — LLM-powered entity extractor.

Extracts named entities from text using a BYOK LLM via the K17.1→K17.3
stack (prompt loader → JSON extraction wrapper with retry). Returns
post-processed candidates with deterministic canonical IDs (K15.1) so
re-running extraction on the same source is idempotent.

**This module does NOT write to Neo4j.** It produces `LLMEntityCandidate`
records that K17.8 (Pass 2 orchestrator) feeds into K15.7's write layer.

**Relationship to K15.2 (pattern-based entity detector):**
  - K15.2 is Pass 1 (fast, regex-based, quarantined at low confidence)
  - K17.4 is Pass 2 (LLM-powered, higher confidence, validates/refines
    Pass 1 candidates)
  - Both produce candidate lists; K17.8 orchestrator reconciles them.

Dependencies: K17.1 (prompt loader), K17.3 (extract_json), K15.1
(canonicalize_entity_name, entity_canonical_id).

Reference: KSA §5.1.6, K17.4 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.clients.provider_client import ProviderClient
from app.db.neo4j_repos.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)
from app.extraction.llm_json_parser import ExtractionError, extract_json
from app.extraction.llm_prompts import load_prompt

__all__ = [
    "EntityExtractionResponse",
    "LLMEntityCandidate",
    "extract_entities",
]

logger = logging.getLogger(__name__)

# ── LLM response schema (matches entity_extraction.md prompt) ────────

EntityKind = Literal[
    "person", "place", "organization", "artifact", "concept", "other"
]


class _LLMEntity(BaseModel):
    """Single entity from the LLM response — raw, pre-canonicalization."""

    name: str
    kind: EntityKind
    aliases: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)


class EntityExtractionResponse(BaseModel):
    """Outer wrapper matching the JSON schema in entity_extraction.md."""

    entities: list[_LLMEntity] = []


# ── Post-processed output model ──────────────────────────────────────


class LLMEntityCandidate(BaseModel):
    """Entity candidate with deterministic canonical ID.

    Ready for K15.7 write layer / K17.8 Pass 2 orchestrator.
    `canonical_id` is derived via K15.1 so re-running extraction on
    the same source text produces the same IDs — idempotent.
    """

    name: str
    kind: str
    aliases: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    canonical_name: str
    canonical_id: str


# ── Public entry point ───────────────────────────────────────────────


async def extract_entities(
    text: str,
    known_entities: list[str],
    *,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    client: ProviderClient | None = None,
) -> list[LLMEntityCandidate]:
    """Extract named entities from *text* via the user's BYOK LLM.

    Args:
        text: chapter or passage text to extract from. Empty/whitespace
            returns ``[]`` without calling the LLM.
        known_entities: canonical entity names already in the graph.
            The LLM prompt instructs the model to prefer these over
            inventing new spellings.
        user_id: tenant scope for canonical ID derivation.
        project_id: project scope (``None`` for global).
        model_source: ``"user_model"`` or ``"platform_model"``.
        model_ref: model reference key in provider-registry.
        client: injectable ``ProviderClient`` for testing. Production
            callers leave this ``None``.

    Returns:
        Deduplicated list of ``LLMEntityCandidate`` sorted by
        confidence descending. Deduplication is by ``canonical_id``,
        which hashes ``(user_id, project_id, name, kind)``. Two
        candidates CAN share the same display ``name`` if their
        ``kind`` differs (e.g. "Kai" as person vs. concept). The
        caller (K17.8 orchestrator) is responsible for reconciling
        same-name-different-kind duplicates if that's undesirable.

    Raises:
        ExtractionError: on terminal LLM / parse / validation failure
            (propagated from K17.3).
    """
    if not text or not text.strip():
        return []

    # I1/I7 (R2): escape curly braces in caller-supplied values before
    # substitution. load_prompt uses str.format_map internally — literal
    # { or } in the text (common in code-quoting novels, system-prompt
    # fiction, or entity names like "The {Ancient} One") would be
    # misinterpreted as format placeholders and raise KeyError.
    safe_text = text.replace("{", "{{").replace("}", "}}")
    safe_known = json.dumps(
        known_entities, ensure_ascii=False
    ).replace("{", "{{").replace("}", "}}")

    user_prompt = load_prompt(
        "entity",
        text=safe_text,
        known_entities=safe_known,
    )

    response = await extract_json(
        EntityExtractionResponse,
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        system=None,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        client=client,
    )

    return _postprocess(
        response.entities,
        user_id=user_id,
        project_id=project_id,
        known_entities=known_entities,
    )


# ── Post-processing ─────────────────────────────────────────────────


def _postprocess(
    raw_entities: list[_LLMEntity],
    *,
    user_id: str,
    project_id: str | None,
    known_entities: list[str],
) -> list[LLMEntityCandidate]:
    """Canonicalize, anchor to known entities, deduplicate."""
    # Build a case-insensitive lookup from known_entities so we can
    # snap LLM output to the canonical spelling the caller already has.
    known_lower: dict[str, str] = {
        name.strip().lower(): name.strip() for name in known_entities
    }

    # Accumulate by canonical_id so near-duplicates fold into one.
    seen: dict[str, LLMEntityCandidate] = {}

    for entity in raw_entities:
        name = _anchor_name(entity.name.strip(), known_lower)
        if not name:
            continue

        canonical_name = canonicalize_entity_name(name)
        if not canonical_name:
            continue

        try:
            cid = entity_canonical_id(
                user_id, project_id, name, entity.kind
            )
        except ValueError:
            # Defensive — canonicalize_entity_name already guards but
            # entity_canonical_id does its own checks. Skip silently.
            logger.debug(
                "skipping entity %r: canonical_id derivation failed",
                name,
            )
            continue

        if cid in seen:
            # Merge: keep higher confidence, union aliases.
            existing = seen[cid]
            merged_aliases = _merge_aliases(
                existing.aliases, entity.aliases, name, existing.name
            )
            seen[cid] = existing.model_copy(
                update={
                    "confidence": max(existing.confidence, entity.confidence),
                    "aliases": merged_aliases,
                }
            )
        else:
            seen[cid] = LLMEntityCandidate(
                name=name,
                kind=entity.kind,
                aliases=list(entity.aliases),
                confidence=entity.confidence,
                canonical_name=canonical_name,
                canonical_id=cid,
            )

    # Sort by confidence descending, then name for stable ordering.
    return sorted(
        seen.values(),
        key=lambda c: (-c.confidence, c.name),
    )


def _anchor_name(
    llm_name: str, known_lower: dict[str, str]
) -> str:
    """If the LLM name matches a known entity (case-insensitive),
    return the canonical spelling from known_entities. Otherwise
    return the LLM name as-is.

    Implements prompt rule 5: "Known entities win ties."
    """
    key = llm_name.strip().lower()
    return known_lower.get(key, llm_name)


def _merge_aliases(
    existing_aliases: list[str],
    new_aliases: list[str],
    new_name: str,
    existing_name: str,
) -> list[str]:
    """Union aliases from two duplicate entities, adding the alternate
    display name as an alias if it differs from the kept name."""
    alias_set: set[str] = set(existing_aliases)
    alias_set.update(new_aliases)
    # If the duplicate had a different display spelling, keep it as alias.
    if new_name != existing_name:
        alias_set.add(new_name)
    # Remove the primary name from aliases (shouldn't be its own alias).
    alias_set.discard(existing_name)
    return sorted(alias_set)
