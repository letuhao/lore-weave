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
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.clients.llm_client import LLMClient
from app.clients.provider_client import ProviderClient
from app.db.neo4j_repos.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)
from app.extraction.llm_json_parser import ExtractionError, extract_json
from app.extraction.llm_prompts import load_prompt
from app.metrics import knowledge_extraction_dropped_total
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import ChunkingConfig

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
    llm_client: LLMClient | None = None,
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
        client: injectable ``ProviderClient`` for testing of the legacy
            K17.2 path. Used when ``llm_client`` is None (back-compat
            during 4a-α; removed in 4a-δ).
        llm_client: Phase 4a-α — when supplied, routes the extraction
            through the loreweave_llm SDK (job pattern + chunking +
            gateway-side retry + per-op JSON aggregator). When None,
            falls back to the legacy K17.2 sync path.

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
            (propagated from K17.3 OR synthesized from new path).
    """
    if not text or not text.strip():
        return []

    # I1/I7 (R2): escape curly braces in caller-supplied values before
    # substitution. load_prompt uses str.format_map internally — literal
    # { or } in the text (common in code-quoting novels, system-prompt
    # fiction, or entity names like "The {Ancient} One") would be
    # misinterpreted as format placeholders and raise KeyError.
    safe_known = json.dumps(
        known_entities, ensure_ascii=False
    ).replace("{", "{{").replace("}", "}}")

    if llm_client is not None:
        # Phase 4a-α-followup: route through SDK with system+user
        # messages so the gateway chunker can split the user message
        # (chapter text) without shredding the system instructions.
        # Unlike the legacy combined-template path, the SDK path does
        # NOT escape `{`/`}` in `text` because we pass it directly as
        # the user message content — no str.format_map() runs on it.
        system_prompt = load_prompt("entity_system", known_entities=safe_known)
        raw_entities = await _extract_via_llm_client(
            llm_client=llm_client,
            user_id=user_id,
            project_id=project_id,
            model_source=model_source,
            model_ref=model_ref,
            system_prompt=system_prompt,
            text=text,
        )
    else:
        # Legacy K17.2 path — preserved through 4a-α, removed in 4a-δ.
        # Combined-template format requires `{}`-escape in text.
        safe_text = text.replace("{", "{{").replace("}", "}}")
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
        raw_entities = response.entities

    return _postprocess(
        raw_entities,
        user_id=user_id,
        project_id=project_id,
        known_entities=known_entities,
    )


# ── Phase 4a-α Step 2 — new SDK-routed path ─────────────────────────


async def _extract_via_llm_client(
    *,
    llm_client: LLMClient,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    system_prompt: str,
    text: str,
) -> list["_LLMEntity"]:
    """Submit entity_extraction job + wait_terminal + tolerant-parse the
    `result.entities` envelope into a list of `_LLMEntity` records.

    Uses caller-side retry budget (1) per ADR §3.3 D3c bridge. On
    transient retry exhaustion or non-transient failure, raises
    ExtractionError so the orchestrator can surface a job-level error.

    **Phase 4a-α-followup — chunking IS enabled.** Messages are
    structured as ``[{role:system, content:system_prompt}, {role:user,
    content:text}]``. The gateway's ``ExtractChattableText`` finds the
    LAST user message and chunks ITS content; system messages are
    preserved verbatim across all per-chunk dispatches via
    ``SubstituteLastUserMessage`` (which only mutates the user message).
    So chunks 0..N each receive: full instructions + KNOWN_ENTITIES
    (in system) + their slice of chapter text (in user). The cycle 20
    jsonListAggregator then dedups entities across chunks by
    ``(name, kind)`` with higher confidence winning on ties.

    ChunkingConfig(strategy='paragraphs', size=15) per ADR §6 Q1
    recommendation: 15 paragraphs covers most chapters in a single
    chunk while bounding chunk-0 size for the rare 70+ paragraph
    chapter (Speckled Band ≈ 70 → ~5 chunks).

    Per ADR §3.3 D6 — `job_meta` carries the reverse-lookup keys so a
    future business-job query can find all LLM jobs for an extraction.
    """
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="entity_extraction",
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
                "extractor": "entity",
                "project_id": project_id or "",
            },
            transient_retry_budget=1,
        )
    except LLMTransientRetryNeededError as exc:
        raise ExtractionError(
            f"entity_extraction failed after transient retry: {exc.underlying_code}",
            stage="provider_exhausted",
            last_error=exc,
        ) from exc
    except LLMError as exc:
        raise ExtractionError(
            f"entity_extraction SDK error: {exc}",
            stage="provider",
            last_error=exc,
        ) from exc

    if job.status == "cancelled":
        # /review-impl MED#3 fix — cancelled job MUST surface as a
        # distinct terminal so orchestrator can flip extraction_jobs
        # status correctly, NOT collapse to "0 entities found" which
        # would lie to the user about cancel result. Raise with a
        # `cancelled` stage marker; orchestrator/runner can handle.
        raise ExtractionError(
            f"entity_extraction job cancelled (job_id={job.job_id})",
            stage="cancelled",  # type: ignore[arg-type]
        )

    if job.status != "completed":
        err_code = job.error.code if job.error else "LLM_UNKNOWN_ERROR"
        err_msg = job.error.message if job.error else ""
        raise ExtractionError(
            f"entity_extraction job ended status={job.status} code={err_code}: {err_msg}",
            stage="provider",
        )

    raw_items: list[Any] = []
    if job.result is not None:
        items = job.result.get("entities", [])
        if isinstance(items, list):
            raw_items = items

    return _tolerant_parse_entities(raw_items)


def _tolerant_parse_entities(raw_items: list[Any]) -> list["_LLMEntity"]:
    """Per /review-impl LOW#11 — required name+kind; optional aliases
    (default []) + confidence (default 0.5). Items missing required
    fields are dropped + counted in metrics so quality regressions
    surface in dashboards before users notice missing entities.

    `evidence_passage_id` is mentioned in the ADR as required-by-anchoring
    BUT the current K17.4 prompt doesn't ask for it (anchoring uses
    canonical_name match against `known_entities` instead). Leaving as
    optional for 4a-α parity with legacy path; revisit when anchor
    loader changes (Phase 4a-β or later)."""
    parsed: list[_LLMEntity] = []
    for item in raw_items:
        if not isinstance(item, dict):
            knowledge_extraction_dropped_total.labels(
                operation="entity_extraction", reason="validation"
            ).inc()
            continue
        name = item.get("name")
        kind = item.get("kind")
        if not isinstance(name, str) or not name.strip():
            knowledge_extraction_dropped_total.labels(
                operation="entity_extraction", reason="missing_name"
            ).inc()
            continue
        if not isinstance(kind, str) or not kind.strip():
            knowledge_extraction_dropped_total.labels(
                operation="entity_extraction", reason="missing_kind"
            ).inc()
            continue
        # Defaults for optional fields per ADR §5.1 Step 3.
        aliases = item.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        # Clamp confidence to [0, 1] so a sloppy LLM emitting 1.2 doesn't
        # trip the Pydantic ge/le validator below.
        confidence = max(0.0, min(1.0, float(confidence)))
        try:
            parsed.append(_LLMEntity(
                name=name,
                kind=kind,  # type: ignore[arg-type]  — Literal validated by Pydantic
                aliases=[a for a in aliases if isinstance(a, str)],
                confidence=confidence,
            ))
        except ValidationError:
            # Wrong-shape kind (not in EntityKind Literal) lands here.
            knowledge_extraction_dropped_total.labels(
                operation="entity_extraction", reason="validation"
            ).inc()
            continue
    return parsed


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
