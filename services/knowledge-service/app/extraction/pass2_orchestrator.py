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
from typing import Literal

from app.clients.provider_client import ProviderClient
from app.db.neo4j_helpers import CypherSession
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
) -> Pass2WriteResult:
    """Core pipeline shared by chat_turn and chapter entry points."""
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
        )

    started = time.perf_counter()

    # Step 1 — K17.4: extract entities (must run first).
    entities = await extract_entities(
        text=text,
        known_entities=known_entities,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        client=client,
    )

    logger.info(
        "Pass 2 entity extraction: %d candidates in %.1fs",
        len(entities), time.perf_counter() - started,
    )

    # Gate: if no entities, nothing to anchor relations/events/facts.
    # Write entities only (empty list) and return.
    if not entities:
        return await write_pass2_extraction(
            session,
            user_id=user_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            job_id=job_id,
            extraction_model=model_ref,
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

    relation_cands, event_cands, fact_cands = await asyncio.gather(
        extract_relations(**extractor_kwargs),
        extract_events(**extractor_kwargs),
        extract_facts(**extractor_kwargs),
    )

    elapsed = time.perf_counter() - started
    logger.info(
        "Pass 2 extraction complete: %d entities, %d relations, "
        "%d events, %d facts in %.1fs",
        len(entities), len(relation_cands),
        len(event_cands), len(fact_cands), elapsed,
    )

    # Step 5 — write everything to Neo4j.
    return await write_pass2_extraction(
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
    )


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
) -> Pass2WriteResult:
    """Run the Pass 2 LLM pipeline on a chat turn.

    Concatenates user + assistant messages, then runs the full
    K17.4→K17.7 pipeline. Same source_type/source_id pattern as
    K15.8's ``extract_from_chat_turn``.
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
) -> Pass2WriteResult:
    """Run the Pass 2 LLM pipeline on a chapter.

    Single text body — no user/assistant split. The caller (K16.6
    job runner) handles chunking if needed.
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
    )
