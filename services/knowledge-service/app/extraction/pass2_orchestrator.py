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
from typing import TYPE_CHECKING, Any, Literal, TypedDict
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
from loreweave_extraction.schema_projection import ExtractionSchema

from app.clients.book_client import get_book_client
from app.clients.llm_client import LLMClient
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entity_status import list_gone_entities
from app.db.pool import get_knowledge_pool
from app.db.repositories.extraction_leaves import ExtractionLeavesRepo
from app.db.repositories.job_logs import JobLogsRepo
from app.extraction.anchor_loader import Anchor
from app.extraction.canon_check import check_extraction_canon
from app.extraction.hierarchy_writer import HierarchyPaths
from app.extraction.pass2_writer import Pass2WriteResult, write_pass2_extraction

if TYPE_CHECKING:
    # L7B — the writer's triage-park Protocol, used only as a type annotation
    # (string-quoted in signatures) so the runtime import graph is unchanged.
    from app.extraction.pass2_writer import TriageParkProtocol
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
    # D-WX-PRECISION-FILTER-MODEL-ARCH: the filter MODEL must NOT come from a platform
    # env. A hardcoded env model_ref is cross-tenant — submitted as user_model scoped
    # to the request's user, so provider-registry 404'd "model not found" for every
    # user who didn't own it (decoupled extraction fold stalled — D-WX live-smoke
    # finding). The filter is configured PER-PROJECT via
    # extraction_config.precision_filter (PrecisionFilterOverride: enabled + model_ref
    # + model_source + categories + partial_policy) — FE-set, DB-stored, resolved
    # per-user, merged onto these (now model-less) global defaults. No env model source.
    return None


# Cached at module load. Re-read by tests via patch on this name.
# Cycle 73f: overridable at runtime via reload_precision_filter_config_from_redis()
# called from lifespan startup + filter-reload subscriber. Module-level rebind
# is atomic via Python GIL; in-flight readers keep their reference per call.
_PRECISION_FILTER_CONFIG: PrecisionFilterConfig | None = _load_precision_filter_config()


def set_precision_filter_config(
    new_config: PrecisionFilterConfig | None,
) -> PrecisionFilterConfig | None:
    """Cycle 73f — atomically replace module-level cache.

    Called by:
      - reload endpoint after writing to Redis (immediate local apply)
      - subscriber task on pubsub receipt (catches reloads from other services)
      - lifespan startup after reading current Redis state

    Returns the now-effective config (echoed in API response)."""
    global _PRECISION_FILTER_CONFIG
    _PRECISION_FILTER_CONFIG = new_config
    return _PRECISION_FILTER_CONFIG


async def hydrate_precision_filter_config_from_redis(redis_url: str) -> None:
    """Cycle 73f r2 H1 fold — on KS lifespan startup, GET the Redis key
    and seed the module-level cache. Without this, container restart
    loses ops-override until first reload-endpoint POST. Bumps
    `knowledge_extraction_filter_reload_total{source=startup}` metric.
    """
    import redis.asyncio as aioredis

    from app.metrics import knowledge_extraction_filter_reload_total
    from loreweave_extraction import get_filter_config

    redis_client = aioredis.from_url(redis_url, decode_responses=False)
    try:
        cached = await get_filter_config(redis_client)
        if cached is not None:
            set_precision_filter_config(cached)
            knowledge_extraction_filter_reload_total.labels(
                source="startup", outcome="applied",
            ).inc()
            logger.info(
                "cycle 73f: hydrated filter config from Redis on startup "
                "(model_ref=%s, categories=%s)",
                cached.model_ref, cached.categories,
            )
        else:
            logger.info(
                "cycle 73f: Redis filter config absent — using env defaults",
            )
    except Exception:
        knowledge_extraction_filter_reload_total.labels(
            source="startup", outcome="failed",
        ).inc()
        logger.exception(
            "cycle 73f: failed to hydrate filter config from Redis "
            "(non-fatal; using env defaults)",
        )
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


async def consume_filter_reload_signal(redis_url: str) -> None:
    """Cycle 73f r2 H1 fold — KS subscriber task. Listens on the
    filter-reload pubsub channel; on each signal, re-reads Redis +
    atomically swaps module-level cache. Without this, multi-replica KS
    deployments (the cloud default per CLAUDE.md) silently drift —
    only the replica that received the POST gets the new config.

    Resilient: SDK's subscribe_filter_reload has outer try/except with
    backoff so this never bubbles into lifespan and breaks startup.
    """
    import redis.asyncio as aioredis

    from app.metrics import knowledge_extraction_filter_reload_total
    from loreweave_extraction import (
        get_filter_config,
        subscribe_filter_reload,
    )

    redis_client = aioredis.from_url(redis_url, decode_responses=False)

    async def _on_reload() -> None:
        try:
            new_config = await get_filter_config(redis_client)
            if new_config is None:
                # Cycle 74b — key absent (e.g. after a disable=true DELETE)
                # reverts to env config, matching startup-hydrate semantics.
                # Without this the runtime path set None (filter OFF) while a
                # restart reloads env config (filter ON) — a silent cross-path
                # divergence surfaced by the cycle-73f live smoke. `_load`
                # returns None when no filter env is set, so a genuinely
                # no-filter deployment still ends at None.
                new_config = _load_precision_filter_config()
            set_precision_filter_config(new_config)
            knowledge_extraction_filter_reload_total.labels(
                source="pubsub", outcome="applied",
            ).inc()
            logger.info(
                "cycle 73f: KS filter config reloaded from Redis "
                "(active=%s)", new_config is not None,
            )
        except Exception:
            knowledge_extraction_filter_reload_total.labels(
                source="pubsub", outcome="failed",
            ).inc()
            logger.exception(
                "cycle 73f: KS failed to re-read filter config from "
                "Redis on pubsub signal",
            )

    try:
        await subscribe_filter_reload(redis_client, _on_reload)
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


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
    override: EntityRecoveryConfig | None = None,
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Cycle 73d — optional 3-tier entity recovery (runs BEFORE filter).

    Glossary anchors are merged into the EntityRecoveryConfig's
    known_entity_kinds map for Tier 1 lookup. Tier 3 (LLM classifier)
    handles names not in glossary. Author hints surface is future work
    (no API yet).

    KN model-roles: `override` is the PER-PROJECT/PER-USER-resolved config
    (endpoint-resolved via resolve_role_model — role override → project default
    → user-global default → env). When None, falls back to the module-level env
    config (`_ENTITY_RECOVERY_CONFIG`) — byte-identical to pre-KN behavior.
    """
    base_cfg = override if override is not None else _ENTITY_RECOVERY_CONFIG
    if base_cfg is None:
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
        base_cfg, known_entity_kinds=known_kinds
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
    # Cycle 73f r3 H2 fold — snapshot the module-level config to a LOCAL
    # variable at function entry. Without this, a concurrent pubsub-driven
    # reload could rebind `_PRECISION_FILTER_CONFIG = None` between the
    # `is None` check below and the later `config=...` read, passing None
    # into `apply_precision_filter` whose call sites assume non-None →
    # AttributeError crashes the extraction job instead of gracefully
    # falling through. Snapshot makes this function atomic w.r.t. reload.
    cfg = _PRECISION_FILTER_CONFIG
    if cfg is None:
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
        config=cfg,
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


# ── D-KG-EXTRACTION-CANON-WIRE — quarantine gate (advisory, never blocks) ────


async def _maybe_run_canon_check_gate(
    session: CypherSession,
    *,
    text: str,
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
    job_logs_repo: JobLogsRepo | None,
    job_id: str,
    source_type: str,
    source_id: str,
) -> None:
    """2026-07-06 — the extraction canon-check gate from the eval-validated POC
    (`app/extraction/canon_check.py`; see docs/eval/canon-check-judge-2026-07-06.md).

    Quarantine, not hard-block: a confirmed contradiction is logged to
    ``job_logs`` (already wired to the Studio's JobLogsPanel) so it's visible
    for human review — the write proceeds UNCHANGED regardless. Reuses the
    SAME model already resolved for this extraction job (no new setting;
    the eval found no reason to prefer a different/bigger model). Best-effort:
    any failure here must never break real extraction (CC4 — a critic never
    blocks on its own failure).
    """
    try:
        gone = await list_gone_entities(session, user_id=user_id, project_id=project_id)
        if not gone:
            return
        snapshot = {
            "entities": [
                {
                    "entity_id": g["entity_id"],
                    "name": g["name"],
                    "canonical_name": g["canonical_name"],
                    "status": "gone",
                    "from_order": g["from_order"],
                }
                for g in gone
            ]
        }
        candidates = await check_extraction_canon(
            text, snapshot, llm=llm_client, user_id=user_id,
            model_source=model_source, model_ref=model_ref,
        )
        for c in candidates:
            if not c.confirmed:
                continue
            await _emit_log(
                job_logs_repo, user_id, job_id,
                f"Canon check: '{c.name}' referenced as active/present despite "
                f"being marked gone at order {c.gone_from_order} -- {c.why}",
                context={
                    "event": "pass2_canon_flag",
                    "source_type": source_type,
                    "source_id": source_id,
                    "entity_id": c.entity_id,
                    "name": c.name,
                    "span": c.span,
                    "why": c.why,
                },
            )
    except Exception:
        logger.warning(
            "D-KG-EXTRACTION-CANON-WIRE: canon-check gate failed (non-fatal)",
            exc_info=True,
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


def _p2_schema_key(schema: "ExtractionSchema | None") -> str:
    """Cache-key segment for the resolved ontology schema (D-KG-LB-CACHE-SCHEMA-KEY).

    Returns the schema's ``label`` ("project_id@vN") — the full identity that
    disambiguates BOTH a schema_version bump within a project AND two projects
    with distinct custom vocab (schema_version alone collides cross-project).
    Falls back to ``v<schema_version>`` if the label is blank. ``None`` schema
    → "" → the legacy task_id hash is preserved byte-for-byte.
    """
    if schema is None:
        return ""
    label = getattr(schema, "label", "") or ""
    if label:
        return label
    ver = getattr(schema, "schema_version", None)
    return f"v{ver}" if ver is not None else ""


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
    schema_key: str = "",
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
    task_id = compute_task_id(leaf_text, op, extractor_version, model_ref, schema_key)
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
        chapter_id=chapter_id,  # WS-0.1: the invalidation key (delete_by_chapter)
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


def _merge_pinned(
    pinned_names: list[str] | None,
    known_entities: Iterable[str] | None,
) -> list[str]:
    """C13 — prepend pinned glossary entity names ahead of the window's own
    known_entities. Pinned names come FIRST (anchor priority), order-stable,
    de-duplicated (case-sensitive exact match; blank/whitespace dropped). The
    union is what reaches extract_entities + the R/E/F gather for THIS window,
    so a pinned entity is in the prompt context even when the chapter text
    never mentions it. None/empty pinned ⇒ identical to the legacy behaviour."""
    out: list[str] = []
    seen: set[str] = set()
    for name in (pinned_names or ()):
        n = (name or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    for name in (known_entities or ()):
        n = (name or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


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
    schema: ExtractionSchema | None = None,
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
        schema=schema,
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
    # C12 — target-typed extraction. None / empty ⇒ ALL passes run
    # (back-compat). Plural contract names entities/relations/events/facts
    # gate the R/E/F gather; `summaries` gates the summary enqueue.
    # Requesting any of {relations,events,facts} auto-includes `entities`.
    targets: set[str] | None = None,
    # KG customizable-ontology (lane LB) — resolved project schema projection.
    # None (default) → static byte-identical prompts + Literal validation
    # (today's behavior). A non-None ExtractionSchema activates the dynamic
    # prompt/validation path in the SDK extractors. This is the ADVISORY posture
    # (allow_free_edges hint, never pre-drop) — see ``write_schema`` below.
    schema: ExtractionSchema | None = None,
    # L7B (D-KG-L7B-EXTRACT-ITEM) — the L7 schema SPLIT for the combined
    # extract-then-write path (/extract-item). ``schema`` above feeds the SDK
    # prompt as an advisory hint; ``write_schema`` is the AUTHORITATIVE projection
    # (real ``allow_free_edges``) handed to the write boundary so the closed-edge
    # guard + ``schema_version`` stamp go live there, and ``triage_repo`` lets an
    # off-schema edge that the guard drops PARK to kg_triage_items instead of
    # vanishing. Both default None → the writer receives ``schema`` (back-compat:
    # before the split the writer got the same advisory schema and no triage_repo,
    # so ``write_schema=None``/``triage_repo=None`` is byte-identical to today).
    write_schema: ExtractionSchema | None = None,
    triage_repo: "TriageParkProtocol | None" = None,
    # KN model-roles — per-project/per-user-resolved entity_recovery config
    # (endpoint-resolved). None ⇒ module-level env config (byte-identical).
    entity_recovery_override: EntityRecoveryConfig | None = None,
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

    # C12 — resolve effective target set (None/empty ⇒ all; dependent
    # targets auto-include entities). Reuses the SDK's single source of
    # truth so the gate matches the worker-ai path exactly.
    from loreweave_extraction.pass2 import normalize_targets
    eff_targets = normalize_targets(targets)
    want_relations = "relations" in eff_targets
    want_events = "events" in eff_targets
    want_facts = "facts" in eff_targets
    # LOCK — recovery/precision-filter auto-disable when `entities` was not
    # explicitly requested (pre-auto-include). None/empty ⇒ entities in ⇒
    # enabled (back-compat). `summaries` gates the summary enqueue.
    entities_requested = (not targets) or ("entities" in targets)
    summaries_requested = (not targets) or ("summaries" in targets)

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
            schema=schema,
        ),
        deserializer=LLMEntityCandidate.model_validate,
        book_id=book_id,
        chapter_id=chapter_id,
        model_ref=model_ref,
        save_raw=save_raw_extraction,
        schema_key=_p2_schema_key(schema),
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
        schema=schema,
    )
    # C12 — build the R/E/F gather task-list CONDITIONALLY. Only the
    # requested trio ops run; skipped ops yield empty lists. Extractor
    # internals + the per-op cache wrap are unchanged — only the task-list
    # assembly is gated.
    gather_started = time.perf_counter()
    _trio_specs: list[tuple[str, str, Any, Any]] = []
    if want_relations:
        _trio_specs.append(
            ("relations", "relation", extract_relations, LLMRelationCandidate.model_validate))
    if want_events:
        _trio_specs.append(
            ("events", "event", extract_events, LLMEventCandidate.model_validate))
    if want_facts:
        _trio_specs.append(
            ("facts", "fact", extract_facts, LLMFactCandidate.model_validate))

    _trio_results: dict[str, list] = {"relations": [], "events": [], "facts": []}
    if _trio_specs:
        gathered = await asyncio.gather(
            *(
                _p2_cache_wrap(
                    op=op,
                    leaf_text=text,
                    extractor_callable=extractor,
                    extractor_kwargs=common_kwargs,
                    deserializer=deser,
                    book_id=book_id, chapter_id=chapter_id,
                    model_ref=model_ref, save_raw=save_raw_extraction,
                    schema_key=_p2_schema_key(schema),
                )
                for _key, op, extractor, deser in _trio_specs
            )
        )
        for (key, _op, _ex, _ds), res in zip(_trio_specs, gathered):
            _trio_results[key] = res
    relation_cands = _trio_results["relations"]
    event_cands = _trio_results["events"]
    fact_cands = _trio_results["facts"]
    gather_elapsed = time.perf_counter() - gather_started

    # Cycle 73d — optional entity recovery (runs BEFORE filter so the
    # filter operates on enriched candidates). No-op when env unset.
    # C12 LOCK — also auto-disabled when entities ∉ requested targets
    # (they refine the canonical entity set; pointless on an R/E/F-only
    # build where entities run only as anchors).
    if entities_requested:
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
            override=entity_recovery_override,
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

    # D-KG-EXTRACTION-CANON-WIRE — advisory gate, before the write (never
    # blocks it; see _maybe_run_canon_check_gate's docstring).
    await _maybe_run_canon_check_gate(
        session, text=text, user_id=user_id, project_id=project_id,
        model_source=model_source, model_ref=model_ref, llm_client=llm_client,
        job_logs_repo=job_logs_repo, job_id=job_id,
        source_type=source_type, source_id=source_id,
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
        # lane LB / L7B — closed-edge-set write-boundary guard. Prefer the
        # AUTHORITATIVE write_schema (real allow_free_edges) when the caller
        # split it from the advisory prompt schema (/extract-item, L7B); else
        # fall back to the single `schema` (back-compat — byte-identical when
        # write_schema is None). None ⇒ no-op guard (today's behavior).
        schema=write_schema if write_schema is not None else schema,
        triage_repo=triage_repo,  # L7B/C4 — park off-schema edge drops to triage
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
    # C12 — gate the summary enqueue on `summaries ∈ targets` (default
    # all ⇒ enqueue, back-compat).
    if (
        summaries_requested
        and hierarchy_paths is not None
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
    # E0-3 Phase 2a-2 — BYOK billing identity forwarded onto every summary
    # message so summary_processor bills the collaborator (empty ⇒ owner/legacy).
    billing_user_id: str = "",
    billing_llm_model: str = "",
    billing_embedding_model: str = "",
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
        billing_user_id=billing_user_id,
        billing_llm_model=billing_llm_model,
        billing_embedding_model=billing_embedding_model,
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
            billing_user_id=billing_user_id,
            billing_llm_model=billing_llm_model,
            billing_embedding_model=billing_embedding_model,
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
        billing_user_id=billing_user_id,
        billing_llm_model=billing_llm_model,
        billing_embedding_model=billing_embedding_model,
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
    # C13 — glossary pinning. Names of pinned glossary entities, force-injected
    # into EVERY window's known_entities so sparse-but-critical entities (a god
    # in ch1 & ch5000) are always anchored regardless of chapter content. Reuses
    # the proven known_entities seam (name-prefix injection, not a new block).
    pinned_names: list[str] | None = None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClient,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
    # KG customizable-ontology (lane LB) — resolved schema projection (None ⇒
    # static byte-identical behavior). Forwarded to _run_pipeline → SDK.
    schema: ExtractionSchema | None = None,
    # L7B (D-KG-L7B-EXTRACT-ITEM) — authoritative write-boundary schema + triage
    # repo for the schema split (see _run_pipeline). Both None ⇒ byte-identical.
    write_schema: ExtractionSchema | None = None,
    triage_repo: "TriageParkProtocol | None" = None,
    # KN model-roles — endpoint-resolved entity_recovery config (None ⇒ env).
    entity_recovery_override: EntityRecoveryConfig | None = None,
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
        # C13 — prepend pinned names so they reach this window's extract_entities
        # call + every R/E/F extractor (deduped downstream in _run_pipeline).
        known_entities=_merge_pinned(pinned_names, known_entities),
        model_source=model_source,
        model_ref=model_ref,
        llm_client=llm_client,
        anchors=anchors,
        job_logs_repo=job_logs_repo,
        schema=schema,
        write_schema=write_schema,
        triage_repo=triage_repo,
        entity_recovery_override=entity_recovery_override,
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
    # C13 — glossary pinning: see extract_pass2_chat_turn. Force-injected into
    # this window's known_entities so pinned entities are anchored even when the
    # chapter text never mentions them.
    pinned_names: list[str] | None = None,
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
    # C12 — target-typed extraction (None ⇒ all passes; back-compat).
    targets: set[str] | None = None,
    # KG customizable-ontology (lane LB) — resolved schema projection (None ⇒
    # static byte-identical behavior). Forwarded to _run_pipeline → SDK.
    schema: ExtractionSchema | None = None,
    # L7B (D-KG-L7B-EXTRACT-ITEM) — authoritative write-boundary schema + triage
    # repo for the schema split (see _run_pipeline). Both None ⇒ byte-identical.
    write_schema: ExtractionSchema | None = None,
    triage_repo: "TriageParkProtocol | None" = None,
    # KN model-roles — endpoint-resolved entity_recovery config (None ⇒ env).
    entity_recovery_override: EntityRecoveryConfig | None = None,
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
        # C13 — prepend pinned names into every chapter window.
        known_entities=_merge_pinned(pinned_names, known_entities),
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
        targets=targets,
        schema=schema,
        write_schema=write_schema,
        triage_repo=triage_repo,
        entity_recovery_override=entity_recovery_override,
    )
