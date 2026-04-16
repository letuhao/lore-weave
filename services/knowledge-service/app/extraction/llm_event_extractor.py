"""K17.6 — LLM-powered event extractor.

Extracts narrative events (time-indexed happenings with participants)
from text using a BYOK LLM via the K17.1→K17.3 stack. Post-processes
with participant resolution (resolving participant names to K17.4
entity canonical IDs) and deterministic ``event_id`` derivation.

**This module does NOT write to Neo4j.** It produces
``LLMEventCandidate`` records that K17.8 (Pass 2 orchestrator)
feeds into the write layer.

**Relationship to K15.3 (pattern-based event extractor):**
  - K15.3 is Pass 1 (regex, English-only, quarantined)
  - K17.6 is Pass 2 (LLM, multilingual, higher confidence)
  - Both produce event lists; K17.8 orchestrator reconciles.

**Entity resolution:** K17.8 runs K17.4 (entity extraction) first,
then passes the resulting ``LLMEntityCandidate`` list to K17.6 so
participant names can be resolved to canonical IDs.

Dependencies: K17.1 (prompt loader), K17.3 (extract_json), K17.4
(LLMEntityCandidate).

Reference: KSA §5.1, K17.6 plan row in
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
    "LLMEventCandidate",
    "EventExtractionResponse",
    "extract_events",
]

logger = logging.getLogger(__name__)

# ── LLM response schema (matches event_extraction.md prompt) ──────

EventKind = Literal[
    "action", "dialogue", "battle", "travel",
    "discovery", "death", "birth", "other",
]


class _LLMEvent(BaseModel):
    """Single event from the LLM response — raw, pre-resolution."""

    name: str
    kind: EventKind
    participants: list[str] = []
    location: str | None = None
    time_cue: str | None = None
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class EventExtractionResponse(BaseModel):
    """Outer wrapper matching the JSON schema in event_extraction.md."""

    events: list[_LLMEvent] = []


# ── Post-processed output model ──────────────────────────────────

class LLMEventCandidate(BaseModel):
    """Event candidate with resolved participant IDs.

    ``participant_ids`` mirrors ``participants`` positionally: each
    entry is the canonical entity ID when resolved, ``None`` when
    the participant could not be matched against K17.4 output.

    ``event_id`` is a deterministic hash of
    ``(user_id, name_normalized, sorted_resolved_participant_ids)``
    — only set when at least one participant is resolved. Events
    with zero resolved participants get ``event_id=None``; the
    caller decides whether to create ad-hoc entity nodes or drop.
    """

    name: str
    kind: str
    participants: list[str]
    participant_ids: list[str | None]
    location: str | None
    time_cue: str | None
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    event_id: str | None


# ── event_id derivation ──────────────────────────────────────────

def _compute_event_id(
    user_id: str,
    name_normalized: str,
    resolved_ids: list[str],
) -> str:
    """Deterministic event ID from (user_id, name, participants).

    Same hashing approach as K11.6 ``relation_id``.
    """
    sorted_ids = sorted(resolved_ids)
    raw = f"v1:{user_id}:{name_normalized}:{','.join(sorted_ids)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _normalize_event_name(name: str) -> str:
    """Lowercase, strip for dedup/hashing purposes."""
    return name.strip().lower()


# ── Public entry point ───────────────────────────────────────────

async def extract_events(
    text: str,
    entities: list[LLMEntityCandidate],
    known_entities: list[str],
    *,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    client: ProviderClient | None = None,
) -> list[LLMEventCandidate]:
    """Extract narrative events from *text* via the user's BYOK LLM.

    Args:
        text: chapter or passage text. Empty/whitespace returns ``[]``
            without calling the LLM.
        entities: entity candidates from K17.4's ``extract_entities``.
            Used to resolve participant names to canonical IDs.
        known_entities: canonical entity names already in the graph.
            Passed through to the LLM prompt for anchoring.
        user_id: tenant scope.
        project_id: project scope (``None`` for global).
        model_source: ``"user_model"`` or ``"platform_model"``.
        model_ref: model reference key in provider-registry.
        client: injectable ``ProviderClient`` for testing.

    Returns:
        List of ``LLMEventCandidate`` sorted by confidence descending.
        Events whose participants cannot be resolved have
        ``participant_ids=[None, ...]`` / ``event_id=None``.

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
        "event",
        text=safe_text,
        known_entities=safe_known,
    )

    response = await extract_json(
        EventExtractionResponse,
        user_id=user_id,
        model_source=model_source,
        model_ref=model_ref,
        system=None,
        user_prompt=user_prompt,
        response_format={"type": "json_object"},
        client=client,
    )

    return _postprocess(
        response.events,
        entities=entities,
        known_entities=known_entities,
        user_id=user_id,
    )


# ── Post-processing ─────────────────────────────────────────────

def _build_entity_lookup(
    entities: list[LLMEntityCandidate],
) -> dict[str, LLMEntityCandidate]:
    """Case-insensitive lookup: name/alias → entity candidate.

    Same pattern as K17.5's ``_build_entity_lookup``.
    """
    lookup: dict[str, LLMEntityCandidate] = {}
    for ent in entities:
        lookup.setdefault(ent.name.lower(), ent)
        lookup.setdefault(ent.canonical_name.lower(), ent)
        for alias in ent.aliases:
            lookup.setdefault(alias.lower(), ent)
    return lookup


def _resolve_participant(
    name: str,
    lookup: dict[str, LLMEntityCandidate],
    known_lower: dict[str, str],
) -> LLMEntityCandidate | None:
    """Resolve a participant name to an entity candidate."""
    key = name.strip().lower()
    if key in lookup:
        return lookup[key]
    anchored = known_lower.get(key)
    if anchored and anchored.lower() in lookup:
        return lookup[anchored.lower()]
    return None


def _postprocess(
    raw_events: list[_LLMEvent],
    *,
    entities: list[LLMEntityCandidate],
    known_entities: list[str],
    user_id: str,
) -> list[LLMEventCandidate]:
    """Resolve participants, derive event_id, deduplicate."""
    entity_lookup = _build_entity_lookup(entities)
    known_lower: dict[str, str] = {
        n.strip().lower(): n.strip() for n in known_entities
    }

    seen: dict[str, LLMEventCandidate] = {}

    for evt in raw_events:
        name = evt.name.strip()
        if not name:
            continue

        summary = evt.summary.strip()
        if not summary:
            continue

        # Filter events with no participants (prompt rule 2)
        participants_raw = [p.strip() for p in evt.participants if p.strip()]
        if not participants_raw:
            continue

        # Resolve each participant
        display_names: list[str] = []
        participant_ids: list[str | None] = []
        for p_name in participants_raw:
            ent = _resolve_participant(p_name, entity_lookup, known_lower)
            if ent:
                display_names.append(ent.name)
                participant_ids.append(ent.canonical_id)
            else:
                display_names.append(p_name)
                participant_ids.append(None)

        # Compute event_id when at least one participant resolved
        resolved_ids = [pid for pid in participant_ids if pid is not None]
        eid: str | None = None
        if resolved_ids:
            eid = _compute_event_id(
                user_id, _normalize_event_name(name), resolved_ids,
            )

        candidate = LLMEventCandidate(
            name=name,
            kind=evt.kind,
            participants=display_names,
            participant_ids=participant_ids,
            location=evt.location,
            time_cue=evt.time_cue,
            summary=summary,
            confidence=evt.confidence,
            event_id=eid,
        )

        # Dedup by event_id (higher confidence wins)
        if eid:
            if eid in seen:
                if evt.confidence > seen[eid].confidence:
                    seen[eid] = candidate
            else:
                seen[eid] = candidate
        else:
            synth_key = (
                f"{_normalize_event_name(name)}"
                f":{':'.join(sorted(p.lower() for p in display_names))}"
            )
            if synth_key not in seen or evt.confidence > seen[synth_key].confidence:
                seen[synth_key] = candidate

    return sorted(
        seen.values(),
        key=lambda c: (-c.confidence, c.name),
    )
