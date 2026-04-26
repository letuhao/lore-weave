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
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.clients.llm_client import LLMClient
from app.extraction.errors import ExtractionError
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_prompts import load_prompt
from app.metrics import knowledge_extraction_dropped_total
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import ChunkingConfig

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


# C18 — truncated ISO date pattern. Months 01-12, days 01-31.
# Doesn't catch Feb 30 (would need calendar awareness) but catches
# the dominant typo class.
_EVENT_DATE_RE = re.compile(
    r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$"
)


class _LLMEvent(BaseModel):
    """Single event from the LLM response — raw, pre-resolution."""

    name: str
    kind: EventKind
    participants: list[str] = []
    location: str | None = None
    time_cue: str | None = None
    # C18 (D-K19e-α-02 closer) — structured ISO date the LLM emits
    # when TEXT contains an explicit calendar date. Truncated ISO:
    # YYYY / YYYY-MM / YYYY-MM-DD. Vague hints stay in time_cue;
    # fictional eras stay in time_cue. Validator coerces malformed
    # → None rather than rejecting the whole event (the rest of the
    # event metadata is still useful even if the date is wrong-format).
    event_date: str | None = None
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("event_date", mode="before")
    @classmethod
    def _coerce_malformed_date(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            return None
        if not _EVENT_DATE_RE.match(v):
            return None
        return v


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
    ``(user_id, name_normalized, sorted_participant_display_names)``.
    Always set because events without participants are dropped.
    """

    name: str
    kind: str
    participants: list[str]
    participant_ids: list[str | None]
    location: str | None
    time_cue: str | None
    # C18 — threaded from _LLMEvent; truncated ISO or None.
    event_date: str | None = None
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    event_id: str | None


# ── event_id derivation ──────────────────────────────────────────

def _compute_event_id(
    user_id: str,
    name_normalized: str,
    display_names: list[str],
) -> str:
    """Deterministic event ID from (user_id, name, all participants).

    Hashes the full display-name list (not just resolved IDs) so that
    events with the same name but different participant lists produce
    distinct IDs — e.g. ("Battle", ["Kai", "Stranger"]) vs
    ("Battle", ["Kai"]) won't collide.
    """
    sorted_names = sorted(n.lower() for n in display_names)
    raw = f"v1:{user_id}:{name_normalized}:{','.join(sorted_names)}"
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
    llm_client: LLMClient,
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
        llm_client: loreweave_llm SDK wrapper.

    Returns:
        List of ``LLMEventCandidate`` sorted by confidence descending.
        Events whose participants cannot be resolved have
        ``participant_ids=[None, ...]`` but ``event_id`` is always
        set (hashed from display names).

    Raises:
        ExtractionError: on terminal LLM / parse / validation failure.
    """
    if not text or not text.strip():
        return []

    safe_known = json.dumps(
        known_entities, ensure_ascii=False
    ).replace("{", "{{").replace("}", "}}")

    system_prompt = load_prompt("event_system", known_entities=safe_known)
    raw_events = await _extract_via_llm_client(
        llm_client=llm_client,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        system_prompt=system_prompt,
        text=text,
    )

    return _postprocess(
        raw_events,
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

        # Compute event_id from display names (always available since
        # we filter empty participants above).
        eid = _compute_event_id(
            user_id, _normalize_event_name(name), display_names,
        )

        candidate = LLMEventCandidate(
            name=name,
            kind=evt.kind,
            participants=display_names,
            participant_ids=participant_ids,
            location=evt.location,
            time_cue=evt.time_cue,
            event_date=evt.event_date,
            summary=summary,
            confidence=evt.confidence,
            event_id=eid,
        )

        # Dedup by event_id (higher confidence wins)
        if eid in seen:
            if evt.confidence > seen[eid].confidence:
                seen[eid] = candidate
        else:
            seen[eid] = candidate

    return sorted(
        seen.values(),
        key=lambda c: (-c.confidence, c.name),
    )


# ── Phase 4a-β SDK-routed path ────────────────────────────────────────


async def _extract_via_llm_client(
    *,
    llm_client: LLMClient,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    system_prompt: str,
    text: str,
) -> list[_LLMEvent]:
    """Submit event_extraction job + wait_terminal + tolerant-parse
    `result.events`. Mirrors entity extractor's SDK path."""
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="event_extraction",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            },
            chunking=ChunkingConfig(strategy="paragraphs", size=15),
            job_meta={
                "extractor": "event",
                "project_id": project_id or "",
            },
            transient_retry_budget=1,
        )
    except LLMTransientRetryNeededError as exc:
        raise ExtractionError(
            f"event_extraction failed after transient retry: {exc.underlying_code}",
            stage="provider_exhausted",
            last_error=exc,
        ) from exc
    except LLMError as exc:
        raise ExtractionError(
            f"event_extraction SDK error: {exc}",
            stage="provider",
            last_error=exc,
        ) from exc

    if job.status == "cancelled":
        raise ExtractionError(
            f"event_extraction job cancelled (job_id={job.job_id})",
            stage="cancelled",  # type: ignore[arg-type]
        )
    if job.status != "completed":
        err_code = job.error.code if job.error else "LLM_UNKNOWN_ERROR"
        err_msg = job.error.message if job.error else ""
        raise ExtractionError(
            f"event_extraction job ended status={job.status} code={err_code}: {err_msg}",
            stage="provider",
        )

    raw_items: list[Any] = []
    if job.result is not None:
        items = job.result.get("events", [])
        if isinstance(items, list):
            raw_items = items
    return _tolerant_parse_events(raw_items)


def _tolerant_parse_events(raw_items: list[Any]) -> list[_LLMEvent]:
    """Drop items missing `name` or `summary` or `confidence`; tolerate
    null location/time_cue/event_date (validator coerces malformed
    event_date to None — preserved); clamp confidence; drop on enum
    validation failure (kind not in EventKind Literal)."""
    parsed: list[_LLMEvent] = []
    for item in raw_items:
        if not isinstance(item, dict):
            knowledge_extraction_dropped_total.labels(
                operation="event_extraction", reason="validation"
            ).inc()
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            knowledge_extraction_dropped_total.labels(
                operation="event_extraction", reason="missing_name"
            ).inc()
            continue
        summary = item.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            knowledge_extraction_dropped_total.labels(
                operation="event_extraction", reason="missing_kind"
            ).inc()
            continue
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))
        participants = item.get("participants") or []
        if not isinstance(participants, list):
            participants = []
        try:
            parsed.append(_LLMEvent(
                name=name,
                kind=item.get("kind", "other"),  # Literal validates
                participants=[p for p in participants if isinstance(p, str)],
                location=item.get("location"),
                time_cue=item.get("time_cue"),
                event_date=item.get("event_date"),  # _coerce_malformed_date validator
                summary=summary,
                confidence=confidence,
            ))
        except ValidationError:
            knowledge_extraction_dropped_total.labels(
                operation="event_extraction", reason="validation"
            ).inc()
            continue
    return parsed
