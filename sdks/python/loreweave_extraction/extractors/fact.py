"""LLM-powered fact extractor (moved from knowledge-service in Phase 4b-α).

Extracts standalone factual claims from text using a BYOK LLM via the
loreweave_llm SDK (job pattern + chunking + per-op JSON aggregator).
Post-processes with subject resolution (resolving the optional
subject name to an entity canonical ID) and deterministic
``fact_id`` derivation.

**This module does NOT write to Neo4j.** It produces
``LLMFactCandidate`` records that the caller (knowledge-service
Pass 2 writer, or any future persistence service) feeds into its own
write layer.

**Relationship to pattern-based detectors:** the LLM extractor is
typically Pass 2 (higher confidence, multilingual). Pass 1 (regex /
heuristic) results live in the caller; this library does not own
reconciliation across passes.

**Entity resolution:** the caller runs ``extract_entities`` first,
then passes the resulting ``LLMEntityCandidate`` list here so the
optional subject name can be resolved to a canonical ID.

Dependencies: loreweave_llm SDK, loreweave_extraction prompts +
canonical helpers + errors + protocol types.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import ChunkingConfig

from loreweave_extraction._types import DroppedHandler, LLMClientProtocol
from loreweave_extraction.errors import ExtractionError
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.prompts import load_prompt

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

    Same hashing approach as canonical ``relation_id``.
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
    llm_client: LLMClientProtocol,
    on_dropped: DroppedHandler | None = None,
) -> list[LLMFactCandidate]:
    """Extract factual claims from *text* via the user's BYOK LLM.

    Args:
        text: chapter or passage text. Empty/whitespace returns ``[]``
            without calling the LLM.
        entities: entity candidates from ``extract_entities``. Used to
            resolve the optional subject to a canonical ID.
        known_entities: canonical entity names already in the graph.
            Passed through to the LLM prompt for anchoring.
        user_id: tenant scope.
        project_id: project scope (``None`` for global).
        model_source: ``"user_model"`` or ``"platform_model"``.
        model_ref: model reference key in provider-registry.
        llm_client: any object satisfying ``LLMClientProtocol``.
        on_dropped: optional callback invoked once per dropped item
            with ``(operation, reason)`` — wire to your Prometheus
            counter for quality observability.

    Returns:
        List of ``LLMFactCandidate`` sorted by confidence descending.
        Facts without a subject have ``subject=None`` /
        ``subject_id=None`` — this is valid (universal claims).

    Raises:
        ExtractionError: on terminal LLM / parse / validation failure.
    """
    if not text or not text.strip():
        return []

    safe_known = json.dumps(
        known_entities, ensure_ascii=False
    ).replace("{", "{{").replace("}", "}}")

    system_prompt = load_prompt("fact_system", known_entities=safe_known)
    raw_facts = await _extract_via_llm_client(
        llm_client=llm_client,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        system_prompt=system_prompt,
        text=text,
        on_dropped=on_dropped,
    )

    return _postprocess(
        raw_facts,
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


# ── SDK-routed path ─────────────────────────────────────────────────


async def _extract_via_llm_client(
    *,
    llm_client: LLMClientProtocol,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    system_prompt: str,
    text: str,
    on_dropped: DroppedHandler | None,
) -> list[_LLMFact]:
    """Submit fact_extraction job + wait_terminal + tolerant-parse
    `result.facts`. Mirrors entity extractor's SDK path."""
    project_id_meta = project_id or ""  # keep job_meta JSON-stringifiable
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="fact_extraction",
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
                "extractor": "fact",
                "project_id": project_id_meta,
            },
            transient_retry_budget=1,
        )
    except LLMTransientRetryNeededError as exc:
        raise ExtractionError(
            f"fact_extraction failed after transient retry: {exc.underlying_code}",
            stage="provider_exhausted",
            last_error=exc,
        ) from exc
    except LLMError as exc:
        raise ExtractionError(
            f"fact_extraction SDK error: {exc}",
            stage="provider",
            last_error=exc,
        ) from exc

    if job.status == "cancelled":
        raise ExtractionError(
            f"fact_extraction job cancelled (job_id={job.job_id})",
            stage="cancelled",  # type: ignore[arg-type]
        )
    if job.status != "completed":
        err_code = job.error.code if job.error else "LLM_UNKNOWN_ERROR"
        err_msg = job.error.message if job.error else ""
        raise ExtractionError(
            f"fact_extraction job ended status={job.status} code={err_code}: {err_msg}",
            stage="provider",
        )

    raw_items: list[Any] = []
    if job.result is not None:
        items = job.result.get("facts", [])
        if isinstance(items, list):
            raw_items = items
    return _tolerant_parse_facts(raw_items, on_dropped=on_dropped)


def _tolerant_parse_facts(
    raw_items: list[Any],
    *,
    on_dropped: DroppedHandler | None,
) -> list[_LLMFact]:
    """Drop items missing `content` or with empty content; tolerate
    null subject; clamp confidence; drop on FactType validation
    failure (kind not in Literal)."""
    parsed: list[_LLMFact] = []
    for item in raw_items:
        if not isinstance(item, dict):
            if on_dropped:
                on_dropped("fact_extraction", "validation")
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            if on_dropped:
                on_dropped("fact_extraction", "missing_name")
            continue
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))
        try:
            parsed.append(_LLMFact(
                content=content,
                type=item.get("type", "description"),  # FactType Literal validates
                subject=item.get("subject"),
                polarity=item.get("polarity", "affirm"),
                modality=item.get("modality", "asserted"),
                confidence=confidence,
            ))
        except ValidationError:
            if on_dropped:
                on_dropped("fact_extraction", "validation")
            continue
    return parsed
