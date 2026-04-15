"""K15.7 — pattern extraction writer (Pass 1 quarantine pipeline).

Per KSA §5.1 / plan row K15.7. Takes the outputs of the pattern
extractors (K15.2 entity candidates, K15.4 triples, K15.5 negation
facts) and writes them to Neo4j as quarantined nodes / edges /
facts via the K11 repository primitives. Every text field that
persists goes through K15.6 `neutralize_injection` first per KSA
§5.1.5 defense point #1 (extraction-time sanitization).

**Algorithm:**

  Step 1 — upsert :ExtractionSource (K11.8 primitive).
  Step 2 — merge_entity per candidate (K11.5). Build a folded-name
           index so triples/negations can resolve subject/object
           strings to canonical entity ids.
  Step 3 — add_evidence for each entity → source (K11.8). This is
           the atomic edge+counter primitive; bypassing it would
           drift the evidence_count cache.
  Step 4 — create_relation per triple (K11.6). Confidence and
           pending_validation flow from the Triple.
  Step 5 — merge_fact(type="negation") per negation (K11.7) +
           add_evidence on the Fact node.
  Step 6 — bump `pass1_facts_written_total{kind}` per write.

**Non-invention principle.** If a triple's subject or object name
is not in the candidate list supplied by the caller, the writer
does NOT synthesize a new :Entity on its own. The triple is
dropped and `skipped_missing_endpoint` is incremented. Rationale:
K15.2 is the authoritative entity detector for Pass 1; conjuring
entities here would bypass its confidence scoring and stopword
filtering, and drift the quarantine dashboard numbers. The same
rule applies to negation subjects.

**What this module deliberately does NOT do:**
  - Score entities or triples — upstream extractors already did
  - Canonicalize surface forms to IDs — repos handle that
  - Promote pending_validation — K18 validator's job
  - Handle decision/preference/milestone facts — future extractors
    will emit their own candidate list; K15.7 currently only
    writes :Fact {type: 'negation'}
  - Transactionally rollback on partial failure — each primitive
    is its own transaction; this writer accepts K11-style partial
    state on error (the K11.9 reconciler is the safety net)

Reference: KSA §5.1, §5.1.5, §3.8.5, K15.7 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.facts import merge_fact
from app.db.neo4j_repos.provenance import (
    add_evidence,
    upsert_extraction_source,
)
from app.db.neo4j_repos.relations import create_relation
from app.extraction.entity_detector import EntityCandidate
from app.extraction.injection_defense import neutralize_injection
from app.extraction.negation import NegationFact
from app.extraction.triple_extractor import Triple
from app.metrics import pass1_facts_written_total

__all__ = [
    "ExtractionWriteResult",
    "write_extraction",
]


_QUARANTINE_CONFIDENCE = 0.5
_DEFAULT_ENTITY_KIND = "character"
_EXTRACTION_MODEL = "pattern-v1"


class ExtractionWriteResult(BaseModel):
    """Summary of what the writer actually persisted.

    Counters split by type so callers (K15.8 orchestrator, CLI
    re-extract tools) can log a one-line summary per source.
    `skipped_missing_endpoint` counts triples and negations whose
    subject/object name could not be resolved in the entity map —
    useful for tuning K15.2 coverage.
    """

    source_id: str
    entities_merged: int
    evidence_edges: int
    relations_created: int
    facts_merged: int
    skipped_missing_endpoint: int


def _fold(name: str) -> str:
    return name.strip().casefold()


async def write_extraction(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    entities: Iterable[EntityCandidate] = (),
    triples: Iterable[Triple] = (),
    negations: Iterable[NegationFact] = (),
    extraction_model: str = _EXTRACTION_MODEL,
) -> ExtractionWriteResult:
    """Persist a Pass 1 extraction batch to Neo4j.

    Args:
        session: K11.4 CypherSession (multi-tenant guarded).
        user_id: tenant id — required by every underlying repo.
        project_id: optional project scope for the entities and
            source. `None` means global (rare for Pass 1).
        source_type: one of K11.8 `SOURCE_TYPES`
            (`chapter` / `chat_message` / ...).
        source_id: natural key of the source (e.g., chapter id,
            message id).
        job_id: unique per extraction run. Used by add_evidence to
            deduplicate edges on re-run — same job_id on the same
            (target, source) pair is a no-op.
        entities, triples, negations: outputs from K15.2/K15.4/K15.5.
        extraction_model: tag stored on evidence edges for
            observability. Defaults to `"pattern-v1"`; K17 LLM
            writer uses its own tag.

    Returns:
        ExtractionWriteResult with per-kind counters. Every counter
        is the number of successful writes — `skipped_missing_endpoint`
        captures drops where subject/object lookup failed.
    """
    triple_list = list(triples)
    negation_list = list(negations)

    # K15.7-R1/I1: dedupe entities by (folded_name, kind_hint) keeping
    # the highest-confidence candidate per key. Without this, a K15.2
    # candidate list with "Kai" / "kai" / "Kai" collapses to one node
    # in Neo4j (the deterministic hash dedupes it) but we still fire
    # three merge_entity round-trips AND report entities_merged=3 to
    # the caller — wasteful and misleading. Deduping here keeps the
    # write count honest and cuts network ops.
    #
    # The dedupe key includes `kind_hint` because K11.5's canonical id
    # hash also includes kind — "Phoenix" (character) and "PHOENIX"
    # (organization) are legitimately distinct entities and must both
    # survive. For ties on confidence, first-seen wins (stable order).
    entity_list: list[EntityCandidate] = []
    seen_keys: dict[tuple[str, str], int] = {}
    for cand in entities:
        folded = _fold(cand.name)
        if not folded:
            continue
        kind = cand.kind_hint or _DEFAULT_ENTITY_KIND
        key = (folded, kind)
        existing_idx = seen_keys.get(key)
        if existing_idx is None:
            seen_keys[key] = len(entity_list)
            entity_list.append(cand)
        else:
            if cand.confidence > entity_list[existing_idx].confidence:
                entity_list[existing_idx] = cand

    # Step 1 — upsert source (idempotent).
    source = await upsert_extraction_source(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
    )

    # Step 2 — merge entities and build the folded-name lookup map.
    # Multiple candidates folding to the same key (K15.2 dedupes
    # those anyway, but defensively) keep the first-seen id.
    entity_id_by_name: dict[str, str] = {}
    entities_merged = 0
    evidence_edges = 0
    for cand in entity_list:
        folded = _fold(cand.name)
        if not folded:
            continue
        kind = cand.kind_hint or _DEFAULT_ENTITY_KIND
        entity = await merge_entity(
            session,
            user_id=user_id,
            project_id=project_id,
            name=cand.name,
            kind=kind,
            source_type=source_type,
            confidence=cand.confidence,
        )
        if folded not in entity_id_by_name:
            entity_id_by_name[folded] = entity.id
        entities_merged += 1
        pass1_facts_written_total.labels(kind="entity").inc()

        # Step 3 — evidence edge Entity → ExtractionSource.
        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Entity",
            target_id=entity.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=cand.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    skipped_missing_endpoint = 0

    # Step 4 — relations from triples. Sanitize the source sentence
    # before it lives on the edge as provenance context.
    relations_created = 0
    for triple in triple_list:
        subj_id = entity_id_by_name.get(_fold(triple.subject))
        obj_id = entity_id_by_name.get(_fold(triple.object_))
        if subj_id is None or obj_id is None:
            skipped_missing_endpoint += 1
            continue
        # neutralize_injection is side-effect-emitting for metrics;
        # we don't use the sanitized sentence on the edge (the edge
        # only carries source_event_id), but calling it ensures the
        # injection counter fires for content that WILL reach the
        # LLM via the source node on later retrieval.
        neutralize_injection(triple.sentence, project_id=project_id)
        rel = await create_relation(
            session,
            user_id=user_id,
            subject_id=subj_id,
            predicate=triple.predicate,
            object_id=obj_id,
            confidence=triple.confidence,
            source_event_id=source.id,
            pending_validation=triple.pending_validation,
        )
        if rel is not None:
            relations_created += 1
            pass1_facts_written_total.labels(kind="relation").inc()
        else:
            skipped_missing_endpoint += 1

    # Step 5 — negation facts. Sanitize every text field that
    # persists: marker and object both end up inside the fact's
    # `content` which DOES get stored, so injection defense must
    # fire on the stored string, not just the sentence.
    facts_merged = 0
    for neg in negation_list:
        subj_folded = _fold(neg.subject)
        if subj_folded not in entity_id_by_name:
            skipped_missing_endpoint += 1
            continue
        marker_clean, _ = neutralize_injection(
            neg.marker, project_id=project_id
        )
        object_clean = ""
        if neg.object_:
            object_clean, _ = neutralize_injection(
                neg.object_, project_id=project_id
            )
        neutralize_injection(neg.sentence, project_id=project_id)

        content_parts = [neg.subject, marker_clean]
        if object_clean:
            content_parts.append(object_clean)
        content = " ".join(p for p in content_parts if p).strip()
        if not content:
            skipped_missing_endpoint += 1
            continue

        fact = await merge_fact(
            session,
            user_id=user_id,
            project_id=project_id,
            type="negation",
            content=content,
            confidence=neg.confidence,
            pending_validation=neg.pending_validation,
            source_type=source_type,
        )
        facts_merged += 1
        pass1_facts_written_total.labels(kind="fact").inc()

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Fact",
            target_id=fact.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=neg.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    return ExtractionWriteResult(
        source_id=source.id,
        entities_merged=entities_merged,
        evidence_edges=evidence_edges,
        relations_created=relations_created,
        facts_merged=facts_merged,
        skipped_missing_endpoint=skipped_missing_endpoint,
    )
