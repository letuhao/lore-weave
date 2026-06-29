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
from collections.abc import Awaitable, Callable
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
from loreweave_extraction.schema_projection import ExtractionSchema

__all__ = [
    "Pass2Candidates",
    "FilterStatus",
    "extract_pass2",
    "TRIO_TARGETS",
    "normalize_targets",
]


# C12 — target-typed extraction taxonomy. The PLURAL contract names that
# map 1:1 to SDK extractors. `summaries` is orchestrator-gated (NOT an
# SDK op) so it never appears here. Requesting any TRIO target forces
# `entities` in (they anchor to entity names).
TRIO_TARGETS = frozenset({"relations", "events", "facts"})
_ALL_SDK_TARGETS = frozenset({"entities"}) | TRIO_TARGETS


def normalize_targets(targets: "set[str] | frozenset[str] | None") -> frozenset[str]:
    """C12 — resolve the effective SDK target set.

    Back-compat: ``None`` or empty ⇒ ALL passes (every pre-C12 caller is
    unaffected). Dependent targets ({relations,events,facts}) silently
    force ``entities`` in (they anchor to entity names — a missing
    auto-include yields empty relations, not an error). Non-SDK tokens
    (e.g. ``summaries``, ``lore``) are dropped here — the orchestrator
    gates those. A target set that carries ONLY non-SDK tokens collapses
    to ``{entities}`` (the mandatory first pass; no R/E/F).
    """
    if not targets:
        return frozenset(_ALL_SDK_TARGETS)
    requested = {t for t in targets if t in _ALL_SDK_TARGETS}
    if requested & TRIO_TARGETS:
        requested.add("entities")
    # Always include entities — it is the mandatory anchor pass and the
    # only SDK op that can run standalone. A targets set with no SDK op
    # at all (e.g. {"summaries"}) still runs the entity pass.
    requested.add("entities")
    return frozenset(requested)


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
    # C12 — target-typed extraction. None / empty ⇒ ALL passes run
    # (back-compat for translation-service + every other consumer).
    # Plural contract names: entities/relations/events/facts. Requesting
    # any of {relations,events,facts} auto-includes `entities`.
    # `summaries` (orchestrator op) is ignored here. When entities is the
    # only effective target, recovery/precision-filter are auto-disabled
    # (they no-op against an entity-only or non-canonical set).
    targets: "set[str] | frozenset[str] | None" = None,
    # C12 — cap on parallel LLM calls in the R/E/F gather. None ⇒ unbounded
    # (current behaviour, back-compat). A positive int gates the gather with
    # an asyncio.Semaphore so at most N of the requested trio ops run at once.
    concurrency_level: int | None = None,
    # KG customizable-ontology (lane LB) — the resolved project schema projection.
    # None (default — worker-ai + translation never pass it) → byte-identical
    # static prompts + Literal validation. A non-None ExtractionSchema activates
    # the dynamic prompt/validation path in every per-op extractor.
    schema: ExtractionSchema | None = None,
    # D-KG-WORKER-GRADED-EFFORT — graded reasoning effort applied to the core
    # entity/relation/event/fact extraction LLM calls. Default "none" emits NO
    # reasoning wire fields, so every existing caller (worker-ai + translation +
    # knowledge pass2 consumers that don't pass it) is byte-identical. A graded
    # value (low/medium/high) spreads {reasoning_effort, chat_template_kwargs}
    # into each op's input. The recovery + precision-filter passes are NOT graded
    # (they stay force-thinking-off — cheap structural passes; see the worker spec
    # D1 carve-out). The value is trusted as-is (already clamped to the caller's
    # grant at mint time, knowledge-side) — the SDK does no re-clamp.
    reasoning_effort: str = "none",
    # bug #34 — optional immediate-cancel hook threaded down to EVERY core
    # extraction submit_and_wait (entity + relation/event/fact). The base
    # loreweave_llm.Client.wait_terminal polls it so an in-flight LLM call is
    # aborted the moment the owning KG-build job is cancelled. None (default —
    # worker-ai chat/glossary callers + translation + knowledge pass2 consumers
    # that don't opt in) ⇒ no cancellation polling, byte-identical behaviour.
    # NOT applied to the recovery/precision-filter passes (cheap structural
    # passes, same carve-out as reasoning_effort).
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
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

    # C12 — resolve effective SDK target set (None/empty ⇒ all; dependent
    # targets auto-include entities). `entities` always present.
    eff_targets = normalize_targets(targets)
    want_relations = "relations" in eff_targets
    want_events = "events" in eff_targets
    want_facts = "facts" in eff_targets
    # LOCK — recovery/precision-filter auto-disable when `entities ∉ targets`
    # (the user's EXPLICIT request, pre-auto-include). They refine the
    # canonical entity set; when entities run only as anchors for an
    # events/relations-only build, recovery/filter would waste an LLM call
    # (recover) or operate on a set the user didn't ask to curate (filter).
    # None / empty targets ⇒ all ⇒ entities requested ⇒ enabled (back-compat).
    entities_requested = (not targets) or ("entities" in targets)

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
        schema=schema,
        reasoning_effort=reasoning_effort,
        cancel_check=cancel_check,
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
        schema=schema,
        reasoning_effort=reasoning_effort,
        cancel_check=cancel_check,
    )

    # C12 — build the gather task-list CONDITIONALLY. Only the requested
    # trio ops run; skipped ops yield empty lists. Extractor internals are
    # unchanged — only the task-list assembly is gated.
    _trio_specs: list[tuple[str, Any, str]] = []
    if want_relations:
        _trio_specs.append(("relations", extract_relations, "relation"))
    if want_events:
        _trio_specs.append(("events", extract_events, "event"))
    if want_facts:
        _trio_specs.append(("facts", extract_facts, "fact"))

    _results: dict[str, list] = {"relations": [], "events": [], "facts": []}
    if _trio_specs:
        # C12 — when concurrency_level caps parallelism, wrap each trio call in
        # a shared Semaphore so at most N run at once; else unbounded gather
        # (current behaviour). The cap applies to the requested ops only.
        if concurrency_level is not None and concurrency_level >= 1:
            _sem = asyncio.Semaphore(concurrency_level)

            async def _gated(coro):
                async with _sem:
                    return await coro

            gathered = await asyncio.gather(
                *(
                    _gated(extractor(**extractor_kwargs, prompt_override_system=_sys(op)))
                    for _, extractor, op in _trio_specs
                )
            )
        else:
            gathered = await asyncio.gather(
                *(
                    extractor(**extractor_kwargs, prompt_override_system=_sys(op))
                    for _, extractor, op in _trio_specs
                )
            )
        for (key, _, _op), res in zip(_trio_specs, gathered):
            _results[key] = res

    candidates = Pass2Candidates(
        entities=entities,
        relations=_results["relations"],
        events=_results["events"],
        facts=_results["facts"],
    )

    # Cycle 73d — optional entity recovery (runs BEFORE precision filter).
    # Promotes "real" entities the extractor missed (so writer doesn't
    # cascade-skip relations referencing them) and drops relations whose
    # subjects/objects are abstract phrases.
    if entity_recovery is not None and entities_requested:
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
    if precision_filter is not None and entities_requested:
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
