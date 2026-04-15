"""K15.8 — pattern extraction orchestrator.

Top-level `extract_from_chat_turn` entry point. Chains the Pass 1
pattern pipeline into a single call the K14.5 chat handler and the
CLI re-extract tools can use:

  1. Concatenate user_message + assistant_message into a single
     corpus scoped to the same source (a chat turn is one logical
     extraction unit; splitting it would double-count shared
     entities and blow up the source-node cardinality).
  2. neutralize_injection on the raw corpus — observability-only
     call that fires `injection_pattern_matched_total` so dashboards
     see attack shapes at orchestrator level, not only at K15.7
     write time. The sanitized text is deliberately NOT fed to the
     extractors: capitalized-token heuristics and verb patterns
     would misfire on `[FICTIONAL] ignore...` tokens. Per-field
     sanitization of persisted strings is K15.7's job.
  3. K15.2 `extract_entity_candidates(text, glossary_names=...)`.
  4. K15.4 `extract_triples(text, glossary_names=...)`.
  5. K15.5 `extract_negations(text, glossary_names=...)`.
  6. K15.7 `write_extraction(...)` — quarantined Neo4j write.
  7. Return the `ExtractionWriteResult` the writer produced so the
     caller can log a one-line summary.

**Empty input is a no-op.** Whitespace-only messages still upsert
the source node (so later re-extraction on the same turn_id is
idempotent), but skip every extractor and return counts = 0. This
matches K15.7's `test_k15_7_empty_input_still_upserts_source`
contract.

**What this module deliberately does NOT do:**
  - Chunking for long text — K15.9 chapter orchestrator handles
    paragraph splitting; a chat turn fits in one scan.
  - Language detection — detectors already use K15.3
    `split_by_language` internally per-sentence.
  - Timing / SLO enforcement — callers can wrap in their own
    `asyncio.wait_for` if they need the <2s acceptance budget.
  - Promote pending_validation — K18 validator's job.

Reference: KSA §5.1, K15.8 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.db.neo4j_helpers import CypherSession
from app.extraction.entity_detector import extract_entity_candidates
from app.extraction.injection_defense import neutralize_injection
from app.extraction.negation import extract_negations
from app.extraction.pattern_writer import (
    ExtractionWriteResult,
    write_extraction,
)
from app.extraction.triple_extractor import extract_triples

__all__ = [
    "extract_from_chat_turn",
]


async def extract_from_chat_turn(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    user_message: str | None = None,
    assistant_message: str | None = None,
    glossary_names: Iterable[str] | None = None,
    extraction_model: str = "pattern-v1",
) -> ExtractionWriteResult:
    """Run the Pass 1 pattern pipeline on a chat turn.

    Args:
        session: K11.4 CypherSession (multi-tenant guarded).
        user_id: tenant id.
        project_id: optional project scope.
        source_type: K11.8 source type — typically `"chat_message"`
            for chat turns, but callers may pass `"manual"` for
            CLI re-extract invocations.
        source_id: natural key of the source (chat turn id).
        job_id: unique per extraction run. K15.7 uses this for
            evidence-edge idempotency: `(target_id, source_id,
            job_id)` is the dedupe key. Callers MUST pass a fresh
            `job_id` per re-extraction wave — reusing it across
            different turns is safe (different `source_id`s produce
            different edges), but reusing it across re-runs of the
            same turn is the intended no-op. See
            `test_k15_8_same_job_id_different_sources_both_write`
            for the contract.
        user_message: raw user turn text. May be None / empty.
        assistant_message: raw assistant turn text. May be None /
            empty.
        glossary_names: optional known entity display names to
            boost K15.2 candidate signals.
        extraction_model: tag for evidence edges; defaults to
            `"pattern-v1"`.

    Returns:
        `ExtractionWriteResult` from K15.7. Empty input produces
        a result with all counters at 0 but a non-empty source_id
        (source node is still upserted).
    """
    # K15.8-R2/I2: extract per-half, not on the combined corpus.
    # Combining user + assistant into one text leaks cross-half
    # anchoring — K15.4's nearest-neighbor subject/object resolver
    # could pair a subject from the user's question with an object
    # from the assistant's answer and fabricate a relation neither
    # side actually stated. Running the extractors on each half
    # independently keeps sentence neighborhoods within the half
    # that uttered them. K15.7 dedupes entities across halves via
    # its (folded_name, kind_hint) key so repeated entities collapse
    # to one :Entity node with one evidence edge.
    halves = [
        part.strip()
        for part in (user_message, assistant_message)
        if part and part.strip()
    ]
    text = "\n\n".join(halves)

    # Observability-only call on the combined corpus: fires
    # `injection_pattern_matched_total` at orchestrator level so
    # dashboards see attack shapes at intake independently of
    # whether a fact survives to K15.7's write path. The sanitized
    # output is discarded — extractors run on raw halves so their
    # pattern regexes aren't confused by injected `[FICTIONAL] `
    # tokens. R2/I1 (K15.8) closes the entity-name persistence gap
    # at write time.
    if text:
        neutralize_injection(text, project_id=project_id)

    glossary_list = list(glossary_names or ())

    if not halves:
        # Empty turn: still upsert the source so re-extract on the
        # same turn_id stays idempotent at K11.8 level.
        return await write_extraction(
            session,
            user_id=user_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            job_id=job_id,
            extraction_model=extraction_model,
        )

    entities = []
    triples = []
    negations = []
    for half in halves:
        entities.extend(
            extract_entity_candidates(half, glossary_names=glossary_list)
        )
        triples.extend(
            extract_triples(half, glossary_names=glossary_list)
        )
        negations.extend(
            extract_negations(half, glossary_names=glossary_list)
        )

    return await write_extraction(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        job_id=job_id,
        entities=entities,
        triples=triples,
        negations=negations,
        extraction_model=extraction_model,
    )
