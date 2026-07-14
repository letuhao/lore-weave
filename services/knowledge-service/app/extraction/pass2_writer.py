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
import re
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.canonical import canonicalize_entity_name
from app.db.neo4j_repos.entities import resolve_participant_anchors
from app.db.neo4j_repos.entity_status import merge_entity_status
from app.db.neo4j_repos.events import (
    EVENT_ORDER_CHAPTER_STRIDE,
    merge_event,
    rerank_chronological_order,
)
from app.db.neo4j_repos.facts import FACT_TYPES, merge_fact
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
from app.metrics import (
    knowledge_extraction_status_effect_total,
    knowledge_extraction_writer_autocreate_total,
)
from loreweave_extraction.extractors.entity import LLMEntityCandidate
from loreweave_extraction.extractors.event import LLMEventCandidate
from loreweave_extraction.extractors.fact import LLMFactCandidate
from loreweave_extraction.extractors.relation import LLMRelationCandidate
from loreweave_extraction.schema_projection import ExtractionSchema

__all__ = [
    "Pass2WriteResult",
    "write_pass2_extraction",
]

logger = logging.getLogger(__name__)


def _as_uuid(val: object) -> UUID | None:
    """Coerce a tenant id to UUID, or None if it isn't one (caller logs + skips
    the park rather than raising). Production user_id IS a UUID string."""
    if isinstance(val, UUID):
        return val
    if isinstance(val, str):
        try:
            return UUID(val)
        except ValueError:
            return None
    return None


class TriageParkProtocol(Protocol):
    """Minimal structural type for the LH ``TriageRepo.park`` the writer calls to
    park an off-schema edge (L7/C4). Kept as a Protocol so the writer stays
    decoupled from the repo + tests can inject a fake."""

    async def park(
        self,
        *,
        user_id: UUID,
        project_id: str,
        item_type: str,
        signature: str,
        payload: dict[str, Any],
        source: dict[str, Any] | None = ...,
        schema_version: int | None = ...,
    ) -> Any: ...


# KG customizable-ontology (lane LB) — normalize a schema edge-type code the
# SAME way the SDK normalizes a relation predicate (`[^\w]+` runs → `_`,
# lowercased, edge-trimmed) so the write-boundary closed-set comparison is
# apples-to-apples with candidate.predicate (already SDK-normalized).
_PREDICATE_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def _normalize_predicate_code(code: str) -> str:
    return _PREDICATE_NON_WORD_RE.sub("_", code.strip().lower()).strip("_")


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


def _resolve_status_entity_id(
    entity_ref: str,
    chapter_entity_by_canonical_name: dict[str, list[tuple[str, str]]],
    anchor_index: AnchorIndex,
    project_id: str | None,
) -> str | None:
    """A2-S1b — resolve a `status_effect.entity_ref` to a canonical entity id.

    Mirrors the relation endpoint repair (Tier A.1 chapter-local map → Tier A.2
    glossary anchor), but **never autocreates** — a status whose subject can't
    be resolved to a real entity is dropped, not invented (we won't mint a
    `concept` node just to hang a status on). Returns ``None`` when unresolved
    OR when the chapter map has multiple kind-ambiguous candidates for the fold.
    """
    cleaned = _sanitize(entity_ref, project_id)
    if not cleaned.strip():
        return None
    fold = _fold_name(cleaned)
    if not fold:
        return None
    # Tier A.1 — chapter-local entity map (single unambiguous candidate only).
    candidates = chapter_entity_by_canonical_name.get(fold, [])
    if len(candidates) == 1:
        return candidates[0][1]
    if len(candidates) > 1:
        return None  # kind-ambiguous — don't guess
    # Tier A.2 — glossary anchor index (cross-chapter).
    anchor_hit = _find_anchor_for_autocreate(anchor_index, fold)
    if anchor_hit is not None:
        return anchor_hit.canonical_id
    return None


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
    # A2-S1b — :EntityStatus transitions written from event status_effects.
    statuses_merged: int = 0


def _evidence_quote(candidate: object, project_id: str | None) -> str | None:
    """F3 — extract + sanitize the EXACT supporting quote a candidate carries, if
    any, for the EVIDENCED_BY citation edge (evidence-grounding, like the glossary
    `evidences.original_text`). Read forward-compatibly via getattr so the writer
    is ready the moment an extractor surfaces a quote span (`quote` /
    `evidence_text`), without a hard dependency on the SDK candidate shape. None
    when the candidate has no quote → today's behaviour (no quote stored).
    """
    raw = getattr(candidate, "quote", None) or getattr(candidate, "evidence_text", None)
    if not raw or not isinstance(raw, str) or not raw.strip():
        return None
    cleaned = _sanitize(raw, project_id)
    return cleaned.strip() or None


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
    # FD-4 (066 fix): the chapter's own reading-order ordinal (book-service
    # sort_order, 1-based). Used to compute event_order when there is NO part
    # hierarchy (`hierarchy_paths` is part-gated). A FLAT book (chapters, no
    # parts) previously got event_order=None → every status_effect was skipped
    # (skipped_no_event_order) AND the dense timeline axis collapsed. None for
    # genuinely positionless sources (chat turns).
    chapter_index: int | None = None,
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
    # CM5 — provenance (authorship origin) stamped on every node this call
    # writes. Default 'human_authored' (chapters are author-written); the
    # caller passes 'ai_assisted' for composition-generated prose. Accumulates
    # into each node's `provenances` set (a node mentioned by both origins
    # carries both).
    provenance: str = "human_authored",
    # KG customizable-ontology (lane LB) — the resolved project schema
    # projection. None (default) → no closed-set enforcement at the write
    # boundary (today's behavior). When present AND the schema's edge set is
    # CLOSED (``allow_free_edges`` False, non-empty ``edge_predicates``), a
    # relation whose normalized predicate is off-vocab is SKIPPED fail-soft
    # (drop-and-skip per-edge, never fail the batch — spec §5-K7 B2). This is a
    # persistence-boundary belt-and-suspenders: the SDK extractor is the primary
    # gate, but cached/legacy candidates (extracted pre-schema) can still reach
    # the writer, so it re-checks. Triage parking of these drops is the LH lane's
    # job (C4) — this lane only drops + logs.
    schema: ExtractionSchema | None = None,
    # KG customizable-ontology (L7, C4 compose) — when a TriageRepo is supplied,
    # an off-schema edge that the closed-edge guard drops is PARKED to
    # kg_triage_items (unknown_edge_type, signature ``edge:<predicate>``) instead
    # of vanishing, so the human triage queue (lane LH) sees it. None (default) →
    # today's drop-and-log only, so legacy callers are unchanged.
    triage_repo: "TriageParkProtocol | None" = None,
    # PP-5 (spec 08 R7) — WORK-mode extraction (an assistant/diary project). When True, a `preference`
    # fact is COERCED to `statement`: a `preference` maps to a durable behavioral-TRAIT claim ("Minh
    # always pushes back") which, about a real colleague derived from one person's account, is forbidden
    # (Q10 non-goal). Coercing all work-mode preferences to `statement` (what the user REPORTED, on a
    # date) is the conservative guarantee — it also harmlessly demotes the user's own preferences.
    # Default False → the novel/fiction path is unchanged (a novel `preference` "Kai carries a sword"
    # stays a preference).
    work_mode: bool = False,
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

    # KG customizable-ontology (lane LB) — closed-edge-set predicate vocab for
    # the write-boundary guard. None ⇒ no enforcement (today's free-string
    # behavior). Candidates' `predicate` is already normalized (snake_case) by
    # the SDK, and schema codes are normalized identically, so the comparison
    # is apples-to-apples. Empty / allow_free_edges ⇒ None ⇒ no guard.
    _closed_edge_vocab: frozenset[str] | None = None
    if (
        schema is not None
        and not schema.allow_free_edges
        and schema.edge_predicates
    ):
        _closed_edge_vocab = frozenset(
            _normalize_predicate_code(c) for c in schema.edge_predicates
        )

    # KG customizable-ontology (L7, D-KG-L7-CARDINALITY) — per-predicate
    # cardinality keyed by the SAME normalized predicate code the candidates
    # carry, so the lookup is apples-to-apples with `predicate_clean`. None /
    # empty (schema=None or no cardinalities) ⇒ no auto-close (legacy behavior).
    _edge_cardinalities: dict[str, str] = {}
    if schema is not None and schema.edge_cardinalities:
        _edge_cardinalities = {
            _normalize_predicate_code(code): card
            for code, card in schema.edge_cardinalities.items()
        }

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
            provenance=provenance,
            job_id=job_id,
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
            quote=_evidence_quote(ent, project_id),  # F3 — exact-quote citation
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    skipped = 0
    # Cycle 73e: Pass2WriteResult new counters.
    entities_autocreated = 0
    endpoints_repaired_by_name = 0
    autocreate_budget_remaining = autocreate_max  # None = unlimited (when enabled)

    # F3 — the chapter's STORY-time ordinal (chapter sort_order × stride), hoisted
    # here (was computed in Step 4) so BOTH the relation chain (Step 3) and the
    # fact chain (Step 5) can stamp valid_from_ordinal + drive the ordinal-aware
    # interval-split close. It is the SAME dense reading-axis ordinal used for
    # event_order / from_order — unifying story valid-time with the reading axis
    # per §8B. None for genuinely positionless sources (chat turns) → no story
    # interval, no chain maintenance (the legacy path).
    _chapter_ordinal = (
        hierarchy_paths.chapter_index if hierarchy_paths is not None
        else chapter_index
    )
    chapter_base = (
        _chapter_ordinal * EVENT_ORDER_CHAPTER_STRIDE
        if _chapter_ordinal is not None
        else None
    )

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
                    provenance=provenance,
                    job_id=job_id,
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

        # KG customizable-ontology (lane LB) — closed-edge-set guard. When the
        # project schema closes its edge set, drop a relation whose predicate is
        # off-vocab fail-soft (skip per-edge; never fail the batch — §5-K7 B2).
        # rel.predicate is already SDK-normalized; vocab is normalized identically.
        if (
            _closed_edge_vocab is not None
            and rel.predicate not in _closed_edge_vocab
        ):
            logger.info(
                "pass2_writer: dropping off-schema edge predicate=%r "
                "(closed edge set, project=%s, schema=%s)",
                rel.predicate, project_id, schema.label if schema else "?",
            )
            # L7/C4 — park the drop to the human triage queue (unknown_edge_type)
            # rather than silently losing it, when a TriageRepo is wired. Fail-soft:
            # a park error must NEVER break the extraction batch.
            if triage_repo is not None and project_id:
                # Coerce the tenant id OUTSIDE the try, so a non-UUID id surfaces as
                # a distinct error rather than being swallowed by the best-effort
                # park `except` (which would silently lose the edge — review-impl MED).
                park_uid = _as_uuid(user_id)
                if park_uid is None:
                    logger.error(
                        "pass2_writer: cannot park off-schema edge %r — user_id %r is not a UUID",
                        rel.predicate, user_id,
                    )
                else:
                    try:
                        await triage_repo.park(
                            user_id=park_uid,
                            project_id=project_id,
                            item_type="unknown_edge_type",
                            signature=f"edge:{rel.predicate}",
                            payload={
                                "predicate": rel.predicate,
                                "subject_id": resolved_subject_id,
                                "object_id": resolved_object_id,
                            },
                            source={"job_id": job_id, "source_id": source.id},
                            schema_version=schema.schema_version if schema else None,
                        )
                    except Exception:  # noqa: BLE001 — triage is best-effort; never block extraction
                        logger.exception(
                            "pass2_writer: triage park failed for off-schema edge %r", rel.predicate,
                        )
            skipped += 1
            continue

        # Predicate is pre-normalized by K17.5 `_normalize_predicate`
        # (`[^\w]+` → `_`), which already strips most English injection
        # markers. CJK (e.g. `无视指令`) survives normalization because
        # CJK characters are `\w` in Python 3, so sanitize is still
        # load-bearing — see K17.9 predicate CJK test.
        predicate_clean = _sanitize(rel.predicate, project_id)
        # L7 (D-KG-L7-CARDINALITY) — look the predicate's cardinality up from the
        # resolved schema. A `single_active` edge type auto-closes its prior open
        # instance between the same endpoints. The lookup keys on the SDK-normalized
        # predicate code, matching the schema's normalized edge_cardinalities.
        # schema=None / unknown predicate ⇒ None ⇒ no auto-close (legacy behavior).
        edge_cardinality = _edge_cardinalities.get(
            _normalize_predicate_code(predicate_clean)
        )
        result = await create_relation(
            session,
            user_id=user_id,
            subject_id=resolved_subject_id,
            predicate=predicate_clean,
            object_id=resolved_object_id,
            confidence=rel.confidence,
            source_event_id=source.id,
            pending_validation=False,
            # L7 — stamp the resolved-schema version (M3) + the graph_id partition
            # seam (M2, NULL at v1). schema=None → both NULL (legacy, no change).
            schema_version=schema.schema_version if schema else None,
            graph_id=None,
            cardinality=edge_cardinality,
            job_id=job_id,
            # F3 — story valid-time. Stamp the chapter ordinal this edge was
            # established at + drive the ordinal-aware interval-split close (Path A
            # close-prior) so a re-membership/drive supersedes the prior instance
            # in STORY time, correct under out-of-order/backfill arrival.
            # chapter_base=None (chat) ⇒ no ordinal ⇒ chain maintenance skipped.
            valid_from_ordinal=chapter_base,
            # dec-3 (D-KG-INSTORY-EVENTDATE) — OPTIONAL detected in-story date,
            # additive valid-time refinement alongside the chapter ordinal (which
            # stays primary). `getattr(..., None)` reads it WHEN the relation
            # candidate carries one (forward-compatible with an SDK revision that
            # adds the field) and is None otherwise — no SDK change required here,
            # null-safe by construction. The same truncated-ISO shape :Event uses.
            event_date_iso=getattr(rel, "event_date", None),
            maintain_chain=True,
        )
        if result is not None:
            relations_created += 1
        else:
            skipped += 1

    # Step 4 — merge events.
    # CM4: assign event_order = chapter sort_order × 1e6 + within-chapter
    # index, so the reading-order (spoiler) axis is dense at chapter
    # granularity. The chapter ordinal is the P3 hierarchy's `chapter_index`
    # when present, ELSE the chapter's own `chapter_index` (sort_order) param
    # — both ARE the book-service sort_order, so a FLAT book (chapters, no
    # parts) gets the same dense event_order instead of None (FD-4/066: without
    # this fallback, no-part books silently lost status_effects + timeline).
    # Only a genuinely positionless source (chat turn) has neither → None →
    # the timeline null-sinks via coalesce(event_order, INT64_MAX). `idx`
    # advances only for events actually written (skipped empties leave gaps —
    # fine for the strict range filter, keeps the order non-decreasing). The
    # stride is the SHARED EVENT_ORDER_CHAPTER_STRIDE (events.py) — backfill
    # imports the same constant so both write on one scale.
    # F3 — `_chapter_ordinal` + `chapter_base` are computed ONCE above (hoisted
    # before Step 3 so the relation chain can also stamp valid_from_ordinal).
    events_merged = 0
    statuses_merged = 0  # A2-S1b — :EntityStatus transitions written
    dated_written = 0  # CM4 debounce: rerank chrono only if a dated event changed
    idx = 0
    # A2-S1b — chapter handle stamped on each status for retract-by-source +
    # FE display. Prefer the hierarchy chapter_id; fall back to the source_id.
    status_source_chapter = (
        hierarchy_paths.chapter_id if hierarchy_paths is not None else source_id
    )
    for evt in event_list:
        name_clean = _sanitize(evt.name, project_id)
        summary_clean = _sanitize(evt.summary, project_id)
        if not name_clean.strip():
            continue

        event_order = chapter_base + idx if chapter_base is not None else None
        idx += 1

        # NOTE: ``evt.location`` is still intentionally dropped here —
        # merge_event does not yet accept location (Location is likely
        # to land as a :Place entity reference rather than a string,
        # so its own design cycle is needed).
        # C18: ``evt.event_date`` is the structured timeline-filter axis.
        # C18-DEF-01: ``evt.time_cue`` is the free-text narrative hint
        # ("the next morning", "in his youth", "summer 1880") — kept
        # for FE display + parsed best-effort by the C18 backfill
        # helper into event_date_iso when possible.
        sanitized_participants = [
            _sanitize(p, project_id) for p in evt.participants
        ]
        # KG-TL Option A (D-KG-TL-PARTICIPANT-ANCHOR) — resolve each participant
        # name to its glossary entity_id NOW (Pass-1 entities are already in the
        # graph) and store the anchor on the event, so the timeline localizer
        # joins by stored id instead of re-resolving names at read time.
        # Best-effort: an unanchored name → source fallback + marker.
        participant_anchors = await resolve_participant_anchors(
            session,
            user_id=user_id,
            project_id=project_id,
            names=sanitized_participants,
        )
        event = await merge_event(
            session,
            user_id=user_id,
            project_id=project_id,
            title=name_clean,
            summary=summary_clean or None,
            event_order=event_order,
            event_date_iso=evt.event_date,
            time_cue=evt.time_cue,
            participants=sanitized_participants,
            participant_anchors=participant_anchors,
            source_type=source_type,
            confidence=evt.confidence,
            provenance=provenance,
            job_id=job_id,
        )
        events_merged += 1
        if evt.event_date:
            dated_written += 1

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Event",
            target_id=event.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=evt.confidence,
            job_id=job_id,
            quote=_evidence_quote(evt, project_id),  # F3 — exact-quote citation
        )
        if ev is not None and ev.created:
            evidence_edges += 1

        # A2-S1b — consume the event's status_effects → :EntityStatus
        # transitions on the reading axis (from_order = this event's
        # event_order). Evidence-backed via the chapter source so
        # retract-before-reextract (CM3b) drops moved/removed transitions.
        status_effects = getattr(evt, "status_effects", None) or []
        for eff in status_effects:
            # M2 — an event with no event_order (legacy/chat, no hierarchy)
            # has no place on the reading axis. Skip + LOG rather than write a
            # positionless status the composition packer can't gate on.
            if event_order is None:
                logger.warning(
                    "A2-S1b: status_effect skipped — event %r has no "
                    "event_order (legacy/chat, no hierarchy) ref=%r status=%r",
                    name_clean, eff.entity_ref, eff.status,
                )
                knowledge_extraction_status_effect_total.labels(
                    outcome="skipped_no_event_order",
                ).inc()
                continue
            entity_id = _resolve_status_entity_id(
                eff.entity_ref,
                chapter_entity_by_canonical_name,
                anchor_index,
                project_id,
            )
            if entity_id is None:
                logger.info(
                    "A2-S1b: status_effect entity unresolved ref=%r "
                    "status=%r (no chapter-map/anchor match) — skipping",
                    eff.entity_ref, eff.status,
                )
                knowledge_extraction_status_effect_total.labels(
                    outcome="skipped_unresolved",
                ).inc()
                continue
            status_node = await merge_entity_status(
                session,
                user_id=user_id,
                project_id=project_id,
                entity_id=entity_id,
                status=eff.status,
                from_order=event_order,
                source_type=source_type,
                source_chapter=status_source_chapter,
                provenance=provenance,
            )
            statuses_merged += 1
            knowledge_extraction_status_effect_total.labels(
                outcome="persisted",
            ).inc()
            status_ev = await add_evidence(
                session,
                user_id=user_id,
                target_label="EntityStatus",
                target_id=status_node.id,
                source_id=source.id,
                extraction_model=extraction_model,
                confidence=evt.confidence,
                job_id=job_id,
            )
            if status_ev is not None and status_ev.created:
                evidence_edges += 1

    # CM4 — recompute chronological_order for the project, but ONLY when this
    # chapter wrote at least one DATED event (debounce: a chat turn or an
    # all-undated chapter must not trigger an O(project-events) rerank). Same
    # session/Tx as the writes above. project_id is required for the rerank
    # scope; chat_turn callers pass it too, but their events are usually
    # undated so the debounce skips them anyway.
    if dated_written > 0 and project_id:
        await rerank_chronological_order(
            session, user_id=user_id, project_id=project_id,
        )

    # Step 5 — merge facts.
    facts_merged = 0
    for fact in fact_list:
        if fact.type not in FACT_TYPES:
            logger.warning(
                "pass2_writer: skipping fact with unknown type %r (content=%.40r)",
                fact.type, fact.content,
            )
            continue
        # PP-5 (spec 08 R7) — in a WORK/assistant extraction, coerce a `preference` fact to `statement`.
        # A preference is a durable behavioral-trait claim; about a real third party (a colleague),
        # derived from one person's account, it is forbidden (Q10). `statement` = what the user reported.
        fact_type = fact.type
        if work_mode and fact_type == "preference":
            logger.info("pass2_writer: PP-5 coerced a work-mode preference fact → statement")
            fact_type = "statement"
        content_clean = _sanitize(fact.content, project_id)
        if not content_clean.strip():
            continue

        # T2.1 — link the fact to its subject entity (`(:Fact)-[:ABOUT]->(:Entity)`).
        # /review-impl HIGH-1: resolve by the subject NAME via the SAME Tier-A repair
        # status (and relations) use — the extractor's pre-resolved `subject_id`
        # frequently drifts from the writer's merged ids (kind drift / chapter-local
        # resolution), so a plain `subject_id in merged_entity_ids` match silently
        # UNDER-links most facts. Fall back to a pre-resolved id that IS already
        # merged (covers a name the chapter map can't disambiguate). An unresolved
        # subject keeps the fact, just unlinked. `from_order=chapter_base` spoiler-
        # windows the fact to the chapter it was established in (None positionless).
        # NOTE: ``fact.fact_id`` is still advisory — ``merge_fact`` derives its own
        # content-hashed ID (see K17.9 negative assertion test).
        fact_subject_id: str | None = None
        if fact.subject:
            fact_subject_id = _resolve_status_entity_id(
                fact.subject, chapter_entity_by_canonical_name, anchor_index, project_id,
            )
        if fact_subject_id is None and fact.subject_id in merged_entity_ids:
            fact_subject_id = fact.subject_id
        f = await merge_fact(
            session,
            user_id=user_id,
            project_id=project_id,
            type=fact_type,  # PP-5 — work-mode preference coerced to statement above
            content=content_clean,
            confidence=fact.confidence,
            pending_validation=False,
            source_type=source_type,
            provenance=provenance,
            subject_id=fact_subject_id,
            from_order=chapter_base,
            # dec-3 (D-KG-INSTORY-EVENTDATE) — OPTIONAL detected in-story date,
            # additive valid-time refinement alongside the chapter ordinal (which
            # stays primary). Read it WHEN the fact candidate carries one
            # (forward-compatible getattr); None otherwise → null-safe legacy path.
            event_date_iso=getattr(fact, "event_date", None),
            # F3 — drive the ordinal-aware interval-split close over this fact's
            # (subject, type) chain (Path A close-prior). merge_fact internally
            # no-ops the chain when there's no subject or no story ordinal, so a
            # positionless / subjectless fact stays on the legacy path.
            maintain_chain=True,
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
            quote=_evidence_quote(fact, project_id),  # F3 — exact-quote citation
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
        statuses_merged=statuses_merged,
    )
