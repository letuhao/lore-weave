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

__all__ = ["Pass2Candidates", "FilterStatus", "extract_pass2"]


# Cycle-72 Pass2 precision filter status. "skipped" = filter not run
# (default); "applied" = filter ran and returned verdicts; "degraded"
# = filter LLM call failed and Pass A candidates were returned
# unchanged. Caller can inspect to know whether downstream metrics
# should attribute results to filter or raw extraction.
FilterStatus = Literal["applied", "degraded", "skipped"]


@dataclass
class Pass2Candidates:
    """All four candidate lists produced by `extract_pass2`. Caller
    feeds these into a Neo4j write layer (or equivalent) — the library
    has no persistence opinion.

    Cycle 72 — Pass2 precision filter extension:
      - `filter_status` marks whether the optional precision filter
        ran. Default ``"skipped"`` preserves the pre-cycle-72 contract
        for every caller that doesn't pass a filter config.
      - `filter_coverage` records the per-category fraction of items
        the filter actually returned a verdict for (1.0 when no items
        existed in the category — vacuously covered).
    """

    entities: list[LLMEntityCandidate] = field(default_factory=list)
    relations: list[LLMRelationCandidate] = field(default_factory=list)
    events: list[LLMEventCandidate] = field(default_factory=list)
    facts: list[LLMFactCandidate] = field(default_factory=list)
    filter_status: FilterStatus = "skipped"
    filter_coverage: dict[str, float] = field(default_factory=dict)

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
    precision_filter: "PrecisionFilterConfig | None" = None,
    on_filter_decision: "DecisionHandler | None" = None,
    entity_recovery: "EntityRecoveryConfig | None" = None,
    on_recovery_decision: "RecoveryDecisionHandler | None" = None,
    # B2-B-b2 — per-op raw system-prompt overrides {op: {"system": str}}.
    # When present for an op, that op's system prompt is replaced by the custom
    # text + an SDK-controlled output-contract reminder (DESIGN §2.5). None /
    # absent op → the default prompt. Only "system" is honored (the user message
    # is always the raw chapter text).
    prompt_overrides: "dict[str, dict[str, str]] | None" = None,
) -> Pass2Candidates:
    """Run the full Pass 2 extraction pipeline.

    Empty/whitespace `text` returns an empty Pass2Candidates without
    calling the LLM. Empty entity result short-circuits — no point
    extracting relations/events/facts that have nothing to anchor to.

    Cycle 72 — when ``precision_filter`` is non-None, runs the
    ``apply_precision_filter`` pass after the gather to drop items the
    filter LLM says are unsupported by the source text. When None
    (default), filter is skipped and the returned
    ``Pass2Candidates.filter_status`` is ``"skipped"`` — zero behavior
    change for pre-cycle-72 callers.

    Args:
        precision_filter: optional config controlling the precision
            filter pass. ``None`` (default) = no filter.
        on_filter_decision: optional per-item telemetry callback
            forwarded to ``apply_precision_filter``. Ignored when
            ``precision_filter is None``.

    Raises:
        ExtractionError: on terminal LLM / parse failure in any
            extractor stage. Filter LLM failure does NOT raise — see
            ``apply_precision_filter`` (degrades to Pass A with
            ``filter_status="degraded"``).
    """
    if not text or not text.strip():
        return Pass2Candidates()

    # B2-B-b2 — per-op system-prompt override lookup ({} when none).
    _po = prompt_overrides or {}

    def _sys(op: str) -> str | None:
        return (_po.get(op) or {}).get("system")

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
        prompt_override_system=_sys("entity"),
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
        extract_relations(**extractor_kwargs, prompt_override_system=_sys("relation")),
        extract_events(**extractor_kwargs, prompt_override_system=_sys("event")),
        extract_facts(**extractor_kwargs, prompt_override_system=_sys("fact")),
    )

    candidates = Pass2Candidates(
        entities=entities,
        relations=relations,
        events=events,
        facts=facts,
    )

    # Cycle 73d — optional entity recovery (runs BEFORE precision filter).
    # Promotes "real" entities the extractor missed (so writer doesn't
    # cascade-skip relations referencing them) and drops relations whose
    # subjects/objects are abstract phrases.
    if entity_recovery is not None:
        from loreweave_extraction.entity_recovery import recover_missing_entities

        candidates = await recover_missing_entities(
            candidates,
            text=text,
            config=entity_recovery,
            user_id=user_id,
            project_id=project_id,
            llm_client=llm_client,
            on_decision=on_recovery_decision,
        )

    # Cycle 72 — optional precision filter pass.
    if precision_filter is not None:
        # Lazy import to break the SDK module import cycle (pass2_filter
        # imports Pass2Candidates + FilterStatus from this module).
        from loreweave_extraction.pass2_filter import apply_precision_filter

        candidates = await apply_precision_filter(
            candidates,
            text=text,
            config=precision_filter,
            user_id=user_id,
            llm_client=llm_client,
            on_decision=on_filter_decision,
        )

    return candidates
