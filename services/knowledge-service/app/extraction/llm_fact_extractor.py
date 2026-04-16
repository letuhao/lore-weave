"""K17.7 — LLM-powered fact extractor.

Extracts standalone factual claims from text using a BYOK LLM via the
K17.1→K17.3 stack. Post-processes with subject resolution (resolving
the optional subject name to a K17.4 entity canonical ID) and
deterministic ``fact_id`` derivation.

**This module does NOT write to Neo4j.** It produces
``LLMFactCandidate`` records that K17.8 (Pass 2 orchestrator)
feeds into the write layer.

**Relationship to K15.5 (pattern-based fact extractor):**
  - K15.5 is Pass 1 (regex, English-only, quarantined)
  - K17.7 is Pass 2 (LLM, multilingual, higher confidence)
  - Both produce fact lists; K17.8 orchestrator reconciles.

**Entity resolution:** K17.8 runs K17.4 (entity extraction) first,
then passes the resulting ``LLMEntityCandidate`` list to K17.7 so
the optional subject name can be resolved to a canonical ID.

Dependencies: K17.1 (prompt loader), K17.3 (extract_json), K17.4
(LLMEntityCandidate).

Reference: KSA §5.1, K17.7 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.clients.provider_client import ProviderClient
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_json_parser import ExtractionError, extract_json
from app.extraction.llm_prompts import load_prompt

__all__ = [
    "LLMFactCandidate",
    "FactExtractionResponse",
    "extract_facts",
]

logger = logging.getLogger(__name__)

# ── LLM response schema (matches fact_extraction.md prompt) ───────

FactType = Literal[
    "description", "attribute", "negation", "temporal", "causal",
]

Polarity = Literal["affirm", "negate"]
Modality = Literal["asserted", "reported", "hypothetical"]


class _LLMFact(BaseModel):
    """Single fact from the LLM response — raw, pre-resolution."""

    content: str
    type: FactType
    subject: str | None = None
    polarity: Polarity = "affirm"
    modality: Modality = "asserted"
    confidence: float = Field(ge=0.0, le=1.0)


class FactExtractionResponse(BaseModel):
    """Outer wrapper matching the JSON schema in fact_extraction.md."""

    facts: list[_LLMFact] = []


# ── Post-processed output model ──────────────────────────────────

class LLMFactCandidate(BaseModel):
    """Fact candidate with resolved subject ID.

    ``subject`` / ``subject_id`` are the display name and canonical
    entity ID when the fact is about a specific entity. ``None`` for
    universal claims (e.g. "The Empire was vast").

    ``fact_id`` is a deterministic hash of ``(user_id, content)`` —
    always set. Two identical factual sentences from different passages
    produce the same ``fact_id`` and are deduplicated.
    """

    content: str
    type: str
    subject: str | None
    subject_id: str | None
    polarity: str
    modality: str
    confidence: float = Field(ge=0.0, le=1.0)
    fact_id: str


# ── fact_id derivation ───────────────────────────────────────────

def _compute_fact_id(user_id: str, content_normalized: str) -> str:
    """Deterministic fact ID from (user_id, content).

    Same hashing approach as K11.6 ``relation_id``.
    """
    raw = f"v1:{user_id}:{content_normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _normalize_content(content: str) -> str:
    """Lowercase, strip, collapse whitespace for hashing."""
    return " ".join(content.strip().lower().split())


# ── Public entry point ───────────────────────────────────────────

async def extract_facts(
    text: str,
    entities: list[LLMEntityCandidate],
    known_entities: list[str],
    *,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    client: ProviderClient | None = None,
) -> list[LLMFactCandidate]:
    """Extract factual claims from *text* via the user's BYOK LLM.

    Args:
        text: chapter or passage text. Empty/whitespace returns ``[]``
            without calling the LLM.
        entities: entity candidates from K17.4's ``extract_entities``.
            Used to resolve the optional subject to a canonical ID.
        known_entities: canonical entity names already in the graph.
            Passed through to the LLM prompt for anchoring.
        user_id: tenant scope.
        project_id: project scope (``None`` for global).
        model_source: ``"user_model"`` or ``"platform_model"``.
        model_ref: model reference key in provider-registry.
        client: injectable ``ProviderClient`` for testing.

    Returns:
        List of ``LLMFactCandidate`` sorted by confidence descending.
        Facts without a subject have ``subject=None`` /
        ``subject_id=None`` — this is valid (universal claims).

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
        "fact",
        text=safe_text,
        known_entities=safe_known,
    )

    response = await extract_json(
        FactExtractionResponse,
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        system=None,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        client=client,
    )

    return _postprocess(
        response.facts,
        entities=entities,
        known_entities=known_entities,
        user_id=user_id,
    )


# ── Post-processing ─────────────────────────────────────────────

def _build_entity_lookup(
    entities: list[LLMEntityCandidate],
) -> dict[str, LLMEntityCandidate]:
    """Case-insensitive lookup: name/alias → entity candidate."""
    lookup: dict[str, LLMEntityCandidate] = {}
    for ent in entities:
        lookup.setdefault(ent.name.lower(), ent)
        lookup.setdefault(ent.canonical_name.lower(), ent)
        for alias in ent.aliases:
            lookup.setdefault(alias.lower(), ent)
    return lookup


def _resolve_subject(
    name: str,
    lookup: dict[str, LLMEntityCandidate],
    known_lower: dict[str, str],
) -> LLMEntityCandidate | None:
    """Resolve a subject name to an entity candidate."""
    key = name.strip().lower()
    if key in lookup:
        return lookup[key]
    anchored = known_lower.get(key)
    if anchored and anchored.lower() in lookup:
        return lookup[anchored.lower()]
    return None


def _postprocess(
    raw_facts: list[_LLMFact],
    *,
    entities: list[LLMEntityCandidate],
    known_entities: list[str],
    user_id: str,
) -> list[LLMFactCandidate]:
    """Resolve subjects, derive fact_id, deduplicate."""
    entity_lookup = _build_entity_lookup(entities)
    known_lower: dict[str, str] = {
        n.strip().lower(): n.strip() for n in known_entities
    }

    seen: dict[str, LLMFactCandidate] = {}

    for fact in raw_facts:
        content = fact.content.strip()
        if not content:
            continue

        # Resolve optional subject
        subject_name: str | None = None
        subject_id: str | None = None
        if fact.subject and fact.subject.strip():
            raw_subject = fact.subject.strip()
            ent = _resolve_subject(raw_subject, entity_lookup, known_lower)
            if ent:
                subject_name = ent.name
                subject_id = ent.canonical_id
            else:
                subject_name = raw_subject

        fid = _compute_fact_id(user_id, _normalize_content(content))

        candidate = LLMFactCandidate(
            content=content,
            type=fact.type,
            subject=subject_name,
            subject_id=subject_id,
            polarity=fact.polarity,
            modality=fact.modality,
            confidence=fact.confidence,
            fact_id=fid,
        )

        # Dedup by fact_id (higher confidence wins)
        if fid in seen:
            if fact.confidence > seen[fid].confidence:
                seen[fid] = candidate
        else:
            seen[fid] = candidate

    return sorted(
        seen.values(),
        key=lambda c: (-c.confidence, c.content),
    )
