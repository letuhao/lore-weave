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

import time
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
from app.metrics import (
    pass1_candidates_extracted_total,
    pass1_extraction_duration_seconds,
)

__all__ = [
    "extract_from_chat_turn",
    "extract_from_chapter",
]


# K15.9: chunk size for chapter-scale extraction. Chapters frequently
# run 3–10k characters; K15.2's capitalized-phrase scan and K15.4's
# per-sentence SVO regex are each O(n) per pattern and do a quadratic-
# ish pass when they call back into entity detection per sentence.
# Splitting into ~4k-char chunks keeps a single pass bounded without
# fragmenting sentences — we split on paragraph boundaries (blank
# lines) first and only fall back to hard slicing when a single
# paragraph exceeds the budget.
_CHAPTER_CHUNK_CHAR_BUDGET = 4000


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
    # K15.12-R1/I3: start the timer and open the try/finally BEFORE
    # any work, so the histogram observes even if glossary_names
    # iteration or injection sanitisation raises. Otherwise a "latency
    # went dark" alert would miss hard failures in the pre-extract
    # prep stage.
    started = time.perf_counter()
    try:
        halves = [
            part.strip()
            for part in (user_message, assistant_message)
            if part and part.strip()
        ]
        text = "\n\n".join(halves)

        # Observability-only call on the combined corpus: fires
        # `injection_pattern_matched_total` at orchestrator level so
        # dashboards see attack shapes at intake independently of
        # whether a fact survives to K15.7's write path. The
        # sanitized output is discarded — extractors run on raw
        # halves so their pattern regexes aren't confused by injected
        # `[FICTIONAL] ` tokens. R2/I1 (K15.8) closes the entity-name
        # persistence gap at write time.
        if text:
            neutralize_injection(text, project_id=project_id)

        glossary_list = list(glossary_names or ())

        if not halves:
            # Empty turn: still upsert the source so re-extract on
            # the same turn_id stays idempotent at K11.8 level.
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

        pass1_candidates_extracted_total.labels(
            kind="entity", source_kind="chat_turn"
        ).inc(len(entities))
        pass1_candidates_extracted_total.labels(
            kind="triple", source_kind="chat_turn"
        ).inc(len(triples))
        pass1_candidates_extracted_total.labels(
            kind="negation", source_kind="chat_turn"
        ).inc(len(negations))

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
    finally:
        pass1_extraction_duration_seconds.labels(
            source_kind="chat_turn"
        ).observe(time.perf_counter() - started)


def _split_chapter_into_chunks(
    text: str,
    *,
    budget: int = _CHAPTER_CHUNK_CHAR_BUDGET,
) -> list[str]:
    """Split a chapter into extraction-sized chunks on paragraph
    boundaries. Paragraphs larger than `budget` are hard-sliced on
    character count — K15.3's per-sentence splitter inside each
    extractor still sees sentence boundaries correctly, so a hard
    slice at character level only risks bisecting one sentence per
    oversized paragraph. For Track 1 hobby-scale text that's
    acceptable; the K17 LLM pass re-anchors facts by content hash
    on Pass 2, so a one-sentence bisect doesn't leak into the
    promoted graph.

    Returns a list of non-empty chunks. An empty / whitespace-only
    chapter returns `[]`.
    """
    if budget <= 0:
        raise ValueError(f"budget must be > 0, got {budget}")
    if not text or not text.strip():
        return []

    # K15.9-R2/I1: normalize line endings before splitting on "\n\n".
    # Windows-authored chapters (Word exports, Notepad, glossary-service
    # DB dumps from Windows hosts) use "\r\n\r\n" between paragraphs,
    # which contains no literal "\n\n" substring. Without normalization,
    # `split("\n\n")` would return a single element containing the whole
    # body, forcing every chapter through the hard-slice fallback and
    # silently losing paragraph-boundary signal.
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > budget:
            # Flush whatever is buffered, then hard-slice the big
            # paragraph directly into the output.
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for start in range(0, len(para), budget):
                chunks.append(para[start : start + budget])
            continue

        projected = current_len + len(para) + (2 if current else 0)
        if current and projected > budget:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len = projected

    if current:
        chunks.append("\n\n".join(current))

    return chunks


async def extract_from_chapter(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    chapter_text: str,
    glossary_names: Iterable[str] | None = None,
    extraction_model: str = "pattern-v1",
    chunk_char_budget: int = _CHAPTER_CHUNK_CHAR_BUDGET,
) -> ExtractionWriteResult:
    """Run the Pass 1 pattern pipeline on a chapter-sized input.

    Differs from `extract_from_chat_turn` in three ways:
      1. Input is a single text body (no user/assistant split).
      2. Text is split into paragraph-boundary chunks bounded by
         `chunk_char_budget` so K15.2's capitalized-phrase scan and
         K15.4's per-sentence SVO regex don't run quadratic passes
         over a full chapter in one shot.
      3. All chunks share the same `source_id` / `job_id`, so
         K15.7's `(folded_name, kind_hint)` dedupe collapses
         entities that repeat across chunks, and `add_evidence`
         idempotency makes re-extraction a no-op.

    The writer is called exactly once with the accumulated
    candidates from every chunk. Writing per-chunk would be
    equally correct but would fire the extraction_source upsert
    N times, inflate per-write metric samples, and make
    `skipped_missing_endpoint` counters harder to read.

    Args:
        session: K11.4 CypherSession.
        user_id: tenant id.
        project_id: optional project scope.
        source_type: K11.8 source type — typically `"chapter"`.
        source_id: natural key of the chapter (e.g., chapter uuid).
        job_id: unique per extraction run.
        chapter_text: the full chapter body. Empty / whitespace-only
            is a no-op that still upserts the source.
        glossary_names: optional known entity display names.
        extraction_model: evidence-edge tag; defaults to `"pattern-v1"`.
        chunk_char_budget: override the default chunk size for
            testing; production callers should leave it at the
            module default.

    Returns:
        `ExtractionWriteResult` from K15.7 reflecting the *combined*
        counts across all chunks (post-dedupe at the writer).
    """
    # K15.12-R1/I3: open try/finally BEFORE chunking and injection
    # so a ValueError from _split_chapter_into_chunks or an iterator
    # failure on glossary_names still records the latency.
    started = time.perf_counter()
    try:
        chunks = _split_chapter_into_chunks(
            chapter_text, budget=chunk_char_budget
        )

        # Orchestrator-level injection observability on the full
        # body. Same rationale as extract_from_chat_turn: sanitized
        # output is discarded; extractors consume raw chunks so
        # regex patterns aren't confused by injected `[FICTIONAL] `
        # tokens.
        if chapter_text and chapter_text.strip():
            neutralize_injection(chapter_text, project_id=project_id)

        glossary_list = list(glossary_names or ())

        if not chunks:
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
        for chunk in chunks:
            entities.extend(
                extract_entity_candidates(chunk, glossary_names=glossary_list)
            )
            triples.extend(
                extract_triples(chunk, glossary_names=glossary_list)
            )
            negations.extend(
                extract_negations(chunk, glossary_names=glossary_list)
            )

        pass1_candidates_extracted_total.labels(
            kind="entity", source_kind="chapter"
        ).inc(len(entities))
        pass1_candidates_extracted_total.labels(
            kind="triple", source_kind="chapter"
        ).inc(len(triples))
        pass1_candidates_extracted_total.labels(
            kind="negation", source_kind="chapter"
        ).inc(len(negations))

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
    finally:
        pass1_extraction_duration_seconds.labels(
            source_kind="chapter"
        ).observe(time.perf_counter() - started)
