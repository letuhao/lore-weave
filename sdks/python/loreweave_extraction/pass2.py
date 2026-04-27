"""High-level Pass 2 extraction orchestrator (Phase 4b-α).

Composes the four per-op extractors into the canonical pipeline:

  1. extract_entities (must run first — anchors the others)
  2. Gate: if no entities, skip relation/event/fact (nothing to anchor)
  3. extract_relations + extract_events + extract_facts in parallel via asyncio.gather
  4. Return Pass2Candidates aggregating all four lists

Caller (knowledge-service pass2_orchestrator, worker-ai 4b-γ runner,
future translation/chat-service consumers) is responsible for:
  - Loading known_entities (e.g. glossary anchors)
  - Persisting the candidates (e.g. Neo4j writes via knowledge-service
    pass2_writer)
  - Telemetry hooks before/after each stage
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from loreweave_extraction._types import DroppedHandler, LLMClientProtocol
from loreweave_extraction.extractors.entity import (
    LLMEntityCandidate,
    extract_entities,
)
from loreweave_extraction.extractors.event import (
    LLMEventCandidate,
    extract_events,
)
from loreweave_extraction.extractors.fact import (
    LLMFactCandidate,
    extract_facts,
)
from loreweave_extraction.extractors.relation import (
    LLMRelationCandidate,
    extract_relations,
)

__all__ = ["Pass2Candidates", "extract_pass2"]


@dataclass
class Pass2Candidates:
    """All four candidate lists produced by `extract_pass2`. Caller
    feeds these into a Neo4j write layer (or equivalent) — the library
    has no persistence opinion."""

    entities: list[LLMEntityCandidate] = field(default_factory=list)
    relations: list[LLMRelationCandidate] = field(default_factory=list)
    events: list[LLMEventCandidate] = field(default_factory=list)
    facts: list[LLMFactCandidate] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.entities or self.relations or self.events or self.facts)


async def extract_pass2(
    *,
    text: str,
    known_entities: list[str],
    user_id: str,
    project_id: str | None,
    model_source: Literal["user_model", "platform_model"],
    model_ref: str,
    llm_client: LLMClientProtocol,
    on_dropped: DroppedHandler | None = None,
) -> Pass2Candidates:
    """Run the full Pass 2 extraction pipeline.

    Empty/whitespace `text` returns an empty Pass2Candidates without
    calling the LLM. Empty entity result short-circuits — no point
    extracting relations/events/facts that have nothing to anchor to.

    Raises:
        ExtractionError: on terminal LLM / parse failure in any stage.
    """
    if not text or not text.strip():
        return Pass2Candidates()

    # Step 1 — entities first so subsequent extractors can anchor.
    entities = await extract_entities(
        text=text,
        known_entities=known_entities,
        user_id=user_id,
        project_id=project_id,
        model_source=model_source,
        model_ref=model_ref,
        llm_client=llm_client,
        on_dropped=on_dropped,
    )

    # Gate: if no entities, nothing to anchor.
    if not entities:
        return Pass2Candidates()

    # Steps 2-4 — relation/event/fact run concurrently.
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

    relations, events, facts = await asyncio.gather(
        extract_relations(**extractor_kwargs),
        extract_events(**extractor_kwargs),
        extract_facts(**extractor_kwargs),
    )

    return Pass2Candidates(
        entities=entities,
        relations=relations,
        events=events,
        facts=facts,
    )
