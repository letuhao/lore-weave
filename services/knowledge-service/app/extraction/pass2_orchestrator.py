"""K17.8 — Pass 2 (LLM) extraction orchestrator.

Top-level entry points for running the K17.4–K17.7 LLM extraction
pipeline and persisting results to Neo4j via the Pass 2 writer.

Pipeline:
  1. K17.4 ``extract_entities`` → entity candidates
  2. **Gate:** if no entities, skip steps 3–4 (nothing to anchor)
  3. K17.5/K17.6/K17.7 run concurrently via ``asyncio.gather``
  4. ``write_pass2_extraction`` persists everything

**Mirrors K15.8** (Pass 1 orchestrator) with two entry points:
  - ``extract_pass2_chat_turn`` — handles user/assistant message split
  - ``extract_pass2_chapter`` — handles single text body

**What this module deliberately does NOT do:**
  - Chunking — the caller (K16.6 job runner) handles chapter splitting
  - Cost tracking — the caller manages budget via K16.1 state machine
  - Pass 1 reconciliation — deferred to K18 validator (promotes
    quarantined Pass 1 facts when Pass 2 confirms them)

Dependencies: K17.4–K17.7 (extractors), K17.8 writer, K11 (Neo4j).

Reference: KSA §5.2, K17.8 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from typing import Any, Literal
from uuid import UUID

from app.clients.llm_client import LLMClient
from app.clients.provider_client import ProviderClient
from app.db.neo4j_helpers import CypherSession
from app.db.repositories.job_logs import JobLogsRepo
from app.extraction.anchor_loader import Anchor
from app.extraction.llm_entity_extractor import extract_entities
from app.extraction.llm_event_extractor import extract_events
from app.extraction.llm_fact_extractor import extract_facts
from app.extraction.llm_relation_extractor import extract_relations
from app.extraction.pass2_writer import Pass2WriteResult, write_pass2_extraction

__all__ = [
    "extract_pass2_chat_turn",
    "extract_pass2_chapter",
]

logger = logging.getLogger(__name__)


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
    client: ProviderClient | None = None,
    llm_client: LLMClient | None = None,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
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
        )

    started = time.perf_counter()

    # Step 1 — K17.4: extract entities (must run first).
    # Phase 4a-α: when llm_client is supplied, this routes through the
    # SDK + gateway job pattern (entity_extraction op + paragraphs/15
    # chunking + per-op JSON aggregator). Other 3 extractors stay on
    # legacy provider_client until 4a-β.
    entities = await extract_entities(
        text=text,
        known_entities=known_entities,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        client=client,
        llm_client=llm_client,
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
        )

    entity_names = [e.name for e in entities]
    all_known = list(set(known_entities + entity_names))

    # Steps 2-4 — K17.5/K17.6/K17.7 run concurrently.
    extractor_kwargs = dict(
        text=text,
        entities=entities,
        known_entities=all_known,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        client=client,
    )

    gather_started = time.perf_counter()
    relation_cands, event_cands, fact_cands = await asyncio.gather(
        extract_relations(**extractor_kwargs),
        extract_events(**extractor_kwargs),
        extract_facts(**extractor_kwargs),
    )
    gather_elapsed = time.perf_counter() - gather_started

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
        # /review-impl L2: duration_ms on write event for symmetry
        # with the entities + gather events. Writes can be the slow
        # step on large batches (50+ relations + evidence edges);
        # operators benefit from seeing its share of the total.
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
    return write_result


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
    client: ProviderClient | None = None,
    llm_client: LLMClient | None = None,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
) -> Pass2WriteResult:
    """Run the Pass 2 LLM pipeline on a chat turn.

    Concatenates user + assistant messages, then runs the full
    K17.4→K17.7 pipeline. Same source_type/source_id pattern as
    K15.8's ``extract_from_chat_turn``.

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
        client=client,
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
    client: ProviderClient | None = None,
    llm_client: LLMClient | None = None,
    anchors: list[Anchor] | None = None,
    job_logs_repo: JobLogsRepo | None = None,
) -> Pass2WriteResult:
    """Run the Pass 2 LLM pipeline on a chapter.

    Single text body — no user/assistant split. The caller (K16.6
    job runner) handles chunking if needed.

    `anchors`: optional K13.0 glossary-anchor index (see
    ``extract_pass2_chat_turn`` for details).

    Phase 4a-α: when ``llm_client`` is supplied, the entity extraction
    step routes through the loreweave_llm SDK (job pattern + chunking
    + per-op JSON aggregator). Other 3 extractors stay on legacy
    ``client`` until 4a-β.
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
        client=client,
        llm_client=llm_client,
        anchors=anchors,
        job_logs_repo=job_logs_repo,
    )
