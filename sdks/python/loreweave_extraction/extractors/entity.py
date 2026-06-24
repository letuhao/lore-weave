"""LLM-powered entity extractor (moved from knowledge-service in Phase 4b-α).

Extracts named entities from text using a BYOK LLM via the
loreweave_llm SDK (job pattern + chunking + per-op JSON aggregator).
Returns post-processed candidates with deterministic canonical IDs
so re-running extraction on the same source is idempotent.

**This module does NOT write to Neo4j.** It produces
`LLMEntityCandidate` records that the caller (knowledge-service Pass 2
writer, or any future persistence service) feeds into its own write
layer.

**Relationship to pattern-based detectors:** the LLM extractor is
typically Pass 2 (higher confidence, multilingual). Pass 1 (regex /
heuristic) results live in the caller; this library does not own
reconciliation across passes.

Dependencies: loreweave_llm SDK, loreweave_extraction prompts +
canonical helpers + errors + protocol types.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import ChunkingConfig

from loreweave_extraction._types import DroppedHandler, LLMClientProtocol
from loreweave_extraction.context_budget import (
    ContextBudget,
    estimate_text_tokens,
)
from loreweave_extraction.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)
from loreweave_extraction.errors import ExtractionError
from loreweave_extraction.prompts import (
    append_schema_constraints,
    apply_prompt_override,
    load_prompt,
)
from loreweave_extraction.reasoning_wire import reasoning_wire_fields
from loreweave_extraction.schema_projection import ExtractionSchema

__all__ = [
    "EntityExtractionResponse",
    "LLMEntityCandidate",
    "extract_entities",
]

logger = logging.getLogger(__name__)

# ── LLM response schema (matches entity_extraction.md prompt) ────────

# Static default vocab — the SDK's historical hardcoded ontology, preserved
# byte-for-byte for the `schema=None` path (backward-compat: worker-ai +
# translation never pass a schema). When a dynamic ExtractionSchema IS passed,
# validation accepts the schema's `entity_kinds` instead (fail-soft).
EntityKind = Literal[
    "person", "place", "organization", "artifact", "concept", "other"
]

_STATIC_ENTITY_KINDS: frozenset[str] = frozenset(
    {"person", "place", "organization", "artifact", "concept", "other"}
)


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

    Ready for the persistence layer (knowledge-service write_pass2_extraction
    or any equivalent). `canonical_id` is derived via `entity_canonical_id`
    so re-running extraction on the same source text produces the same
    IDs — idempotent.
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
    llm_client: LLMClientProtocol,
    on_dropped: DroppedHandler | None = None,
    context_budget: "ContextBudget | None" = None,
    prompt_override_system: str | None = None,
    schema: ExtractionSchema | None = None,
    # D-KG-WORKER-GRADED-EFFORT — graded reasoning effort threaded to the
    # submit builder. Default "none" ⇒ no wire fields (back-compat).
    reasoning_effort: str = "none",
) -> list[LLMEntityCandidate]:
    """Extract named entities from *text* via the user's BYOK LLM.

    ``schema`` (KG customizable-ontology, lane LB): when ``None`` (default —
    worker-ai + translation never pass it) the static ``EntityKind`` ``Literal``
    governs validation and the prompt is byte-identical to the historical
    ``.md``. When an :class:`ExtractionSchema` is passed, its ``entity_kinds``
    are injected into the prompt and accepted by validation instead.

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
        llm_client: any object satisfying ``LLMClientProtocol``
            (knowledge-service's `LLMClient` wrapper, or a custom
            adapter around `loreweave_llm.Client`).
        on_dropped: optional callback invoked once per dropped item
            with ``(operation, reason)`` — wire to your Prometheus
            counter for quality observability.

    Returns:
        Deduplicated list of ``LLMEntityCandidate`` sorted by
        confidence descending. Deduplication is by ``canonical_id``,
        which hashes ``(user_id, project_id, name, kind)``. Two
        candidates CAN share the same display ``name`` if their
        ``kind`` differs (e.g. "Kai" as person vs. concept). The
        caller is responsible for reconciling same-name-different-
        kind duplicates if that's undesirable.

    Raises:
        ExtractionError: on terminal LLM / parse / validation failure.
    """
    if not text or not text.strip():
        return []

    # build_entity_system handles curly-brace escaping of known_entities
    # (load_prompt uses str.format_map; literal { or } in a known-entity name
    # like "The {Ancient} One" would otherwise raise KeyError). `text` rides
    # the user message verbatim — never format_map'd.
    system_prompt = build_entity_system(
        known_entities, prompt_override_system, schema=schema,
    )
    raw_entities = await _extract_via_llm_client(
        llm_client=llm_client,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        system_prompt=system_prompt,
        text=text,
        on_dropped=on_dropped,
        context_budget=context_budget,
        reasoning_effort=reasoning_effort,
        schema=schema,
    )

    return _postprocess(
        raw_entities,
        user_id=user_id,
        project_id=project_id,
        known_entities=known_entities,
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
    context_budget: ContextBudget | None = None,
    schema: ExtractionSchema | None = None,
    reasoning_effort: str = "none",
) -> list["_LLMEntity"]:
    """Submit entity_extraction job + wait_terminal + tolerant-parse the
    `result.entities` envelope into a list of `_LLMEntity` records.

    Uses caller-side retry budget (1) for transient errors. On retry
    exhaustion or non-transient failure, raises ExtractionError so the
    orchestrator can surface a job-level error.

    **Chunking is enabled.** Messages are structured as
    ``[{role:system, content:system_prompt}, {role:user, content:text}]``.
    The gateway's ``ExtractChattableText`` finds the LAST user message
    and chunks ITS content; system messages are preserved verbatim
    across all per-chunk dispatches via ``SubstituteLastUserMessage``
    (which only mutates the user message). So chunks 0..N each
    receive: full instructions + KNOWN_ENTITIES (in system) + their
    slice of chapter text (in user). The gateway's jsonListAggregator
    then dedups entities across chunks by ``(name, kind)`` with higher
    confidence winning on ties.

    ChunkingConfig(strategy='paragraphs', size=15) — 15 paragraphs
    covers most chapters in a single chunk while bounding chunk-0 size
    for the rare 70+ paragraph chapter (e.g. Speckled Band ≈ 70 →
    ~5 chunks).

    `job_meta` carries the reverse-lookup keys so a future business-
    job query can find all LLM jobs for an extraction.

    Chunk size derivation: when ``context_budget`` is supplied, the
    chunk size is computed from the model's loaded context — accounts
    for the system prompt length AND CJK token density (Vietnamese /
    Chinese pack ~4× more tokens per paragraph than English). When
    omitted (legacy callers + tests), falls back to the original
    hardcoded ``size=15``.
    """
    kwargs = build_entity_submit_kwargs(
        system_prompt=system_prompt, text=text, model_source=model_source,
        model_ref=model_ref, project_id=project_id, context_budget=context_budget,
        reasoning_effort=reasoning_effort,
    )
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id, transient_retry_budget=1, **kwargs,
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

    return parse_entity_job(job, on_dropped=on_dropped, schema=schema)


# ── Decouple seams (LLM re-arch Phase 2b WX-T2) ─────────────────────
# The submit-request build + the terminal-Job parse are split into pure functions
# so the SYNCHRONOUS path above and the DECOUPLED orchestrator (worker-ai WX-T3)
# build/parse identically — the decoupled path uses submit_job (fire-and-forget)
# + parse_entity_job on the terminal event. No behavior change for the sync path.


def build_entity_submit_kwargs(
    *,
    system_prompt: str,
    text: str,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    project_id: str | None,
    context_budget: ContextBudget | None = None,
    # D-KG-WORKER-GRADED-EFFORT — graded reasoning effort. Default "none" emits
    # NO wire fields (byte-identical for every caller that doesn't opt in); a
    # graded value spreads {reasoning_effort, chat_template_kwargs}.
    reasoning_effort: str = "none",
) -> dict[str, Any]:
    """Pure: the submit_and_wait / submit_job kwargs for an entity_extraction job
    (operation/model/input/chunking/job_meta — NOT user_id, which is per-call)."""
    if context_budget is not None:
        sys_tokens = estimate_text_tokens(system_prompt)
        chunk_size = context_budget.max_paragraphs_per_chunk(
            system_prompt_tokens=sys_tokens,
            lang="auto",
        )
    else:
        chunk_size = 15
    return dict(
        operation="entity_extraction",
        model_source=model_source,
        model_ref=model_ref,
        input={
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "response_format": {"type": "text"},
            "temperature": 0.0,
            # Cap output so LM Studio (+ similar slot-based servers) doesn't
            # reserve the full context window per slot. Without this, the parallel
            # R+E+F gather (3 concurrent jobs) made llama.cpp reserve ~3×model_ctx
            # of KV cache → GPU OOM. 4096 fits a generous JSON envelope for
            # 15-paragraph chunks.
            "max_tokens": (
                context_budget.max_output_tokens
                if context_budget is not None
                else 4096
            ),
            # D-KG-WORKER-GRADED-EFFORT — graded effort → reasoning wire fields
            # ({} for the default "none", so unchanged for non-opt-in callers).
            **reasoning_wire_fields(reasoning_effort),
        },
        chunking=ChunkingConfig(strategy="paragraphs", size=chunk_size),
        job_meta={
            "extractor": "entity",
            "project_id": project_id or "",
        },
    )


def parse_entity_job(
    job: Any, *, on_dropped: DroppedHandler | None,
    schema: ExtractionSchema | None = None,
) -> list["_LLMEntity"]:
    """Pure: validate the terminal Job + tolerant-parse `result.entities`. Cancelled
    / non-completed surface as ExtractionError (so the caller flips job status
    correctly rather than reporting a false '0 entities found')."""
    if job.status == "cancelled":
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
    return _tolerant_parse_entities(raw_items, on_dropped=on_dropped, schema=schema)


def build_entity_system(
    known_entities: list[str], prompt_override_system: str | None = None,
    *, schema: ExtractionSchema | None = None,
) -> str:
    """Pure: the entity system prompt (WX-T2d). Same as extract_entities builds —
    so the decoupled orchestrator assembles an identical submit.

    ``schema=None`` (default) → byte-identical to the historical static prompt.
    A non-None schema appends the project ontology's entity-kind vocab BEFORE
    the override-contract logic (lane LB)."""
    safe_known = json.dumps(known_entities, ensure_ascii=False).replace("{", "{{").replace("}", "}}")
    default_system = append_schema_constraints(
        load_prompt("entity_system", known_entities=safe_known), "entity", schema,
    )
    return apply_prompt_override(default_system, prompt_override_system)


def apply_entity_job(
    job: Any, *, on_dropped: DroppedHandler | None,
    user_id: str, project_id: str | None, known_entities: list[str],
    schema: ExtractionSchema | None = None,
) -> list[LLMEntityCandidate]:
    """Parse + postprocess an entity terminal Job (WX-T2d) = parse_entity_job →
    _postprocess. Identical to extract_entities' tail."""
    return _postprocess(
        parse_entity_job(job, on_dropped=on_dropped, schema=schema),
        user_id=user_id, project_id=project_id, known_entities=known_entities,
    )


def _kind_accepted(
    kind: str, schema: ExtractionSchema | None, static: frozenset[str],
) -> bool:
    """Dynamic-vs-static vocab gate (fail-soft).

    ``schema=None`` → accept iff in the static ``Literal`` set (today's
    behavior). With a schema: accept iff in the schema's vocab; an EMPTY schema
    vocab accepts anything (a partial projection must never be STRICTER than the
    static path — §schema_projection). Comparison is case-insensitive on the
    code slug."""
    if schema is None:
        return kind in static
    vocab = schema.entity_kinds
    if not vocab:
        return True
    low = kind.strip().lower()
    return any(low == v.strip().lower() for v in vocab)


def _tolerant_parse_entities(
    raw_items: list[Any],
    *,
    on_dropped: DroppedHandler | None,
    schema: ExtractionSchema | None = None,
) -> list["_LLMEntity"]:
    """Required name+kind; optional aliases (default []) + confidence
    (default 0.5). Items missing required fields are dropped + counted
    via `on_dropped` so quality regressions surface in dashboards
    before users notice missing entities.

    ``schema=None`` validates ``kind`` against the static ``EntityKind``
    ``Literal`` (via the ``_LLMEntity`` Pydantic model). With a schema, ``kind``
    is validated against ``schema.entity_kinds`` (fail-soft: off-vocab → drop +
    ``on_dropped``), bypassing the ``Literal`` so a custom kind is accepted.
    """
    parsed: list[_LLMEntity] = []
    for item in raw_items:
        if not isinstance(item, dict):
            if on_dropped:
                on_dropped("entity_extraction", "validation")
            continue
        name = item.get("name")
        kind = item.get("kind")
        if not isinstance(name, str) or not name.strip():
            if on_dropped:
                on_dropped("entity_extraction", "missing_name")
            continue
        if not isinstance(kind, str) or not kind.strip():
            if on_dropped:
                on_dropped("entity_extraction", "missing_kind")
            continue
        # Defaults for optional fields.
        aliases = item.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        # Clamp confidence to [0, 1] so a sloppy LLM emitting 1.2 doesn't
        # trip the Pydantic ge/le validator below.
        confidence = max(0.0, min(1.0, float(confidence)))
        if schema is not None:
            # Dynamic path — validate kind against the projected vocab WITHOUT
            # the Literal (which would reject a custom kind). model_construct
            # skips Pydantic validation so a schema kind isn't re-checked
            # against EntityKind. Off-vocab → fail-soft drop.
            if not _kind_accepted(kind, schema, _STATIC_ENTITY_KINDS):
                if on_dropped:
                    on_dropped("entity_extraction", "validation")
                continue
            parsed.append(_LLMEntity.model_construct(
                name=name,
                kind=kind,  # type: ignore[arg-type]
                aliases=[a for a in aliases if isinstance(a, str)],
                confidence=confidence,
            ))
            continue
        try:
            parsed.append(_LLMEntity(
                name=name,
                kind=kind,  # type: ignore[arg-type]  — Literal validated by Pydantic
                aliases=[a for a in aliases if isinstance(a, str)],
                confidence=confidence,
            ))
        except ValidationError:
            # Wrong-shape kind (not in EntityKind Literal) lands here.
            if on_dropped:
                on_dropped("entity_extraction", "validation")
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
