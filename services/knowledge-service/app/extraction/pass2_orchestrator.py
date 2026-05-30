"""K17.8 — Pass 2 (LLM) extraction orchestrator.

Top-level entry points for running the LLM extraction pipeline and
persisting results to Neo4j via the Pass 2 writer.

Pipeline:
  1. ``extract_entities`` → entity candidates
  2. **Gate:** if no entities, skip steps 3-4 (nothing to anchor)
  3. relation/event/fact extractors run concurrently via ``asyncio.gather``
  4. ``write_pass2_extraction`` persists everything

**Mirrors K15.8** (Pass 1 orchestrator) with two entry points:
  - ``extract_pass2_chat_turn`` — handles user/assistant message split
  - ``extract_pass2_chapter`` — handles single text body

**What this module deliberately does NOT do:**
  - Chunking — the caller (K16.6 job runner) handles chapter splitting
  - Cost tracking — the caller manages budget via K16.1 state machine
  - Pass 1 reconciliation — deferred to K18 validator (promotes
    quarantined Pass 1 facts when Pass 2 confirms them)

Phase 4b-α: extractor logic moved to ``loreweave_extraction``. This
module orchestrates the per-stage telemetry pattern + glossary anchor
loading + Neo4j write — keeps service-side concerns at the service
boundary while the library owns the LLM/SDK plumbing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Iterable
from typing import Any, Literal, TypedDict
from uuid import UUID

from loreweave_extraction import (
    ContextBudget,
    EntityRecoveryConfig,
    FilterDecision,
    Pass2Candidates,
    PrecisionFilterConfig,
    RecoveryDecision,
    apply_precision_filter,
    get_extractor_version,
    recover_missing_entities,
)
from loreweave_extraction.extractors.entity import extract_entities
from loreweave_extraction.extractors.event import extract_events
from loreweave_extraction.extractors.fact import extract_facts
from loreweave_extraction.extractors.relation import extract_relations

from app.clients.book_client import get_book_client
from app.clients.llm_client import LLMClient
from app.db.neo4j_helpers import CypherSession
from app.db.pool import get_knowledge_pool
from app.db.repositories.extraction_leaves import ExtractionLeavesRepo
from app.db.repositories.job_logs import JobLogsRepo
from app.extraction.anchor_loader import Anchor
from app.extraction.hierarchy_writer import HierarchyPaths
from app.extraction.pass2_writer import Pass2WriteResult, write_pass2_extraction
from app.jobs.summary_enqueue import SummaryEnqueueFn, SummarizeMessage
from app.jobs.task_id import compute_task_id
from app.metrics import (
    knowledge_extraction_dropped_total,
    knowledge_extraction_filter_coverage_ratio,
    knowledge_extraction_filter_decisions_total,
    knowledge_extraction_recovery_decisions_total,
)

__all__ = [
    "extract_pass2_chat_turn",
    "extract_pass2_chapter",
    "enqueue_chapter_and_maybe_book_summaries",
    "gather_relations_events_facts",
]


# ── Cycle 72 — precision filter env-driven config ──────────────────────


def _load_precision_filter_config() -> PrecisionFilterConfig | None:
    """Read the cycle-72 precision filter env config.

    Returns:
        ``PrecisionFilterConfig`` when
        ``KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF`` is set;
        ``None`` otherwise (filter disabled — default).

    Envs (all optional):
        KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF: gateway
            model_ref / UUID for the precision filter LLM. Unset = off.
        KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY: ``"keep"``
            (default) or ``"drop"``.
        KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_SOURCE: ``"user_model"``
            (default) or ``"platform_model"``.
        KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES: comma-separated
            subset of ``{"entity","relation","event"}`` (default
            ``"entity,relation,event"`` for cycle-72 backward-compat;
            cycle-73b ship uses ``"relation"`` for 55% latency
            reduction at near-identical F1).
    """
    model_ref = os.environ.get(
        "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_REF", ""
    ).strip()
    if not model_ref:
        return None
    partial_policy = os.environ.get(
        "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_PARTIAL_POLICY", "keep"
    ).strip() or "keep"
    model_source = os.environ.get(
        "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_MODEL_SOURCE", "user_model"
    ).strip() or "user_model"
    categories_env = os.environ.get(
        "KNOWLEDGE_EXTRACTION_PRECISION_FILTER_CATEGORIES",
        "entity,relation,event",
    ).strip() or "entity,relation,event"
    categories = tuple(
        c.strip() for c in categories_env.split(",") if c.strip()
    )
    return PrecisionFilterConfig(
        model_ref=model_ref,
        model_source=model_source,  # type: ignore[arg-type]
        partial_policy=partial_policy,  # type: ignore[arg-type]
        categories=categories,  # type: ignore[arg-type]
    )


# Cached at module load. Re-read by tests via patch on this name.
_PRECISION_FILTER_CONFIG: PrecisionFilterConfig | None = _load_precision_filter_config()


def _load_entity_recovery_config() -> EntityRecoveryConfig | None:
    """Cycle 73d — read entity recovery env config.

    Envs (all optional):
        KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF: gateway
            model_ref / UUID for the LLM classifier (Tier 3). Unset = off.
        KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_SOURCE: default
            "user_model".
        KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MAX_BATCH: int (default 5).
    """
    model_ref = os.environ.get(
        "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_REF", ""
    ).strip()
    if not model_ref:
        return None
    model_source = os.environ.get(
        "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MODEL_SOURCE", "user_model"
    ).strip() or "user_model"
    max_batch_env = os.environ.get(
        "KNOWLEDGE_EXTRACTION_ENTITY_RECOVERY_MAX_BATCH", "5"
    ).strip() or "5"
    try:
        max_batch = int(max_batch_env)
    except ValueError:
        max_batch = 5
    return EntityRecoveryConfig(
        model_ref=model_ref,
        model_source=model_source,  # type: ignore[arg-type]
        max_items_per_batch=max(1, max_batch),
        # known_entity_kinds populated per-call from glossary anchors
    )


_ENTITY_RECOVERY_CONFIG: EntityRecoveryConfig | None = _load_entity_recovery_config()


class _WriterAutocreateKwargs(TypedDict):
    """Typed kwargs spreadable into ``write_pass2_extraction(**)``.

    Cycle 73e — used by ``_load_writer_autocreate_config`` so the
    ``**_WRITER_AUTOCREATE_CONFIG`` spread is mypy-clean. Matches the
    new kwargs added to ``pass2_writer.write_pass2_extraction`` exactly.
    """
    autocreate_enabled: bool
    autocreate_max: int | None


def _load_writer_autocreate_config() -> _WriterAutocreateKwargs:
    """Cycle 73e — read Pass2 writer autocreate env config.

    Returns a TypedDict spreadable into ``write_pass2_extraction(**)``.
    Default: disabled. Tier A.1/A.2 free repairs still run regardless;
    only Tier B autocreate is gated.

    Envs (all optional):
        KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED: ``"true"`` /
            ``"1"`` / ``"yes"`` / ``"on"`` (case-insensitive) enables
            Tier B. Anything else (default) keeps it off.
        KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER: int
            cap per chapter (default 20). Empty / non-numeric also
            defaults to 20.
    """
    enabled_env = os.environ.get(
        "KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED", "false"
    ).strip().lower()
    enabled = enabled_env in ("true", "1", "yes", "on")
    max_env = os.environ.get(
        "KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_MAX_PER_CHAPTER", "20"
    ).strip() or "20"
    try:
        max_per_chapter: int | None = max(1, int(max_env))
    except ValueError:
        max_per_chapter = 20
    return {
        "autocreate_enabled": enabled,
        "autocreate_max": max_per_chapter,
    }


_WRITER_AUTOCREATE_CONFIG: _WriterAutocreateKwargs = _load_writer_autocreate_config()


def _on_recovery_decision(decision: RecoveryDecision) -> None:
    """Bridge RecoveryDecision callbacks to Prometheus counter."""
    knowledge_extraction_recovery_decisions_total.labels(
        source=decision.source, verdict=decision.verdict,
    ).inc()


def _on_filter_decision(decision: FilterDecision) -> None:
    """Bridge `FilterDecision` callbacks to the Prometheus counter."""
    knowledge_extraction_filter_decisions_total.labels(
        category=decision.category, verdict=decision.verdict
    ).inc()


async def _maybe_apply_entity_recovery(
    *,
    entities: list[Any],
    relations: list[Any],
    events: list[Any],
    facts: list[Any],
    text: str,
    user_id: str,
    project_id: str | None,
    llm_client: LLMClient,
    anchors: list[Anchor] | None,
    job_logs_repo: JobLogsRepo | None,
    job_id: str,
    source_type: str,
    source_id: str,
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Cycle 73d — optional 3-tier entity recovery (runs BEFORE filter).

    Glossary anchors are merged into the EntityRecoveryConfig's
    known_entity_kinds map for Tier 1 lookup. Tier 3 (LLM classifier)
    handles names not in glossary. Author hints surface is future work
    (no API yet).
    """
    if _ENTITY_RECOVERY_CONFIG is None:
        return entities, relations, events, facts

    # Build name→kind from glossary anchors (name + aliases, lowercase
    # for case-insensitive lookup downstream).
    known_kinds: dict[str, str] = {}
    if anchors:
        for a in anchors:
            known_kinds[a.name] = a.kind
            for alias in a.aliases:
                known_kinds.setdefault(alias, a.kind)

    # Inject per-call config with merged known_entity_kinds.
    from dataclasses import replace as dc_replace
    config = dc_replace(
        _ENTITY_RECOVERY_CONFIG, known_entity_kinds=known_kinds
    )

    pre_entity_count = len(entities)
    pre_rel_count = len(relations)

    recovery_started = time.perf_counter()
    enriched = await recover_missing_entities(
        Pass2Candidates(
            entities=entities,
            relations=relations,
            events=events,
            facts=facts,
        ),
        text=text,
        config=config,
        user_id=user_id,
        project_id=project_id,
        llm_client=llm_client,
        on_decision=_on_recovery_decision,
    )
    recovery_elapsed = time.perf_counter() - recovery_started

    post_entity_count = len(enriched.entities)
    post_rel_count = len(enriched.relations)

    await _emit_log(
        job_logs_repo, user_id, job_id,
        f"Pass 2 entity recovery: "
        f"ent {pre_entity_count}->{post_entity_count} "
        f"(+{post_entity_count - pre_entity_count} recovered), "
        f"rel {pre_rel_count}->{post_rel_count} "
        f"({pre_rel_count - post_rel_count} dropped as abstract) "
        f"in {recovery_elapsed:.2f}s "
        f"(glossary hints: {len(known_kinds)})",
        context={
            "event": "pass2_entity_recovery",
            "source_type": source_type,
            "source_id": source_id,
            "entities_in": pre_entity_count,
            "entities_out": post_entity_count,
            "relations_in": pre_rel_count,
            "relations_out": post_rel_count,
            "glossary_hint_count": len(known_kinds),
            "duration_ms": int(recovery_elapsed * 1000),
        },
    )

    return (
        enriched.entities,
        enriched.relations,
        enriched.events,
        enriched.facts,
    )


async def _maybe_apply_precision_filter(
    *,
    entities: list[Any],
    relations: list[Any],
    events: list[Any],
    facts: list[Any],
    text: str,
    user_id: str,
    llm_client: LLMClient,
    job_logs_repo: JobLogsRepo | None,
    job_id: str,
    source_type: str,
    source_id: str,
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Cycle 72 — optional precision filter pass between gather and write.

    When ``_PRECISION_FILTER_CONFIG`` is None, returns the inputs
    unchanged (zero-overhead pass-through).

    When set, wraps the candidates into a ``Pass2Candidates``, calls
    ``apply_precision_filter``, emits a stage log + updates the
    coverage gauge, and returns the filtered lists. Facts are NEVER
    filtered (per spec D2 — passed through unchanged).
    """
    if _PRECISION_FILTER_CONFIG is None:
        return entities, relations, events, facts

    pass2_candidates = Pass2Candidates(
        entities=entities,
        relations=relations,
        events=events,
        facts=facts,
    )

    filter_started = time.perf_counter()
    filtered = await apply_precision_filter(
        pass2_candidates,
        text=text,
        config=_PRECISION_FILTER_CONFIG,
        user_id=user_id,
        llm_client=llm_client,
        on_decision=_on_filter_decision,
    )
    filter_elapsed = time.perf_counter() - filter_started

    # Update coverage gauge per category.
    for cat, cov in filtered.filter_coverage.items():
        if cat in ("entity", "relation", "event"):
            knowledge_extraction_filter_coverage_ratio.labels(
                category=cat
            ).set(cov)

    # Stage log so the FE log panel can show filter progress.
    await _emit_log(
        job_logs_repo, user_id, job_id,
        f"Pass 2 precision filter ({filtered.filter_status}): "
        f"ent {len(entities)}->{len(filtered.entities)}, "
        f"rel {len(relations)}->{len(filtered.relations)}, "
        f"evt {len(events)}->{len(filtered.events)} "
        f"in {filter_elapsed:.2f}s "
        f"(coverage entity={filtered.filter_coverage.get('entity', 1.0):.0%} "
        f"relation={filtered.filter_coverage.get('relation', 1.0):.0%} "
        f"event={filtered.filter_coverage.get('event', 1.0):.0%})",
        context={
            "event": "pass2_precision_filter",
            "source_type": source_type,
            "source_id": source_id,
            "filter_status": filtered.filter_status,
            "filter_coverage": filtered.filter_coverage,
            "entities_in": len(entities),
            "entities_out": len(filtered.entities),
            "relations_in": len(relations),
            "relations_out": len(filtered.relations),
            "events_in": len(events),
            "events_out": len(filtered.events),
            "duration_ms": int(filter_elapsed * 1000),
        },
    )

    # Facts are NOT filtered per spec D2; pass through unchanged.
    return (
        filtered.entities,
        filtered.relations,
        filtered.events,
        facts,
    )


# ── P2 (hierarchical extraction T3) — D3 cache integration ──────────────────


async def _fetch_chapter_leaf_text(
    book_id: UUID,
    chapter_id: UUID,
) -> tuple[str | None, str]:
    """P2 D8 — fetch chapter content via book-service.

    Returns (text, source) where source is "scenes" if scenes existed, or
    "draft_text" if we fell back to the legacy-chapter path (NULL
    structural_path → chapter_drafts.body Tiptap-to-text projection).

    Returns (None, "missing") on transport failure or empty chapter.
    """
    client = get_book_client()
    scenes = await client.list_scenes_by_chapter(book_id, chapter_id)
    if scenes:
        # P1-decomposed chapter: join scene leaf_texts in sort_order.
        joined = "\n\n".join(s.get("leaf_text", "") for s in scenes if s.get("leaf_text"))
        return (joined.strip() or None, "scenes")
    # Legacy chapter (P1 R-SELF-1 NULL sentinel) — fall back to draft text.
    draft = await client.get_chapter_draft_text(book_id, chapter_id)
    if draft and draft.strip():
        return (draft.strip(), "draft_text")
    return (None, "missing")


async def _p2_cache_wrap(
    *,
    op: Literal["entity", "relation", "event", "fact"],
    leaf_text: str,
    extractor_callable,
    extractor_kwargs: dict[str, Any],
    deserializer,  # callable(dict) -> Pydantic candidate
    book_id: UUID | None,
    chapter_id: UUID | None,
    model_ref: str,
    save_raw: bool,
) -> list[Any]:
    """P2 cache wrapper around a single extractor call.

    When book_id+chapter_id are provided: compute task_id, check cache,
    on miss claim + call extractor + persist. On hit, deserialize cached
    candidates back to Pydantic and return — NO LLM call.

    When book_id+chapter_id are None (chat_turn path): no cache, just
    call extractor as before.
    """
    if book_id is None or chapter_id is None:
        # Chat-turn or other non-chapter path — no cache, pass through.
        return await extractor_callable(**extractor_kwargs)

    # D-P2-MIGRATE-TO-PER-OP-EXTRACTOR-VERSION. Per-op hash so editing
    # one op's prompt only invalidates that op's cache slice — previously
    # the global hash invalidated all 4 ops on any prompt edit.
    # Format: `v1-{op}-{8hex}` (vs old `v1-{8hex}`). One-time cache
    # thrash on first deploy: every existing P2 task_id changes once.
    extractor_version = get_extractor_version(op=op)
    task_id = compute_task_id(leaf_text, op, extractor_version, model_ref)
    pool = get_knowledge_pool()
    repo = ExtractionLeavesRepo(pool)

    cached = await repo.fetch_cached(task_id)
    if cached is not None and cached.candidates_jsonb is not None:
        logger.info(
            "p2 cache HIT op=%s chapter_id=%s candidates=%d task_id=%s",
            op, chapter_id, len(cached.candidates_jsonb), task_id[:12],
        )
        return [deserializer(c) for c in cached.candidates_jsonb]

    # Cache miss — claim then call extractor.
    leaf_path = f"book/legacy/chapter-{chapter_id}/scene-1"
    await repo.claim_pending(
        book_id=book_id,
        scene_id=chapter_id,  # placeholder until per-scene fanout (D-P2-PER-SCENE-FANOUT)
        leaf_path=leaf_path,
        op=op,
        task_id=task_id,
        parse_version=1,
        extractor_version=extractor_version,
        model_ref=model_ref,
    )
    try:
        candidates = await extractor_callable(**extractor_kwargs)
    except Exception as exc:
        await repo.mark_failed(
            task_id=task_id,
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise

    # Persist candidates (model_dump for JSONB).
    await repo.persist(
        task_id=task_id,
        candidates=[c.model_dump(mode="json") for c in candidates],
        glossary_anchor_size=None,
        raw_response=None,  # raw_response stitching across the chunked
                            # extractor calls is non-trivial; save_raw
                            # opt-in deferred to D-P2-PER-SCENE-FANOUT
                            # where per-leaf raw is naturally one call.
        raw_token_usage=None,
    )
    logger.info(
        "p2 cache MISS op=%s chapter_id=%s candidates=%d task_id=%s persisted",
        op, chapter_id, len(candidates), task_id[:12],
    )
    _ = save_raw  # explicit consumption — see comment above
    return candidates

logger = logging.getLogger(__name__)


def _on_dropped(operation: str, reason: str) -> None:
    """Phase 4b-α — bridge the library's `on_dropped` callback to the
    service-side Prometheus counter. Keeps the existing
    `knowledge_extraction_dropped_total{operation, reason}` time series
    intact so dashboards don't need updating."""
    knowledge_extraction_dropped_total.labels(
        operation=operation, reason=reason
    ).inc()


async def _emit_log(
    repo: JobLogsRepo | None,
    user_id: str,
    job_id: str,
    message: str,
    context: dict[str, Any],
) -> None:
    """C3 (D-K19b.8-02) — best-effort stage logger for Pass 2 pipeline.

    Writes to ``job_logs`` so the FE's JobLogsPanel can render
    extraction-pipeline progress alongside worker-ai's lifecycle events
    (chapter_processed / skipped / failed). Always ``info`` level;
    extraction failures surface from worker-ai at job level via the
    existing ``_append_log`` call sites.

    When ``repo`` is None the call is a no-op — lets existing
    ``extract_pass2_*`` test callers (≈20 of them) remain untouched
    while production paths pass a real repo. A Postgres write error
    during log emission is NOT fatal to extraction: we log a warning
    and continue.
    """
    if repo is None:
        return
    try:
        await repo.append(
            UUID(user_id), UUID(job_id), "info", message, context,
        )
    except Exception:
        logger.warning(
            "C3: pass2 stage log emit failed (non-fatal) message=%r",
            message, exc_info=True,
        )


async def gather_relations_events_facts(
    *,
    text: str,
    entities: list[Any],
    known_entities: list[str],
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
    on_dropped: Any = None,
    context_budget: "ContextBudget | None" = None,
) -> tuple[list[Any], list[Any], list[Any]]:
    """C-PRED-ALIGN-DEF-01 — single source of truth for Pass 2 R+E+F
    parallelism. Returns ``(relations, events, facts)``.

    Why this helper exists: production ``_run_pipeline`` and the
    ``tests/quality/test_extraction_eval.py`` golden-set harness both
    need the same concurrent fan-out across the relation/event/fact
    extractors. Before this helper existed, the eval test ran them
    serially (and was missing ``extract_facts`` entirely), so any
    future change to the gather shape — say a 4th sibling extractor
    or a switch to ``TaskGroup`` — would silently desync the test
    from production. Both call sites now go through here.

    Pure: no Neo4j, no telemetry, no logging. Merges
    ``known_entities`` with the entity names just like production did
    so callers don't have to. The ``on_dropped`` callback is forwarded
    to each extractor for the Prometheus drop counter (eval can pass
    ``None`` if it doesn't track drops).

    Model-aware concurrency (NEW): when ``context_budget`` is
    supplied, the 3 R/E/F extractors are gated by an
    ``asyncio.Semaphore(context_budget.max_parallel_slots())``. On
    tight-context local models (e.g. 24K loaded), this auto-falls-back
    to 1 or 2 concurrent slots → eliminates the LM Studio
    "failed to find a memory slot for batch" / slot-purge errors
    observed when 3 R+E+F × full-model-context-per-slot exceeded
    available VRAM. The budget is also threaded to each extractor so
    chunk size scales with the loaded context. Legacy callers (None)
    keep the unbounded gather behaviour.
    """
    entity_names = [e.name for e in entities]
    all_known = list(set(known_entities + entity_names))
    extractor_kwargs = dict(
        text=text,
        entities=entities,
        known_entities=all_known,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        llm_client=llm_client,
        on_dropped=on_dropped,
    )
    if context_budget is not None:
        extractor_kwargs["context_budget"] = context_budget
        max_parallel = context_budget.max_parallel_slots()
        sem = asyncio.Semaphore(max_parallel)

        async def _gated(coro):
            async with sem:
                return await coro

        relations, events, facts = await asyncio.gather(
            _gated(extract_relations(**extractor_kwargs)),
            _gated(extract_events(**extractor_kwargs)),
            _gated(extract_facts(**extractor_kwargs)),
        )
    else:
        relations, events, facts = await asyncio.gather(
            extract_relations(**extractor_kwargs),
            extract_events(**extractor_kwargs),
            extract_facts(**extractor_kwargs),
        )
    return relations, events, facts


async def _run_pipeline(
    session: CypherSession,
    *,
    text: str,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    known_entities: list[str],
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
    # P2 (D3): when book_id+chapter_id supplied, the per-op extractor
    # calls are wrapped in the extraction_leaves cache (hit -> no LLM
    # call). When None (chat_turn path), legacy behaviour — direct calls.
    book_id: UUID | None = None,
    chapter_id: UUID | None = None,
    save_raw_extraction: bool = False,
    # P3 (D2 + D2a + D3 + D9): hierarchy threading + async summary enqueue.
    # When hierarchy_paths supplied: pass2_writer MERGEs Book/Part/Chapter/Scene
    # in same Tx before entity writes. When summary_enqueue supplied:
    # after successful write, enqueue summary.chapter (always) + on
    # is_last_chapter_of_book, also summary.part × N + summary.book.
    hierarchy_paths: HierarchyPaths | None = None,
    is_last_chapter_of_book: bool = False,
    book_parts: list[tuple[str, str, str]] | None = None,  # for book-end: [(part_id, part_path, part_index), ...]
    embedding_model_uuid: str | None = None,
    embedding_dimension: int | None = None,
    summary_enqueue: SummaryEnqueueFn | None = None,
) -> Pass2WriteResult:
    """Core pipeline shared by chat_turn and chapter entry points.

    C3 (D-K19b.8-02): ``job_logs_repo`` is optional — when supplied,
    stage progress is mirrored into ``job_logs`` so the FE's log panel
    can show Pass 2 extraction timings alongside worker-ai's lifecycle
    events. All emitted events are ``info`` level; extraction failures
    are surfaced from worker-ai at job level via its own
    ``_append_log`` call sites.
    """
    # Empty text → write empty source for idempotency, return zeros.
    if not text or not text.strip():
        return await write_pass2_extraction(
            session,
            user_id=user_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            job_id=job_id,
            extraction_model=model_ref,
            anchors=anchors,
            **_WRITER_AUTOCREATE_CONFIG,
        )

    started = time.perf_counter()

    # Step 1 — extract entities first (must run before R/E/F so they
    # can anchor against entity_names + known_entities). Routes through
    # SDK + gateway job pattern (entity_extraction op + paragraphs/15
    # chunking + per-op JSON aggregator).
    # P2 (D3): wrap with extraction_leaves cache when book/chapter known.
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    entities = await _p2_cache_wrap(
        op="entity",
        leaf_text=text,
        extractor_callable=extract_entities,
        extractor_kwargs=dict(
            text=text,
            known_entities=known_entities,
            user_id=user_id,
            project_id=project_id,
            model_source=model_source,
            model_ref=model_ref,
            llm_client=llm_client,
            on_dropped=_on_dropped,
        ),
        deserializer=LLMEntityCandidate.model_validate,
        book_id=book_id,
        chapter_id=chapter_id,
        model_ref=model_ref,
        save_raw=save_raw_extraction,
    )

    entities_elapsed = time.perf_counter() - started
    logger.info(
        "Pass 2 entity extraction: %d candidates in %.1fs",
        len(entities), entities_elapsed,
    )
    await _emit_log(
        job_logs_repo, user_id, job_id,
        f"Pass 2 entity extraction: {len(entities)} candidates in "
        f"{entities_elapsed:.2f}s",
        context={
            "event": "pass2_entities",
            "source_type": source_type,
            "source_id": source_id,
            "count": len(entities),
            "duration_ms": int(entities_elapsed * 1000),
        },
    )

    # Gate: if no entities, nothing to anchor relations/events/facts.
    # Write entities only (empty list) and return.
    if not entities:
        await _emit_log(
            job_logs_repo, user_id, job_id,
            "Pass 2 gate: no entity candidates — skipping "
            "relation/event/fact extractors",
            context={
                "event": "pass2_entities_gate",
                "source_type": source_type,
                "source_id": source_id,
            },
        )
        return await write_pass2_extraction(
            session,
            user_id=user_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            job_id=job_id,
            extraction_model=model_ref,
            anchors=anchors,
            **_WRITER_AUTOCREATE_CONFIG,
        )

    # Steps 2-4 — relation/event/fact run concurrently. All three
    # extractors route through SDK + chunking + jsonListAggregator.
    # P2 (D3): each of the 3 ops is independently cache-wrapped — a
    # re-extraction of unchanged text gets 4 cache hits (entity above
    # + R/E/F here) = 0 LLM calls. When book_id/chapter_id are None
    # (chat_turn), wrappers passthrough to legacy gather behaviour.
    from loreweave_extraction.extractors.event import LLMEventCandidate
    from loreweave_extraction.extractors.fact import LLMFactCandidate
    from loreweave_extraction.extractors.relation import LLMRelationCandidate
    entity_names = [e.name for e in entities]
    all_known = list(set(known_entities + entity_names))
    common_kwargs = dict(
        text=text,
        entities=entities,
        known_entities=all_known,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        llm_client=llm_client,
        on_dropped=_on_dropped,
    )
    gather_started = time.perf_counter()
    relation_cands, event_cands, fact_cands = await asyncio.gather(
        _p2_cache_wrap(
            op="relation",
            leaf_text=text,
            extractor_callable=extract_relations,
            extractor_kwargs=common_kwargs,
            deserializer=LLMRelationCandidate.model_validate,
            book_id=book_id, chapter_id=chapter_id,
            model_ref=model_ref, save_raw=save_raw_extraction,
        ),
        _p2_cache_wrap(
            op="event",
            leaf_text=text,
            extractor_callable=extract_events,
            extractor_kwargs=common_kwargs,
            deserializer=LLMEventCandidate.model_validate,
            book_id=book_id, chapter_id=chapter_id,
            model_ref=model_ref, save_raw=save_raw_extraction,
        ),
        _p2_cache_wrap(
            op="fact",
            leaf_text=text,
            extractor_callable=extract_facts,
            extractor_kwargs=common_kwargs,
            deserializer=LLMFactCandidate.model_validate,
            book_id=book_id, chapter_id=chapter_id,
            model_ref=model_ref, save_raw=save_raw_extraction,
        ),
    )
    gather_elapsed = time.perf_counter() - gather_started

    # Cycle 73d — optional entity recovery (runs BEFORE filter so the
    # filter operates on enriched candidates). No-op when env unset.
    entities, relation_cands, event_cands, fact_cands = await _maybe_apply_entity_recovery(
        entities=entities,
        relations=relation_cands,
        events=event_cands,
        facts=fact_cands,
        text=text,
        user_id=user_id,
        project_id=project_id,
        llm_client=llm_client,
        anchors=anchors,
        job_logs_repo=job_logs_repo,
        job_id=job_id,
        source_type=source_type,
        source_id=source_id,
    )

    # Cycle 72 — optional precision filter (no-op when env unset).
    entities, relation_cands, event_cands, fact_cands = await _maybe_apply_precision_filter(
        entities=entities,
        relations=relation_cands,
        events=event_cands,
        facts=fact_cands,
        text=text,
        user_id=user_id,
        llm_client=llm_client,
        job_logs_repo=job_logs_repo,
        job_id=job_id,
        source_type=source_type,
        source_id=source_id,
    )

    elapsed = time.perf_counter() - started
    logger.info(
        "Pass 2 extraction complete: %d entities, %d relations, "
        "%d events, %d facts in %.1fs",
        len(entities), len(relation_cands),
        len(event_cands), len(fact_cands), elapsed,
    )
    await _emit_log(
        job_logs_repo, user_id, job_id,
        f"Pass 2 R/E/F extraction: "
        f"{len(relation_cands)}/"
        f"{len(event_cands)}/"
        f"{len(fact_cands)} candidates in {gather_elapsed:.2f}s",
        context={
            "event": "pass2_gather",
            "source_type": source_type,
            "source_id": source_id,
            "relations": len(relation_cands),
            "events": len(event_cands),
            "facts": len(fact_cands),
            "duration_ms": int(gather_elapsed * 1000),
        },
    )

    # Step 5 — write everything to Neo4j.
    write_started = time.perf_counter()
    write_result = await write_pass2_extraction(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        job_id=job_id,
        entities=entities,
        relations=relation_cands,
        events=event_cands,
        facts=fact_cands,
        extraction_model=model_ref,
        anchors=anchors,
        hierarchy_paths=hierarchy_paths,   # P3 D2a — hierarchy MERGE in same Tx
        **_WRITER_AUTOCREATE_CONFIG,
    )
    write_elapsed = time.perf_counter() - write_started
    await _emit_log(
        job_logs_repo, user_id, job_id,
        f"Pass 2 write complete: "
        f"entities={write_result.entities_merged}, "
        f"relations={write_result.relations_created}, "
        f"events={write_result.events_merged}, "
        f"facts={write_result.facts_merged} "
        f"in {write_elapsed:.2f}s",
        context={
            "event": "pass2_write",
            "source_type": source_type,
            "source_id": source_id,
            "entities_merged": write_result.entities_merged,
            "relations_created": write_result.relations_created,
            "events_merged": write_result.events_merged,
            "facts_merged": write_result.facts_merged,
            "evidence_edges": write_result.evidence_edges,
            "duration_ms": int(write_elapsed * 1000),
        },
    )

    # P3 (D3): async summary enqueue. Only fires when caller wired all the
    # P3 dependencies (hierarchy_paths + summary_enqueue + embedding model
    # info). Chat-turn path + legacy callers don't trigger.
    if (
        hierarchy_paths is not None
        and summary_enqueue is not None
        and embedding_model_uuid is not None
        and embedding_dimension is not None
    ):
        await enqueue_chapter_and_maybe_book_summaries(
            summary_enqueue=summary_enqueue,
            hierarchy_paths=hierarchy_paths,
            user_id=user_id,
            project_id=project_id or "",
            job_id=job_id,
            model_ref=model_ref,
            embedding_model_uuid=embedding_model_uuid,
            embedding_dimension=embedding_dimension,
            is_last_chapter_of_book=is_last_chapter_of_book,
            book_parts=book_parts or [],
        )

    return write_result


async def enqueue_chapter_and_maybe_book_summaries(
    *,
    summary_enqueue: SummaryEnqueueFn,
    hierarchy_paths: HierarchyPaths,
    user_id: str,
    project_id: str,
    job_id: str,
    model_ref: str,
    embedding_model_uuid: str,
    embedding_dimension: int,
    is_last_chapter_of_book: bool,
    book_parts: list[tuple[str, str, str]],
) -> None:
    """Always enqueue summary.chapter for this chapter. On is_last_chapter,
    additionally enqueue summary.part per book_parts + summary.book.

    The summary_processor's D9 defensive check verifies all children exist
    before generating part/book summaries — caller's is_last_chapter is a
    HINT, not a hard precondition.
    """
    # 1. Chapter summary — always.
    await summary_enqueue(SummarizeMessage(
        level="chapter",
        node_path=hierarchy_paths.chapter_path,
        node_id=hierarchy_paths.chapter_id,
        book_id=hierarchy_paths.book_id,
        user_id=user_id,
        project_id=project_id,
        job_id=job_id,
        model_ref=model_ref,
        embedding_model_uuid=embedding_model_uuid,
        embedding_dimension=embedding_dimension,
    ))
    if not is_last_chapter_of_book:
        return
    # 2. Part summaries — one per (part_id, part_path) for the book.
    for part_id, part_path, _part_index in book_parts:
        await summary_enqueue(SummarizeMessage(
            level="part",
            node_path=part_path,
            node_id=part_id,
            book_id=hierarchy_paths.book_id,
            user_id=user_id,
            project_id=project_id,
            job_id=job_id,
            model_ref=model_ref,
            embedding_model_uuid=embedding_model_uuid,
            embedding_dimension=embedding_dimension,
        ))
    # 3. Book summary — last.
    await summary_enqueue(SummarizeMessage(
        level="book",
        node_path=hierarchy_paths.book_path,
        node_id=hierarchy_paths.book_id,
        book_id=hierarchy_paths.book_id,
        user_id=user_id,
        project_id=project_id,
        job_id=job_id,
        model_ref=model_ref,
        embedding_model_uuid=embedding_model_uuid,
        embedding_dimension=embedding_dimension,
    ))


async def extract_pass2_chat_turn(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    user_message: str | None = None,
    assistant_message: str | None = None,
    known_entities: Iterable[str] | None = None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
) -> Pass2WriteResult:
    """Run the Pass 2 LLM pipeline on a chat turn.

    Concatenates user + assistant messages, then runs the full
    pipeline. Same source_type/source_id pattern as K15.8's
    ``extract_from_chat_turn``.

    `anchors`: optional K13.0 glossary-anchor index. When supplied,
    extraction candidates matching a curated anchor (by folded
    name/alias + normalized kind) link to the anchor's canonical_id
    instead of minting a duplicate `:Entity`.
    """
    halves = [
        part.strip()
        for part in (user_message, assistant_message)
        if part and part.strip()
    ]
    text = "\n\n".join(halves)

    return await _run_pipeline(
        session,
        text=text,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        job_id=job_id,
        known_entities=list(known_entities or ()),
        model_source=model_source,
        model_ref=model_ref,
        llm_client=llm_client,
        anchors=anchors,
        job_logs_repo=job_logs_repo,
    )


async def extract_pass2_chapter(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    chapter_text: str,
    known_entities: Iterable[str] | None = None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
    # P2 (D3): pass book_id+chapter_id to enable the extraction_leaves
    # cache. Re-extraction of unchanged chapters -> 4 cache hits per
    # chapter (entity + R/E/F) -> 0 LLM calls. When omitted, legacy
    # cache-bypass behaviour for back-compat.
    book_id: UUID | None = None,
    chapter_id: UUID | None = None,
    save_raw_extraction: bool = False,
    # P3 (D2 + D3 + D9): hierarchy + async summary kwargs passthrough.
    # See _run_pipeline docstring for semantics.
    hierarchy_paths: HierarchyPaths | None = None,
    is_last_chapter_of_book: bool = False,
    book_parts: list[tuple[str, str, str]] | None = None,
    embedding_model_uuid: str | None = None,
    embedding_dimension: int | None = None,
    summary_enqueue: SummaryEnqueueFn | None = None,
) -> Pass2WriteResult:
    """Run the Pass 2 LLM pipeline on a chapter.

    Single text body — no user/assistant split. The caller (K16.6
    job runner) handles chunking if needed.

    `anchors`: optional K13.0 glossary-anchor index (see
    ``extract_pass2_chat_turn`` for details).

    All 4 extractors route through the loreweave_llm SDK (job pattern +
    chunking + per-op JSON aggregator).

    P2 (D3): when book_id+chapter_id are provided, each per-op extractor
    call is wrapped in the extraction_leaves cache — same task_id
    (sha256 of text+op+extractor_version+model_ref) hit = no LLM call,
    cached candidates returned. See _p2_cache_wrap for semantics.
    """
    return await _run_pipeline(
        session,
        text=chapter_text,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        job_id=job_id,
        known_entities=list(known_entities or ()),
        model_source=model_source,
        model_ref=model_ref,
        llm_client=llm_client,
        anchors=anchors,
        job_logs_repo=job_logs_repo,
        book_id=book_id,
        chapter_id=chapter_id,
        save_raw_extraction=save_raw_extraction,
        hierarchy_paths=hierarchy_paths,
        is_last_chapter_of_book=is_last_chapter_of_book,
        book_parts=book_parts,
        embedding_model_uuid=embedding_model_uuid,
        embedding_dimension=embedding_dimension,
        summary_enqueue=summary_enqueue,
    )
