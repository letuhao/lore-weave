"""K17.5 — LLM-powered relation extractor.

Extracts (subject, predicate, object) relations from text using a
BYOK LLM via the K17.1→K17.3 stack. Post-processes with entity
anchoring (resolving subject/object to K17.4 entity canonical IDs)
and deterministic `relation_id` derivation (K11.6).

**This module does NOT write to Neo4j.** It produces
`LLMRelationCandidate` records that K17.8 (Pass 2 orchestrator)
feeds into K11.6's write layer.

**Relationship to K15.4 (pattern-based triple extractor):**
  - K15.4 is Pass 1 (SVO regex, English-only, quarantined)
  - K17.5 is Pass 2 (LLM, multilingual, higher confidence)
  - Both produce relation lists; K17.8 orchestrator reconciles.

**Entity resolution:** K17.8 runs K17.4 (entity extraction) first,
then passes the resulting `LLMEntityCandidate` list to K17.5 so
subject/object names can be resolved to canonical IDs. Relations
whose subject or object cannot be resolved get `subject_id=None` /
`object_id=None` / `relation_id=None` — the caller decides whether
to create ad-hoc entity nodes or drop the relation.

Dependencies: K17.1 (prompt loader), K17.3 (extract_json), K17.4
(LLMEntityCandidate), K15.1 (entity_canonical_id), K11.6 (relation_id).

Reference: KSA §5.1, K17.5 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.clients.provider_client import ProviderClient
from app.db.neo4j_repos.relations import relation_id as compute_relation_id
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_json_parser import ExtractionError, extract_json
from app.extraction.llm_prompts import load_prompt

__all__ = [
    "LLMRelationCandidate",
    "RelationExtractionResponse",
    "extract_relations",
]

logger = logging.getLogger(__name__)

# ── LLM response schema (matches relation_extraction.md prompt) ──────

Polarity = Literal["affirm", "negate"]
Modality = Literal["asserted", "reported", "hypothetical"]


class _LLMRelation(BaseModel):
    """Single relation from the LLM response — raw, pre-resolution."""

    subject: str
    predicate: str
    object_: str = Field(alias="object")
    polarity: Polarity = "affirm"
    modality: Modality = "asserted"
    confidence: float = Field(ge=0.0, le=1.0)

    model_config = {"populate_by_name": True}


class RelationExtractionResponse(BaseModel):
    """Outer wrapper matching the JSON schema in relation_extraction.md."""

    relations: list[_LLMRelation] = []


# ── Post-processed output model ──────────────────────────────────────


class LLMRelationCandidate(BaseModel):
    """Relation candidate with resolved entity IDs.

    `subject_id` / `object_id` are canonical entity IDs when the
    subject/object name could be resolved against the entities
    extracted by K17.4. ``None`` when unresolvable — K17.8 decides
    whether to create ad-hoc entity nodes or drop the relation.

    `relation_id` is only set when both endpoints are resolved
    (K11.6 `relation_id` requires both `subject_id` and `object_id`).
    """

    subject: str
    predicate: str
    object: str
    polarity: str
    modality: str
    confidence: float = Field(ge=0.0, le=1.0)
    subject_id: str | None
    object_id: str | None
    relation_id: str | None


# ── Predicate normalization ──────────────────────────────────────────

_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def _normalize_predicate(pred: str) -> str:
    """Lowercase, strip, collapse non-alphanum runs to underscores.

    'Works For' → 'works_for', 'married-to' → 'married_to'.
    Prompt instructs snake_case but LLMs are inconsistent.
    """
    result = _NON_WORD_RE.sub("_", pred.strip().lower())
    return result.strip("_")


# ── Public entry point ───────────────────────────────────────────────


async def extract_relations(
    text: str,
    entities: list[LLMEntityCandidate],
    known_entities: list[str],
    *,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    client: ProviderClient | None = None,
) -> list[LLMRelationCandidate]:
    """Extract relations from *text* via the user's BYOK LLM.

    Args:
        text: chapter or passage text. Empty/whitespace returns ``[]``
            without calling the LLM.
        entities: entity candidates from K17.4's ``extract_entities``.
            Used to resolve subject/object names to canonical IDs.
        known_entities: canonical entity names already in the graph.
            Passed through to the LLM prompt for anchoring.
        user_id: tenant scope.
        project_id: project scope (``None`` for global).
        model_source: ``"user_model"`` or ``"platform_model"``.
        model_ref: model reference key in provider-registry.
        client: injectable ``ProviderClient`` for testing.

    Returns:
        List of ``LLMRelationCandidate`` sorted by confidence
        descending. Relations whose subject/object cannot be resolved
        have ``subject_id=None`` / ``object_id=None`` /
        ``relation_id=None``.

    Raises:
        ExtractionError: on terminal LLM / parse / validation failure
            (propagated from K17.3).
    """
    if not text or not text.strip():
        return []

    # K17.4-R2 I1/I7: escape curly braces in caller-supplied values.
    safe_text = text.replace("{", "{{").replace("}", "}}")
    safe_known = json.dumps(
        known_entities, ensure_ascii=False
    ).replace("{", "{{").replace("}", "}}")

    user_prompt = load_prompt(
        "relation",
        text=safe_text,
        known_entities=safe_known,
    )

    response = await extract_json(
        RelationExtractionResponse,
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        system=None,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        client=client,
    )

    return _postprocess(
        response.relations,
        entities=entities,
        known_entities=known_entities,
        user_id=user_id,
        project_id=project_id,
    )


# ── Post-processing ─────────────────────────────────────────────────


def _build_entity_lookup(
    entities: list[LLMEntityCandidate],
) -> dict[str, LLMEntityCandidate]:
    """Case-insensitive lookup: name/alias → entity candidate.

    Priority order via setdefault: first-inserted wins. Entities are
    ordered by confidence (K17.4 sorts descending), so higher-confidence
    entities claim the key first.
    """
    lookup: dict[str, LLMEntityCandidate] = {}
    for ent in entities:
        # Index by display name
        lookup.setdefault(ent.name.lower(), ent)
        # Index by canonical name
        lookup.setdefault(ent.canonical_name.lower(), ent)
        # Index by aliases
        for alias in ent.aliases:
            lookup.setdefault(alias.lower(), ent)
    return lookup


def _resolve_entity(
    name: str,
    lookup: dict[str, LLMEntityCandidate],
    known_entities_lower: dict[str, str],
) -> LLMEntityCandidate | None:
    """Resolve a subject/object name to an entity candidate.

    Tries: exact match, known-entities-anchored match, then gives up.
    """
    key = name.strip().lower()
    if key in lookup:
        return lookup[key]
    # Try anchoring to known entity spelling first, then look up
    anchored = known_entities_lower.get(key)
    if anchored and anchored.lower() in lookup:
        return lookup[anchored.lower()]
    return None


def _postprocess(
    raw_relations: list[_LLMRelation],
    *,
    entities: list[LLMEntityCandidate],
    known_entities: list[str],
    user_id: str,
    project_id: str | None,
) -> list[LLMRelationCandidate]:
    """Resolve endpoints, normalize predicates, deduplicate."""
    entity_lookup = _build_entity_lookup(entities)
    known_lower: dict[str, str] = {
        n.strip().lower(): n.strip() for n in known_entities
    }

    seen: dict[str, LLMRelationCandidate] = {}

    for rel in raw_relations:
        predicate = _normalize_predicate(rel.predicate)
        if not predicate:
            continue

        subject_name = rel.subject.strip()
        object_name = rel.object_.strip()
        if not subject_name or not object_name:
            continue

        # Resolve to entity candidates
        subject_ent = _resolve_entity(subject_name, entity_lookup, known_lower)
        object_ent = _resolve_entity(object_name, entity_lookup, known_lower)

        subject_id = subject_ent.canonical_id if subject_ent else None
        object_id = object_ent.canonical_id if object_ent else None

        # Compute relation_id only when both endpoints are resolved
        rid: str | None = None
        if subject_id and object_id:
            try:
                rid = compute_relation_id(
                    user_id, subject_id, predicate, object_id
                )
            except ValueError:
                logger.debug(
                    "skipping relation %s->%s->%s: relation_id failed",
                    subject_name, predicate, object_name,
                )
                continue

        # Use anchored display names when available
        display_subject = subject_ent.name if subject_ent else subject_name
        display_object = object_ent.name if object_ent else object_name

        candidate = LLMRelationCandidate(
            subject=display_subject,
            predicate=predicate,
            object=display_object,
            polarity=rel.polarity,
            modality=rel.modality,
            confidence=rel.confidence,
            subject_id=subject_id,
            object_id=object_id,
            relation_id=rid,
        )

        # Deduplicate by relation_id (keep higher confidence).
        # Relations without relation_id are kept as-is (no dedup key).
        if rid and rid in seen:
            existing = seen[rid]
            if rel.confidence > existing.confidence:
                seen[rid] = candidate
        elif rid:
            seen[rid] = candidate
        else:
            # No relation_id — use a synthetic key to avoid duplicates
            # for the same (subject, predicate, object) triple.
            synth_key = f"{display_subject.lower()}:{predicate}:{display_object.lower()}"
            if synth_key not in seen:
                seen[synth_key] = candidate
            elif rel.confidence > seen[synth_key].confidence:
                seen[synth_key] = candidate

    return sorted(
        seen.values(),
        key=lambda c: (-c.confidence, c.subject),
    )
