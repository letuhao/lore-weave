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
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.clients.llm_client import LLMClient
from app.clients.provider_client import ProviderClient
from app.db.neo4j_repos.relations import relation_id as compute_relation_id
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_json_parser import ExtractionError, extract_json
from app.extraction.llm_prompts import load_prompt
from app.metrics import knowledge_extraction_dropped_total
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import ChunkingConfig

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
    """Single relation from the LLM response — raw, pre-resolution.

    C-LM-STUDIO-FIX scope expansion: ``subject``/``object_`` accept
    ``str | None`` even though the prompt explicitly tells the LLM to
    omit relations with missing endpoints. Discovered during C19 quality
    eval: every local LLM tested (qwen2.5-coder-14b, phi-4, gemma-3-27b,
    qwen3-coder-30b) emitted ``null`` objects for intransitive
    narrative verbs ("Tấm khóc" / "石猴 拜了四方") instead of dropping
    the relation as instructed. Cloud LLMs may behave differently but
    the schema must tolerate the broader observed behavior so a single
    null in 22 relations doesn't bloc the entire extraction. The
    ``_postprocess`` step filters out null/empty endpoints downstream
    (see line near ``if not subject_name or not object_name``).
    """

    subject: str | None = None
    predicate: str
    object_: str | None = Field(default=None, alias="object")
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
    llm_client: LLMClient | None = None,
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

    safe_known = json.dumps(
        known_entities, ensure_ascii=False
    ).replace("{", "{{").replace("}", "}}")

    if llm_client is not None:
        # Phase 4a-β: SDK path with system+user 2-message structure
        # so the gateway chunker can split chapter text without
        # shredding instructions. Mirrors entity extractor pattern.
        system_prompt = load_prompt("relation_system", known_entities=safe_known)
        raw_relations = await _extract_via_llm_client(
            llm_client=llm_client,
            user_id=user_id,
            project_id=project_id,
            model_source=model_source,
            model_ref=model_ref,
            system_prompt=system_prompt,
            text=text,
        )
    else:
        # Legacy K17.2 path — preserved through 4a-β, removed in 4a-δ.
        safe_text = text.replace("{", "{{").replace("}", "}}")
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
        raw_relations = response.relations

    return _postprocess(
        raw_relations,
        entities=entities,
        known_entities=known_entities,
        user_id=user_id,
        project_id=project_id,
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
) -> list[_LLMRelation]:
    """Submit relation_extraction job + wait_terminal + tolerant-parse
    `result.relations`. Mirrors entity extractor's SDK path:
      - system message preserved across chunks (instructions + KNOWN_ENTITIES)
      - user message = chapter text (chunked on \\n\\n at gateway)
      - ChunkingConfig(strategy=paragraphs, size=15) per ADR §6 Q1
      - Cancelled job raises ExtractionError(stage='cancelled')
      - Tolerant parser drops items missing required fields per LOW#11
    """
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="relation_extraction",
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
                "extractor": "relation",
                "project_id": project_id or "",
            },
            transient_retry_budget=1,
        )
    except LLMTransientRetryNeededError as exc:
        raise ExtractionError(
            f"relation_extraction failed after transient retry: {exc.underlying_code}",
            stage="provider_exhausted",
            last_error=exc,
        ) from exc
    except LLMError as exc:
        raise ExtractionError(
            f"relation_extraction SDK error: {exc}",
            stage="provider",
            last_error=exc,
        ) from exc

    if job.status == "cancelled":
        raise ExtractionError(
            f"relation_extraction job cancelled (job_id={job.job_id})",
            stage="cancelled",  # type: ignore[arg-type]
        )
    if job.status != "completed":
        err_code = job.error.code if job.error else "LLM_UNKNOWN_ERROR"
        err_msg = job.error.message if job.error else ""
        raise ExtractionError(
            f"relation_extraction job ended status={job.status} code={err_code}: {err_msg}",
            stage="provider",
        )

    raw_items: list[Any] = []
    if job.result is not None:
        items = job.result.get("relations", [])
        if isinstance(items, list):
            raw_items = items
    return _tolerant_parse_relations(raw_items)


def _tolerant_parse_relations(raw_items: list[Any]) -> list[_LLMRelation]:
    """Drop items missing `predicate` or `confidence`; tolerate
    null subject/object endpoints (post-processed downstream); clamp
    confidence to [0, 1]; drop on enum-validation failure."""
    parsed: list[_LLMRelation] = []
    for item in raw_items:
        if not isinstance(item, dict):
            knowledge_extraction_dropped_total.labels(
                operation="relation_extraction", reason="validation"
            ).inc()
            continue
        predicate = item.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            knowledge_extraction_dropped_total.labels(
                operation="relation_extraction", reason="missing_name"
            ).inc()
            continue
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))
        # subject/object are tolerated as None — _postprocess filters
        # out null endpoints (relation_extractor C-LM-STUDIO-FIX scope).
        try:
            parsed.append(_LLMRelation(
                subject=item.get("subject"),
                predicate=predicate,
                object_=item.get("object"),  # alias='object' in pydantic
                polarity=item.get("polarity", "affirm"),
                modality=item.get("modality", "asserted"),
                confidence=confidence,
            ))
        except ValidationError:
            knowledge_extraction_dropped_total.labels(
                operation="relation_extraction", reason="validation"
            ).inc()
            continue
    return parsed


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

        # C-LM-STUDIO-FIX: rel.subject / rel.object_ can be None when
        # the LLM emits null instead of dropping a partial relation
        # (see _LLMRelation docstring). Coerce to '' so the existing
        # filter handles both cases uniformly.
        subject_name = (rel.subject or "").strip()
        object_name = (rel.object_ or "").strip()
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
