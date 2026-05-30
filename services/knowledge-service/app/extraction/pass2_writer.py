"""K17.8 — Pass 2 (LLM) extraction writer.

Maps LLM extraction candidates from K17.4–K17.7 to K11 Neo4j repository
calls with provenance tracking via EVIDENCED_BY edges.

**Relationship to K15.7 (Pass 1 writer):**
  - K15.7 writes pattern-extracted data with ``pending_validation=True``
    (quarantine).
  - K17.8 writer writes LLM-extracted data with ``pending_validation=False``
    (trusted).

**Key invariant:** every persisted text field goes through
``neutralize_injection`` before hitting Neo4j.

**Entity ID resolution:** K17.4–K17.7 candidates already carry
``canonical_id`` from the extraction step. The writer merges entities
first, then validates that relation endpoints / event participants /
fact subjects reference actually-merged entity IDs before creating
downstream edges. Unresolvable endpoints are cascade-skipped — unless
cycle 73e's Tier A name-repair OR Tier B autocreate resolves them.

**Cycle 73e — Tier A + Tier B for unresolved relation endpoints:**
  - **Tier A.1 (free, always-on):** chapter-local canonical_name map
    repairs cases where relation subject/object name matches an
    extracted entity but the resolved IDs don't (kind-mismatch, etc.).
  - **Tier A.2 (free, always-on):** anchor index pre-check; if the
    name matches a glossary anchor of any kind, reuse the anchor's
    canonical_id (no new node). Distinct outcome label so dashboards
    can distinguish "anchor pre-existed" from "autocreate minted new".
  - **Tier B (env-gated, default off):** MERGE a new ``:Entity`` node
    with ``kind="concept"``, ``auto_created=True``,
    ``confidence=min(rel.confidence, 0.3)``. Per-chapter cap via
    ``autocreate_max`` kwarg; noise heuristic skips compound subjects.

**Tx boundary (cycle 73e M5):** ``write_pass2_extraction`` runs all
its writes inside a single ``CypherSession`` per chapter. Autocreate
failures (any exception from ``resolve_or_merge_entity``) are caught
and logged as ``warning`` + emit ``outcome="error"`` metric; the
specific relation cascade-skips but the surrounding chapter Tx is
NOT aborted. Concurrent writers on the same chapter are not
expected (one-active-job-per-project K17.9) — no new race surface.

Dependencies: K11.5 (entities), K11.6 (relations), K11.7 (events,
facts), K11.8 (provenance).

Reference: KSA §5.2, K17.8 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md; cycle 73e plan in
``docs/plans/2026-05-30-pass2-writer-autocreate.md``.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.canonical import canonicalize_entity_name
from app.db.neo4j_repos.events import merge_event
from app.db.neo4j_repos.facts import merge_fact
from app.db.repositories.entity_alias_map import EntityAliasMapRepo
from app.db.neo4j_repos.provenance import add_evidence, upsert_extraction_source
from app.db.neo4j_repos.relations import create_relation
from app.extraction.anchor_loader import Anchor
from app.extraction.entity_resolver import (
    AnchorIndex,
    build_anchor_index,
    resolve_or_merge_entity,
)
from app.extraction.hierarchy_writer import HierarchyPaths, upsert_for_chapter
from app.extraction.injection_defense import neutralize_injection
from app.metrics import knowledge_extraction_writer_autocreate_total
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate
from loreweave_extraction.extractors.fact import LLMFactCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate

__all__ = [
    "Pass2WriteResult",
    "write_pass2_extraction",
]

logger = logging.getLogger(__name__)


# Cycle 73e noise heuristic — char-length + word-count combined. The
# word-count alone breaks for CJK (`"齐天大圣孙悟空"`.split() == 1).
# Char-budget catches long CJK strings. Trailing/leading punctuation
# stripped first (handles `，。、！？` and ASCII equivalents).
#
# WORD_BUDGET=3 is aggressive: any name with 4+ space-separated tokens
# is treated as noise (cycle 73c findings: "home peace and comfort"
# 4 words, "fancy words and refined speech" 5 words — both compound
# narrative subjects, not real entities). Compound legitimate names
# ("Sir William and Lady Lucas") are false-negative — they cascade-
# skip as in pre-73e behaviour. User can opt-in via lower threshold
# for specific projects if pattern emerges.
_NOISE_CHAR_BUDGET = 60
_NOISE_WORD_BUDGET = 3
_NOISE_STRIP_CHARS = "，。、？！,.?!:;()[]{}\"' \t\n"


def _is_noise_subject(name: str) -> bool:
    """True if `name` looks like a compound noise subject ("fancy
    words and refined speech", "home peace and comfort") rather than
    a real entity. Conservative: word-budget catches English compounds,
    char-budget catches long CJK strings.
    """
    stripped = name.strip(_NOISE_STRIP_CHARS)
    if not stripped:
        return True
    if len(stripped) > _NOISE_CHAR_BUDGET:
        return True
    if len(stripped.split()) > _NOISE_WORD_BUDGET:
        return True
    return False


def _find_anchor_for_autocreate(
    anchor_index: AnchorIndex, fold: str,
) -> Anchor | None:
    """Tier A.2 anchor pre-check: scan ``anchor_index`` for ANY kind
    matching ``fold``. Relations don't carry kind info on the
    autocreate path, so we don't pre-select a kind — first match wins.
    O(n) on anchor_index size (per-chapter, small).
    """
    for (k_fold, _kind), anchor in anchor_index.items():
        if k_fold == fold:
            return anchor
    return None


def _fold_name(name: str) -> str:
    """Folded name used as key in chapter_entity_by_canonical_name +
    anchor pre-check lookups. Mirrors ``entity_resolver._fold`` exactly
    so keys are interchangeable across both indices."""
    return canonicalize_entity_name(name).strip().casefold()


def _bump_autocreate_metric(role: Literal["subject", "object"], outcome: str) -> None:
    """Per-role per-outcome counter increment. Outcomes are pre-seeded
    in `metrics.py` so the labels enum is closed."""
    knowledge_extraction_writer_autocreate_total.labels(
        role=role, outcome=outcome,
    ).inc()


class Pass2WriteResult(BaseModel):
    """Summary of what the Pass 2 writer persisted."""

    source_id: str
    entities_merged: int = 0
    # Cycle 73e: Tier-B autocreates that minted new :Entity nodes
    # (anchor pre-existed → tier_a_anchor_repair counted separately
    # via metric, NOT incremented here).
    entities_autocreated: int = 0
    # Cycle 73e: per-endpoint name-repair count (Tier A.1 or A.2).
    # Per-endpoint not per-relation — a relation needing both subject
    # AND object repair bumps this twice.
    endpoints_repaired_by_name: int = 0
    relations_created: int = 0
    events_merged: int = 0
    facts_merged: int = 0
    evidence_edges: int = 0
    skipped_missing_endpoint: int = 0


def _sanitize(text: str, project_id: str | None) -> str:
    """Injection-sanitize a text field before persisting.

    KSA §5.1.5 Defense 2 (extraction-time). See K15.6
    ``neutralize_injection`` for the pattern set and
    ``tests/unit/test_pass2_writer.py`` K17.9 section for
    regression coverage on every persisted text field.
    """
    cleaned, _ = neutralize_injection(text, project_id=project_id)
    return cleaned


async def write_pass2_extraction(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    entities: list[LLMEntityCandidate] | None = None,
    relations: list[LLMRelationCandidate] | None = None,
    events: list[LLMEventCandidate] | None = None,
    facts: list[LLMFactCandidate] | None = None,
    extraction_model: str = "llm-v1",
    anchors: list[Anchor] | None = None,
    alias_map_repo: EntityAliasMapRepo | None = None,
    # P3 (D2 + D2a): optional hierarchy paths. When supplied, the writer
    # MERGEs the Book/Part/Chapter/Scene hierarchy in the same session
    # BEFORE entity writes (per D2a Tx boundary — same CypherSession,
    # which IS the chapter Tx in the existing per-chapter pattern).
    # When None: legacy flat-write behavior preserved (chat_turn path +
    # back-compat for callers that don't yet pass hierarchy).
    hierarchy_paths: HierarchyPaths | None = None,
    # Cycle 73e: writer autocreate gates.
    #   ``autocreate_enabled=False`` (default) → Tier A.1 + A.2 free
    #   repairs run unconditionally (cheap; bug-fixes silent cascade);
    #   Tier B autocreate is SKIPPED → unresolved-after-A endpoints
    #   cascade-skip as before (pre-73e behaviour preserved).
    #
    #   ``autocreate_enabled=True`` → Tier B runs; ``autocreate_max``
    #   bounds per-chapter autocreate count (``None`` = unlimited).
    autocreate_enabled: bool = False,
    autocreate_max: int | None = None,
) -> Pass2WriteResult:
    """Persist Pass 2 LLM extraction candidates to Neo4j.

    All candidate lists are optional — the writer persists whatever
    is provided. This supports running extractors individually (e.g.
    entities only) or all together.

    Args:
        session: K11.4 CypherSession (multi-tenant guarded).
        user_id: tenant id.
        project_id: optional project scope.
        source_type: K11.8 source type (``"chapter"`` / ``"chat_message"``).
        source_id: natural key of the source.
        job_id: unique per extraction run — dedupes evidence edges.
        entities: K17.4 entity candidates.
        relations: K17.5 relation candidates.
        events: K17.6 event candidates.
        facts: K17.7 fact candidates.
        extraction_model: tag for evidence edges.

    Returns:
        Pass2WriteResult with per-kind counters.
    """
    entity_list = entities or []
    relation_list = relations or []
    event_list = events or []
    fact_list = facts or []

    # P3 (D2 + D2a): MERGE Book/Part/Chapter/Scene hierarchy BEFORE entity
    # writes when hierarchy_paths supplied. Same CypherSession = same Tx
    # per chapter — partial failure rolls back hierarchy + entities together.
    # Per-entity :MENTIONED_IN -> :Scene edges are NOT written here in the
    # MVP (P2 chapter-cache loses per-scene attribution); per-scene edges
    # arrive with D-P2-PER-SCENE-FANOUT.
    if hierarchy_paths is not None:
        await upsert_for_chapter(session, hierarchy_paths)

    # K13.0 resolver: pre-build anchor index. Empty (default) preserves
    # pre-K13.0 behavior where every candidate mints a new :Entity.
    anchor_index = build_anchor_index(anchors or [])

    # Step 1 — upsert provenance source (idempotent).
    source = await upsert_extraction_source(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
    )

    entities_merged = 0
    evidence_edges = 0
    merged_entity_ids: set[str] = set()
    # Cycle 73e: per-fold map of (kind, entity_id) for every entity merged
    # in THIS chapter. Used by Tier A.1 relation endpoint repair when a
    # relation references an entity by name but with a mismatched/missing
    # ID. Multi-kind collisions (same fold mapped to entities of different
    # kinds) yield `kind_ambiguous` outcome — repair is skipped and Tier B
    # also skipped (we won't pollute with a 3rd `concept` entity when the
    # graph already has 2 disambiguated kinds for the same name).
    chapter_entity_by_canonical_name: dict[str, list[tuple[str, str]]] = {}

    # Step 2 — merge entities.
    for ent in entity_list:
        name_clean = _sanitize(ent.name, project_id)
        if not name_clean.strip():
            continue
        # NOTE: ``ent.aliases`` is intentionally dropped here — K11.5
        # ``merge_entity`` does not yet accept an ``aliases`` parameter.
        # Alias persistence is tracked for K18+. See K17.9 negative
        # assertion tests pinning this behavior.
        entity = await resolve_or_merge_entity(
            session,
            anchor_index,
            user_id=user_id,
            project_id=project_id,
            name=name_clean,
            kind=ent.kind,
            source_type=source_type,
            confidence=ent.confidence,
            alias_map_repo=alias_map_repo,
        )
        merged_entity_ids.add(entity.id)
        entities_merged += 1

        # Cycle 73e: index for Tier A.1 chapter map lookups.
        fold = _fold_name(name_clean)
        if fold:
            chapter_entity_by_canonical_name.setdefault(fold, []).append(
                (ent.kind, entity.id),
            )

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Entity",
            target_id=entity.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=ent.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    skipped = 0
    # Cycle 73e: Pass2WriteResult new counters.
    entities_autocreated = 0
    endpoints_repaired_by_name = 0
    autocreate_budget_remaining = autocreate_max  # None = unlimited (when enabled)

    # Step 3 — create relations.
    relations_created = 0
    for rel in relation_list:
        # Cycle 73e — Tier A.1 + A.2 + B endpoint resolution. Resolves
        # subject + object via free repairs first, falling through to
        # Tier B autocreate when env-enabled.
        #
        # /review-impl round 2 H2 fold: resolve into LOCAL variables
        # instead of mutating rel.subject_id / rel.object_id, so the
        # caller's relation_list is not silently rewritten between
        # write attempts.
        resolved_subject_id = rel.subject_id
        resolved_object_id = rel.object_id
        for role, raw_endpoint_name, current_id in (
            ("subject", rel.subject, resolved_subject_id),
            ("object", rel.object, resolved_object_id),
        ):
            if current_id and current_id in merged_entity_ids:
                continue  # already resolved + merged — skip repair path

            # H1 fold: sanitize BEFORE folding so the key matches the
            # one Step 2 built from sanitized `ent.name`. Without this,
            # any name a sanitizer mutates (e.g. injection-stripped)
            # would silently miss Tier A.1 and autocreate a duplicate.
            endpoint_name = _sanitize(raw_endpoint_name, project_id)
            if not endpoint_name.strip():
                _bump_autocreate_metric(role, "invalid_name")
                continue
            fold = _fold_name(endpoint_name)
            if not fold:
                _bump_autocreate_metric(role, "invalid_name")
                continue

            # Tier A.1 — chapter-local name map.
            candidates = chapter_entity_by_canonical_name.get(fold, [])
            if len(candidates) == 1:
                if role == "subject":
                    resolved_subject_id = candidates[0][1]
                else:
                    resolved_object_id = candidates[0][1]
                endpoints_repaired_by_name += 1
                _bump_autocreate_metric(role, "tier_a_name_repair")
                continue
            if len(candidates) > 1:
                # Multi-kind: don't repair, don't autocreate (would
                # create a 3rd `concept` entity polluting worse).
                _bump_autocreate_metric(role, "kind_ambiguous")
                continue

            # Tier A.2 — anchor index (cross-chapter, glossary-backed).
            anchor_hit = _find_anchor_for_autocreate(anchor_index, fold)
            if anchor_hit is not None:
                if role == "subject":
                    resolved_subject_id = anchor_hit.canonical_id
                else:
                    resolved_object_id = anchor_hit.canonical_id
                merged_entity_ids.add(anchor_hit.canonical_id)
                chapter_entity_by_canonical_name.setdefault(fold, []).append(
                    (anchor_hit.kind, anchor_hit.canonical_id),
                )
                endpoints_repaired_by_name += 1
                _bump_autocreate_metric(role, "tier_a_anchor_repair")
                # H3 fold: bump anchor's evidence accrual for this
                # extraction source. Without this, anchors referenced
                # only via relations (never extracted as entities) would
                # never have evidence_count bumped, stale-ing K11.5b's
                # recompute_anchor_score for the next pass.
                anchor_ev = await add_evidence(
                    session,
                    user_id=user_id,
                    target_label="Entity",
                    target_id=anchor_hit.canonical_id,
                    source_id=source.id,
                    extraction_model=extraction_model,
                    confidence=rel.confidence or 0.0,
                    job_id=job_id,
                )
                if anchor_ev is not None and anchor_ev.created:
                    evidence_edges += 1
                continue

            # Tier B — env-gated autocreate.
            if not autocreate_enabled:
                continue  # cascade-skip below
            if (
                autocreate_budget_remaining is not None
                and autocreate_budget_remaining <= 0
            ):
                # M4 fold: bump `cap_exhausted` always; bump
                # `cap_exhausted_high_conf` ADDITIONALLY for tuning
                # signal. Matches eval driver semantics so dashboards
                # don't need to sum the two labels for "total exhausted".
                _bump_autocreate_metric(role, "cap_exhausted")
                if (rel.confidence or 0.0) > 0.8:
                    _bump_autocreate_metric(role, "cap_exhausted_high_conf")
                continue
            if _is_noise_subject(endpoint_name):
                _bump_autocreate_metric(role, "noise_skipped")
                continue

            try:
                auto_entity = await resolve_or_merge_entity(
                    session,
                    anchor_index,
                    user_id=user_id,
                    project_id=project_id,
                    name=endpoint_name,
                    kind="concept",
                    source_type=source_type,
                    confidence=min(rel.confidence or 0.0, 0.3),
                    alias_map_repo=alias_map_repo,
                    auto_created=True,
                )
            except Exception:
                logger.warning(
                    "cycle 73e autocreate failed role=%s name=%r "
                    "— cascade-skipping relation",
                    role, raw_endpoint_name, exc_info=True,
                )
                _bump_autocreate_metric(role, "error")
                continue

            if role == "subject":
                resolved_subject_id = auto_entity.id
            else:
                resolved_object_id = auto_entity.id
            merged_entity_ids.add(auto_entity.id)
            chapter_entity_by_canonical_name.setdefault(fold, []).append(
                ("concept", auto_entity.id),
            )
            entities_autocreated += 1
            if autocreate_budget_remaining is not None:
                autocreate_budget_remaining -= 1
            _bump_autocreate_metric(role, "tier_b_autocreated")

        # Original cascade-skip — still load-bearing for endpoints that
        # remained unresolved after Tier A + Tier B. Use the LOCAL
        # resolved IDs (H2 fold) so retries see the unchanged input rel.
        if not resolved_subject_id or not resolved_object_id:
            skipped += 1
            continue
        if (
            resolved_subject_id not in merged_entity_ids
            or resolved_object_id not in merged_entity_ids
        ):
            skipped += 1
            continue

        # Predicate is pre-normalized by K17.5 `_normalize_predicate`
        # (`[^\w]+` → `_`), which already strips most English injection
        # markers. CJK (e.g. `无视指令`) survives normalization because
        # CJK characters are `\w` in Python 3, so sanitize is still
        # load-bearing — see K17.9 predicate CJK test.
        predicate_clean = _sanitize(rel.predicate, project_id)
        result = await create_relation(
            session,
            user_id=user_id,
            subject_id=resolved_subject_id,
            predicate=predicate_clean,
            object_id=resolved_object_id,
            confidence=rel.confidence,
            source_event_id=source.id,
            pending_validation=False,
        )
        if result is not None:
            relations_created += 1
        else:
            skipped += 1

    # Step 4 — merge events.
    events_merged = 0
    for evt in event_list:
        name_clean = _sanitize(evt.name, project_id)
        summary_clean = _sanitize(evt.summary, project_id)
        if not name_clean.strip():
            continue

        # NOTE: ``evt.location`` is still intentionally dropped here —
        # merge_event does not yet accept location (Location is likely
        # to land as a :Place entity reference rather than a string,
        # so its own design cycle is needed).
        # C18: ``evt.event_date`` is the structured timeline-filter axis.
        # C18-DEF-01: ``evt.time_cue`` is the free-text narrative hint
        # ("the next morning", "in his youth", "summer 1880") — kept
        # for FE display + parsed best-effort by the C18 backfill
        # helper into event_date_iso when possible.
        event = await merge_event(
            session,
            user_id=user_id,
            project_id=project_id,
            title=name_clean,
            summary=summary_clean or None,
            event_date_iso=evt.event_date,
            time_cue=evt.time_cue,
            participants=[
                _sanitize(p, project_id) for p in evt.participants
            ],
            source_type=source_type,
            confidence=evt.confidence,
        )
        events_merged += 1

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Event",
            target_id=event.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=evt.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    # Step 5 — merge facts.
    facts_merged = 0
    for fact in fact_list:
        content_clean = _sanitize(fact.content, project_id)
        if not content_clean.strip():
            continue

        # NOTE: ``fact.subject`` and ``fact.subject_id`` are intentionally
        # dropped here — K11.7 ``merge_fact`` does not yet accept a
        # subject. Tracked for K18+. Additionally, ``fact.fact_id`` is
        # treated as advisory: K11.7 ``merge_fact`` derives its own ID
        # from the sanitized content hash, not the candidate's raw-
        # content-derived ``fact_id``. See K17.9 negative assertion test.
        f = await merge_fact(
            session,
            user_id=user_id,
            project_id=project_id,
            type=fact.type,
            content=content_clean,
            confidence=fact.confidence,
            pending_validation=False,
            source_type=source_type,
        )
        facts_merged += 1

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Fact",
            target_id=f.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=fact.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    return Pass2WriteResult(
        source_id=source.id,
        entities_merged=entities_merged,
        entities_autocreated=entities_autocreated,
        endpoints_repaired_by_name=endpoints_repaired_by_name,
        relations_created=relations_created,
        events_merged=events_merged,
        facts_merged=facts_merged,
        evidence_edges=evidence_edges,
        skipped_missing_endpoint=skipped,
    )
