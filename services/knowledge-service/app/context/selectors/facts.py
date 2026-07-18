"""K18.2 — L2 fact selector with intent-driven hop count + temporal grouping.

Runs against Neo4j after the K18.2a intent classifier has extracted
entity names from the user's message. For each mentioned entity:

  - Always: 1-hop relations involving the entity (via
    ``find_relations_for_entity``, both directions, confidence ≥ 0.8,
    excluding pending-validation rows and archived peers).
  - When ``intent.hop_count == 2``: additionally 2-hop traversals
    (via ``find_relations_2hop``) so relational queries surface
    "A knows someone who knows B" paths.
  - Always: negative facts (``:Fact`` nodes with ``type='negation'``)
    touching the mentioned entities so the LLM respects "X does NOT
    know Y"-style guardrails.

**Temporal grouping (Commit 1 simplification).** The full KSA §4.2
spec buckets results into ``<current>``, ``<recent>``,
``<background>``, ``<negative>``. Bucketing by chapter requires the
evidence edges to carry chapter_index, which is not yet wired through
Pass 2. For this commit everything non-negation is placed in
``background`` — the bucketing will be refined in a follow-up once
chapter provenance lands on edges. Negation is still its own bucket.

**Multi-tenant safety.** Every underlying repo call carries ``user_id``
and ``project_id``; the selector does not touch Cypher directly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.context.intent.classifier import Intent, IntentResult
from app.context.selectors.glossary import extract_candidates
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import find_entities_by_name
from app.db.neo4j_repos.facts import list_facts_by_type
from app.db.neo4j_repos.relations import (
    Relation,
    RelationHop,
    find_relations_2hop,
    find_relations_for_entity,
)

logger = logging.getLogger(__name__)

__all__ = [
    "L2FactResult",
    "select_l2_facts",
    "format_relation",
    "format_relation_hop",
    "select_bridge_anchor_names",
    "expand_facts_from_passages",
]


# Per-selector caps. The formatter will compress beyond this, but the
# Cypher-level limits keep the total payload from blowing up on
# celebrity characters with hundreds of edges.
_MAX_1HOP_PER_ENTITY = 20
_MAX_2HOP_PER_ENTITY = 10
_MAX_NEGATIVES = 15

# 2-hop fan-out gate. ``find_relations_2hop`` REQUIRES a non-empty
# ``hop1_types`` so a hub entity (a main character with hundreds of
# outgoing edges) doesn't multiply at the second hop and blow the
# query budget. We restrict the first hop to the DURABLE structural
# predicates — kinship, mentorship, authority/affiliation, and
# social-state — which are exactly the edges that form meaningful
# "A — via — B" relational chains. Spatial/action predicates
# (``located_in``, ``owns``, ``follows`` …) are deliberately excluded:
# they fan out hard (a place has many residents) and rarely answer a
# RELATIONAL query. Mirrors the canonical relation vocabulary in
# loreweave_extraction/prompts/relation_extraction_system.md.
_RELATIONAL_HOP1_PREDICATES: list[str] = [
    # Kinship
    "child_of", "stepchild_of", "sibling_of", "stepsibling_of", "married_to",
    # Mentorship
    "mentor_of", "disciple_of", "instructs",
    # Authority / affiliation
    "commands", "serves", "imprisoned_by", "works_for", "member_of",
    # Social / state
    "knows", "trusts", "enemy_of",
]


@dataclass
class L2FactResult:
    """Grouped fact strings ready for the Mode 3 XML formatter.

    Each string is a human-readable fact sentence. The formatter in
    ``modes/full.py`` wraps these in ``<fact>`` elements; deciding
    which sub-block they go into is this selector's job.
    """

    current: list[str] = field(default_factory=list)
    recent: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.current) + len(self.recent)
            + len(self.background) + len(self.negative)
        )


def format_relation(r: Relation) -> str:
    """Render a 1-hop relation as ``subject - predicate - object``.

    Handles the case where the endpoint names failed to project (e.g.
    relation to an archived entity that slipped through): the relation
    is rendered with ``<unknown>`` placeholders rather than crashing.
    """
    subj = r.subject_name or "<unknown>"
    obj = r.object_name or "<unknown>"
    return f"{subj} — {r.predicate} — {obj}"


def format_relation_hop(hop: RelationHop) -> str:
    """Render a 2-hop path as ``A - p1 - Via - p2 - B``."""
    return (
        f"{hop.hop1.subject_name or '<unknown>'} — "
        f"{hop.hop1.predicate} — "
        f"{hop.via_name} — "
        f"{hop.hop2.predicate} — "
        f"{hop.hop2.object_name or '<unknown>'}"
    )


async def _resolve_entity_ids(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    entity_names: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Look up `(name, canonical_id)` pairs for each mentioned entity.

    Names that don't resolve to any entity are dropped silently —
    absence detection (K18.5) picks them up.
    """
    resolved: list[tuple[str, str]] = []
    for name in entity_names:
        matches = await find_entities_by_name(
            session,
            user_id=user_id,
            project_id=project_id,
            name=name,
        )
        if matches:
            # Prefer the first match (repo orders anchored > discovered).
            resolved.append((name, matches[0].id))
    return resolved


# WS-4C — the source tag memory_remember writes onto its facts (canonical:
# app/tools/executor.py TOOL_FACT_SOURCE_TYPE). Facts carrying it are the
# assistant's explicit "remember this" decisions/preferences/milestones —
# project-level, unanchored, written below the 0.8 L2 gate on purpose.
_TOOL_FACT_SOURCE_TYPE = "llm_tool_call"


async def _select_tool_facts(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    result: L2FactResult,
    min_confidence: float,
    limit: int,
) -> None:
    """WS-4C — admit memory_remember / llm_tool_call facts into per-turn L2.

    These are PROJECT-LEVEL session canon ("we decided the villain dies in
    ch.10", "the user wants a grimdark tone") — deliberately unanchored (no
    :ABOUT entity edge) and written at 0.7, so the entity-anchored relation/
    negation path never surfaced them. Selected project-wide (not gated on the
    message naming an entity, since they aren't about a specific entity) at
    their own lower floor. All go to `current` (each is a full sentence that
    carries its own polarity, so a saved negation reads fine as a plain fact) —
    keeping `negative` purely entity-anchored so the caller's widened-retry
    miss-detection isn't perturbed. Mutates `result` in place.
    """
    tool_facts = await list_facts_by_type(
        session,
        user_id=user_id,
        project_id=project_id,
        type=None,  # any of decision/preference/milestone/negation
        source_type=_TOOL_FACT_SOURCE_TYPE,
        min_confidence=min_confidence,
        limit=limit,
    )
    for fact in tool_facts:
        text = (fact.content or "").strip()
        if text:
            result.current.append(text)


async def select_l2_facts(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    intent: IntentResult,
    min_confidence: float = 0.8,
    tool_facts: bool = True,
    tool_fact_min_confidence: float = 0.7,
    tool_facts_limit: int = 20,
) -> L2FactResult:
    """Gather L2 fact strings for the intent's entity set.

    Args:
        session: CypherSession (multi-tenant guarded).
        user_id: tenant.
        project_id: project scope — required (Mode 3 is project-only).
        intent: K18.2a result; drives hop count and which entities to
            query.
        min_confidence: default 0.8 (matches KSA §4.2 L2 RAG loader).
        tool_facts: WS-4C — also admit project-level memory_remember /
            llm_tool_call facts (default on). Runs regardless of whether the
            message named an entity (these facts are project-level, not
            entity-anchored).
        tool_fact_min_confidence: floor for the tool-fact branch (0.7, below
            the 0.8 entity-fact gate — that lower floor is the whole point).
        tool_facts_limit: cap on tool-facts injected per turn.

    Returns:
        L2FactResult with separate buckets. Entity-anchored relations/negations
        need the intent to name an entity; the tool-fact branch does not.
    """
    result = L2FactResult()

    # WS-4C tool facts first — project-level, entity-independent, so they are
    # recalled even on a turn whose message names no entity (the early-return
    # below only skips the entity-ANCHORED material).
    #
    # In its OWN try/except (same discipline as the 2-hop call below): this is a
    # STRICTLY-ADDITIVE recall branch, and it runs FIRST — an unguarded failure
    # here would propagate out of select_l2_facts, be swallowed by Mode 3's
    # `_safe_l2_facts`, and silently zero the ENTIRE L2 layer (relations +
    # negations) that would otherwise have succeeded. A non-positive limit is
    # skipped rather than passed down (list_facts_by_type raises on limit<=0, so
    # an operator setting CONTEXT_L2_TOOL_FACTS_LIMIT=0 to "disable" the feature
    # would otherwise kill all L2 memory).
    if tool_facts and tool_facts_limit > 0:
        try:
            await _select_tool_facts(
                session,
                user_id=user_id,
                project_id=project_id,
                result=result,
                min_confidence=tool_fact_min_confidence,
                limit=tool_facts_limit,
            )
        except Exception:  # noqa: BLE001 — additive branch, never nuke L2
            logger.warning(
                "WS-4C: tool-fact selection failed for project %s; "
                "continuing with entity-anchored L2 only",
                project_id,
                exc_info=True,
            )

    if not intent.entities:
        return result

    resolved = await _resolve_entity_ids(
        session,
        user_id=user_id,
        project_id=project_id,
        entity_names=intent.entities,
    )
    if not resolved:
        return result

    seen_relations: set[str] = set()

    for _name, entity_id in resolved:
        # 1-hop (always).
        one_hop = await find_relations_for_entity(
            session,
            user_id=user_id,
            project_id=project_id,
            entity_id=entity_id,
            min_confidence=min_confidence,
            limit=_MAX_1HOP_PER_ENTITY,
        )
        for r in one_hop:
            if r.id in seen_relations:
                continue
            seen_relations.add(r.id)
            result.background.append(format_relation(r))

        # 2-hop (relational intent only). ``hop1_types`` is REQUIRED by
        # the repo (selectivity gate) — omitting it raises TypeError,
        # which the Mode-3 ``_safe_l2_facts`` wrapper would swallow,
        # silently zeroing the ENTIRE L2 layer (1-hop + negations) for
        # exactly the RELATIONAL queries that most need graph reasoning.
        # Keep the 2-hop call in its own try/except so a future 2-hop
        # failure degrades to 1-hop-only rather than discarding the
        # 1-hop facts already gathered above.
        if intent.hop_count >= 2:
            try:
                two_hop = await find_relations_2hop(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    entity_id=entity_id,
                    hop1_types=_RELATIONAL_HOP1_PREDICATES,
                    min_confidence=min_confidence,
                    limit=_MAX_2HOP_PER_ENTITY,
                )
            except Exception:  # noqa: BLE001 — degrade to 1-hop, never nuke L2
                logger.warning(
                    "2-hop traversal failed for entity %s; "
                    "falling back to 1-hop facts only",
                    entity_id,
                    exc_info=True,
                )
                two_hop = []
            for hop in two_hop:
                key = f"{hop.hop1.id}|{hop.hop2.id}"
                if key in seen_relations:
                    continue
                seen_relations.add(key)
                result.background.append(format_relation_hop(hop))

    # Negative facts for the whole project — filtered to those that
    # mention any resolved entity. Negation Facts are cheap to list
    # and small in count (K15.5 extractor output), so a single
    # per-project query plus post-filter is simpler than per-entity
    # Cypher.
    negs = await list_facts_by_type(
        session,
        user_id=user_id,
        project_id=project_id,
        type="negation",
        limit=_MAX_NEGATIVES,
    )
    resolved_names_lower = {n.lower() for n, _ in resolved}
    for fact in negs:
        text = (fact.content or "").strip()
        if not text:
            continue
        if any(name in text.lower() for name in resolved_names_lower):
            result.negative.append(text)

    logger.debug(
        "K18.2: L2 fact selection intent=%s entities=%d resolved=%d "
        "current=%d background=%d negative=%d",
        intent.intent.value,
        len(intent.entities),
        len(resolved),
        len(result.current),
        len(result.background),
        len(result.negative),
    )
    return result


# ── M1a: passage→graph anchor bridge (2026-07-06) ────────────────────
#
# `select_l2_facts` anchors graph expansion ONLY on `intent.entities` — the
# proper nouns the classifier pulled from the MESSAGE. The M4 measurement
# (docs/eval/context-budget/M4-graph-anchor-bridge-2026-07-06.md) showed that on
# natural questions naming no entity ("what happened at the castle?") the
# classifier extracts nothing, so the whole L2 graph-fact layer is dark — even
# though the semantically-retrieved PASSAGES clearly name relation-bearing
# entities (6/6 such queries). This bridge expands 1-hop from the entities the
# passages surfaced that the message did NOT anchor, injecting the new relations
# into the L2 facts block. Caps mirror the A/B config (0 regressions there).
_MAX_BRIDGE_ANCHORS = 6
_MAX_BRIDGE_RELS_PER_ANCHOR = 5
_MAX_BRIDGE_NEW_FACTS = 20
# `extract_candidates` is a user-MESSAGE proper-noun extractor; run over passage
# PROSE it also emits quoted dialogue sentences and sentence-initial common words
# as "candidates". On English that noise is mild, but the multilingual M4 re-measure
# (Vietnamese corpus 019f1783, 2026-07-06) showed it dominating: 5 of 6 anchor slots
# filled with junk (quoted sentences + "Một"/"Sự"/"Không") so only 1/6 resolved to a
# real entity. Two mitigations, bridge-local (never touch the shared extractor):
#   (1) drop obviously-sentence candidates before the cap (see `_looks_like_sentence`),
#   (2) resolve-THEN-cap over a bounded pool (see `expand_facts_from_passages`) so
#       unresolvable junk no longer consumes the anchor budget.
# NOTE (D-BRIDGE-NAME-FRAGMENT, deferred): a 2nd multilingual defect remains — a
# multi-token Sino-Vietnamese name ("Cửu U Ma Cơ") gets split by the extractor at the
# mid-name single-char token ("U") into non-resolving fragments. That fix lives in the
# SHARED extractor/LATIN_NAME_RE and needs a glossary-path regression pass; tracked, not
# fixed here.
_MAX_BRIDGE_CANDIDATE_POOL = 40  # bound the resolve-then-cap I/O on prose-heavy passages
_MAX_BRIDGE_ANCHOR_WORDS = 8     # a "name" longer than this is prose, not an entity

# Sentence/dialogue punctuation that a real entity name never carries mid-string.
# `\.\s` catches an interior "period + space" sentence break; a trailing abbreviation
# dot ("Coutts & Co.") has no following space so it is NOT matched.
_BRIDGE_SENTENCE_PUNCT = re.compile(r"[!?…。！？]|\.\s")


def _looks_like_sentence(candidate: str) -> bool:
    """True when a bridge candidate is prose (a quoted dialogue line), not a name.

    Bridge-local hygiene for the passage→graph anchor path — keeps `Coutts & Co.`
    and `Cửu U Ma Cơ` (short, no interior sentence punctuation) while dropping
    `"Không thể... không thể để nó nuốt chửng mình!"`.
    """
    if _BRIDGE_SENTENCE_PUNCT.search(candidate):
        return True
    return len(candidate.split()) > _MAX_BRIDGE_ANCHOR_WORDS


def select_bridge_anchor_names(
    passage_texts: list[str],
    already_anchored_names: set[str],
    *,
    max_anchors: int = _MAX_BRIDGE_ANCHORS,
) -> list[str]:
    """Proper-noun candidates the PASSAGES surfaced that the message did not
    already anchor.

    Passages are processed in RANK order and first-seen wins under the cap, so
    the selection is DETERMINISTIC — the most query-relevant passage entities
    survive (this fixes the non-deterministic set-ordering cap the M4 harness
    had). Case-insensitive dedup; any name already anchored by the message-driven
    L2 selector is skipped so we never double-expand it. Pure — no I/O — so the
    cap/dedup logic is unit-testable without a Neo4j session.
    """
    already = {n.lower() for n in already_anchored_names}
    seen: set[str] = set()
    out: list[str] = []
    for text in passage_texts:
        for cand in extract_candidates(text):
            low = cand.lower()
            if low in already or low in seen:
                continue
            # Drop quoted-dialogue-sentence noise before it consumes a cap slot
            # (multilingual M4 fix). Cheap + bridge-local; the shared extractor
            # is untouched.
            if _looks_like_sentence(cand):
                continue
            seen.add(low)
            out.append(cand)
            if len(out) >= max_anchors:
                return out
    return out


async def expand_facts_from_passages(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    passage_texts: list[str],
    already_anchored_names: set[str],
    existing_facts: set[str],
    min_confidence: float = 0.8,
    max_anchors: int = _MAX_BRIDGE_ANCHORS,
    max_rels_per_anchor: int = _MAX_BRIDGE_RELS_PER_ANCHOR,
    max_new_facts: int = _MAX_BRIDGE_NEW_FACTS,
) -> list[str]:
    """M1a — 1-hop expand entities the passages surfaced but the message missed.

    Returns NEW fact strings (deduped against `existing_facts` and each other),
    ready to append to `L2FactResult.background`. Reuses the exact resolver
    (`find_entities_by_name`) and 1-hop primitive (`find_relations_for_entity`)
    the message-anchored path uses, with the same confidence + archived-peer
    filters. Bounded by `max_anchors × max_rels_per_anchor` and `max_new_facts`.

    `max_anchors` bounds RESOLVED anchors, not candidates examined: the selector
    yields a bounded POOL (`_MAX_BRIDGE_CANDIDATE_POOL`) and this loop resolves in
    rank order until `max_anchors` candidates hit a real entity. That resolve-then-cap
    ordering is the multilingual M4 fix — on Vietnamese prose the raw candidate stream
    is mostly unresolvable noise, and a plain cap-then-resolve wasted 5 of 6 slots on
    it (only 1/6 anchors real); this way junk is skipped without spending the budget.
    I/O stays bounded: ≤ pool resolution lookups + ≤ max_anchors relation lookups.

    Best-effort at the candidate grain: a name that fails to resolve or expand is
    skipped, never raised — the caller wraps the whole call in a degrade-to-empty
    guard, but per-candidate resilience means one bad anchor can't starve the rest.
    """
    # Pull a bounded POOL (≥ max_anchors) so unresolvable junk doesn't crowd real
    # names out of the cap; the resolve loop below enforces the real max_anchors.
    pool = max(max_anchors, _MAX_BRIDGE_CANDIDATE_POOL)
    anchor_names = select_bridge_anchor_names(
        passage_texts, already_anchored_names, max_anchors=pool
    )
    if not anchor_names:
        return []

    new_facts: list[str] = []
    seen_ids: set[str] = set()
    resolved_anchors = 0
    for name in anchor_names:
        if len(new_facts) >= max_new_facts or resolved_anchors >= max_anchors:
            break
        matches = await find_entities_by_name(
            session, user_id=user_id, project_id=project_id, name=name
        )
        if not matches:
            continue
        # Repo orders anchored > discovered; take the best match. Dedup by id so
        # two surface names for one entity don't double-expand.
        eid = matches[0].id
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        resolved_anchors += 1
        rels = await find_relations_for_entity(
            session,
            user_id=user_id,
            project_id=project_id,
            entity_id=eid,
            min_confidence=min_confidence,
            limit=max_rels_per_anchor,
        )
        for r in rels:
            f = format_relation(r)
            if f in existing_facts or f in new_facts:
                continue
            new_facts.append(f)
            if len(new_facts) >= max_new_facts:
                break

    if new_facts:
        logger.debug(
            "M1a: passage→graph bridge expanded %d anchors → %d new facts",
            len(anchor_names), len(new_facts),
        )
    return new_facts
