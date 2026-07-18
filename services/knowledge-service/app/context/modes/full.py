"""K18.1 — Mode 3 builder scaffold (full extraction-enabled context).

Assembles the Mode 3 memory block used when a chat session is attached
to a project with ``extraction_enabled=true``. Builds on Mode 2 by
adding L2 facts (from the Neo4j graph), absence hints, and
intent-aware CoT instructions.

**Pipeline (all live):**

  - Uses the K18.2a intent classifier to route.
  - Runs the K18.2 L2 fact selector (1-hop always, 2-hop on
    relational intent, + negations).
  - Runs the K18.3 L3 semantic passage selector + P3 D5 abstract-query
    summary blend.
  - Runs K18.5 absence detection.
  - Emits K18.6 intent-aware instructions.
  - K18.7 token-budget enforcement trims in reverse priority.
  - Falls back gracefully to a Mode-2-shaped block if Neo4j is
    unavailable or the L2 query fails.

Mode 3 is **flipped on (K18.8)** and reached in production: ``builder.py``
dispatches here on ``project.extraction_enabled`` (no ``NotImplementedError``
remains). ``embedding_client=None`` callers (Track 1 / no-Neo4j) cleanly get an
empty ``<passages>`` block.

Recent-message count is 20 (down from Mode 2's 50) — the graph
itself carries the durable memory, so chat history can be tighter.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from uuid import UUID

from app.context.anchors import (
    get_anchor_index,
    get_project_protagonist,
    has_non_ascii_letter,
    has_protagonist_role,
    looks_like_question,
    resolve_anchors,
)
from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.clients.llm_client import LLMClient
from app.clients.reranker_client import get_reranker_client
from app.config import settings
from loreweave_context import scale_by_window
from app.context.formatters.dedup import (
    filter_entities_not_in_summary,
    filter_facts_not_in_summary,
)
from app.context.formatters.instructions import build_instructions_block
from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.intent.classifier import Intent, IntentResult, classify
from app.context.modes.no_project import BuiltContext, split_at_boundary
from app.context.selectors.absence import detect_absences
from app.context.selectors.facts import (
    L2FactResult,
    expand_facts_from_passages,
    select_l2_facts,
)
from app.context.query_embedding import embed_query_cached
from app.context.selectors.glossary import select_glossary_for_context
from app.context.selectors.salience import apply_salience
from app.context.intent.abstract_query import is_abstract_query
from app.context.selectors.passages import L3Passage  # select_l3_passages is lazy-imported in _safe_l3_passages for test-patchability
from app.context.selectors.summary_blend import LevelSummaryHit  # select_summary_blend is lazy-imported in _safe_summary_blend
from app.context.selectors.projects import load_project_summary
from app.context.selectors.summaries import load_global_summary
from app.db.models import Project
from app.db.neo4j import neo4j_session
from app.db.repositories.summaries import SummariesRepo
from app.metrics import (
    layer_timeout_total,
    mode3_grounding_zero_anchor_total,
    mode3_intent_classifier_glossary_unavailable_total,
)

logger = logging.getLogger(__name__)

__all__ = ["build_full_mode"]


# Mode 3 uses a tighter chat-history window; the graph provides the
# durable memory so we don't need to re-play as much.
_RECENT_MESSAGE_COUNT = 20


async def _safe_l2_facts(
    *,
    user_id: UUID,
    project: Project,
    intent: IntentResult,
) -> L2FactResult:
    """Run the L2 selector under a Neo4j session with a timeout.

    On any failure returns an empty result — Mode 3 degrades to
    roughly Mode 2 shape plus absence-of-graph instructions.
    """
    try:
        async with neo4j_session() as session:
            return await asyncio.wait_for(
                select_l2_facts(
                    session,
                    user_id=str(user_id),
                    project_id=str(project.project_id),
                    intent=intent,
                    # WS-4C — admit project-level memory_remember facts to L2.
                    tool_facts=settings.context_l2_tool_facts,
                    tool_fact_min_confidence=settings.context_l2_tool_fact_min_confidence,
                    tool_facts_limit=settings.context_l2_tool_facts_limit,
                ),
                timeout=settings.context_l2_timeout_s,
            )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l2").inc()
        logger.warning(
            "Mode 3 L2 timeout user_id=%s project_id=%s budget=%.3fs",
            user_id, project.project_id, settings.context_l2_timeout_s,
        )
        return L2FactResult()
    except Exception:
        logger.warning(
            "Mode 3 L2 failed user_id=%s project_id=%s — degrading",
            user_id, project.project_id, exc_info=True,
        )
        return L2FactResult()


async def _safe_expand_from_passages(
    *,
    user_id: UUID,
    project: Project,
    passage_texts: list[str],
    already_anchored_names: set[str],
    existing_facts: set[str],
) -> list[str]:
    """M1a bridge wrapper — 1-hop expand entities the passages surfaced but the
    message didn't anchor. Degrades to ``[]`` on any failure/timeout (mirrors
    ``_safe_l2_facts``): the bridge is strictly-additive recall, so a failure
    must never break the L2 facts the message-anchored path already produced.
    """
    if not passage_texts:
        return []
    try:
        async with neo4j_session() as session:
            return await asyncio.wait_for(
                expand_facts_from_passages(
                    session,
                    user_id=str(user_id),
                    project_id=str(project.project_id),
                    passage_texts=passage_texts,
                    already_anchored_names=already_anchored_names,
                    existing_facts=existing_facts,
                ),
                timeout=settings.context_l2_timeout_s,
            )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l2_bridge").inc()
        logger.warning(
            "Mode 3 M1a passage→graph bridge timeout user_id=%s project_id=%s",
            user_id, project.project_id,
        )
        return []
    except Exception:
        logger.warning(
            "Mode 3 M1a passage→graph bridge failed user_id=%s project_id=%s — degrading",
            user_id, project.project_id, exc_info=True,
        )
        return []


async def _safe_l3_passages(
    embedding_client: EmbeddingClient | None,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    intent: IntentResult,
    current_chapter_id: UUID | None = None,
    llm_client: LLMClient | None = None,
    rerank_model: str | None = None,
    reranker_client=None,
    cross_encoder_model: str | None = None,
) -> list[L3Passage]:
    """Run the L3 selector under a Neo4j session with a timeout.

    Returns `[]` when embedding is not configured, the embedding
    call fails, the vector search returns nothing, or any exception
    propagates. The selector itself handles most of these; this
    wrapper adds the timeout ceiling and the session plumbing.

    M1b: when the editor forwarded the open `current_chapter_id`, resolve
    it to a chapter_index inside the same session and pass it (plus the
    boost knobs) to the selector so passages near the working chapter are
    up-ranked. A missing/foreign chapter resolves to None → boost inert.
    """
    # Lazy import is deliberate — test helpers patch
    # `app.context.selectors.passages.select_l3_passages` directly, and
    # a top-level import here would bind the original reference at
    # module load time, making the monkeypatch a no-op.
    from app.context.selectors.passages import select_l3_passages
    from app.db.neo4j_repos.passages import get_chapter_index_for_source

    if embedding_client is None or not project.embedding_model:
        return []

    # D-EMB-MODEL-REF-01 — the dimension is the caller-supplied
    # `embedding_dimension` column; `project.embedding_model` now carries
    # the provider-registry `user_model` UUID (the embed `model_ref`).
    embedding_dim = project.embedding_dimension
    if not embedding_dim:
        logger.debug(
            "Mode 3 L3 skipped: project %s has no embedding_dimension",
            project.project_id,
        )
        return []

    # M1b — the working-scope boost is only worth its config when the editor
    # is open on a chapter AND the boost is enabled. `working_boost=0.0`
    # (kill-switch) skips the resolution query entirely (byte-identical).
    working_boost = settings.context_working_scope_boost
    working_window = settings.context_working_scope_window

    try:
        async with neo4j_session() as session:
            working_chapter_index: int | None = None
            if working_boost > 0.0 and current_chapter_id is not None:
                working_chapter_index = await get_chapter_index_for_source(
                    session,
                    user_id=str(user_id),
                    project_id=str(project.project_id),
                    chapter_id=str(current_chapter_id),
                )
            return await asyncio.wait_for(
                select_l3_passages(
                    session,
                    embedding_client,
                    user_id=str(user_id),
                    project_id=str(project.project_id),
                    message=message,
                    intent=intent,
                    embedding_model=project.embedding_model,
                    embedding_dim=embedding_dim,
                    user_uuid=user_id,
                    current_chapter_index=working_chapter_index,
                    working_scope_boost=working_boost,
                    working_scope_window=working_window,
                    llm_client=llm_client,
                    rerank_model=rerank_model,
                    reranker_client=reranker_client,
                    cross_encoder_model=cross_encoder_model,
                ),
                timeout=settings.context_l3_timeout_s,
            )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l3").inc()
        logger.warning(
            "Mode 3 L3 timeout user_id=%s project_id=%s budget=%.3fs",
            user_id, project.project_id, settings.context_l3_timeout_s,
        )
        return []
    except Exception:
        logger.warning(
            "Mode 3 L3 failed user_id=%s project_id=%s — degrading",
            user_id, project.project_id, exc_info=True,
        )
        return []


async def _safe_summary_blend(
    embedding_client: EmbeddingClient | None,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    glossary_entities: list[str],
) -> list[LevelSummaryHit]:
    """P3 D5 — abstract-query summary blend.

    Cheap-first gate: `is_abstract_query` returns False for the vast
    majority of Mode-3 queries (specific entity lookups), in which case
    we skip the embed call entirely and return []. Only abstract
    queries pay the embedding + 3-way Neo4j vector cost.

    Degrades silently to [] when:
      - embedding_client unset or project has no embedding_model
      - is_abstract_query returns False
      - the embed call fails
      - the Neo4j blend call times out or errors
      - no per-level indexes exist yet (legacy graph, no summaries)
    """
    # Lazy import mirrors `_safe_l3_passages` — test helpers monkeypatch
    # `app.context.selectors.summary_blend.select_summary_blend`.
    from app.context.selectors.summary_blend import select_summary_blend

    if not is_abstract_query(message, glossary_entities=glossary_entities):
        return []

    if embedding_client is None or not project.embedding_model:
        return []

    # mui #4 MED-2 — shared query-embedding cache: the same message embedded
    # for L3 / glossary-semantic in this build is reused here (and vice versa).
    try:
        query_embedding = await embed_query_cached(
            embedding_client,
            user_id=user_id,
            project_id=str(project.project_id),
            embedding_model=project.embedding_model,
            message=message,
        )
    except Exception:
        logger.warning(
            "Mode 3 summary_blend embed failed user_id=%s project_id=%s — degrading",
            user_id, project.project_id, exc_info=True,
        )
        return []

    if query_embedding is None:
        return []

    try:
        async with neo4j_session() as session:
            return await asyncio.wait_for(
                select_summary_blend(
                    session,
                    project_id=str(project.project_id),
                    embedding_model_uuid=project.embedding_model,
                    query_embedding=query_embedding,
                ),
                timeout=settings.context_l3_timeout_s,
            )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="summary_blend").inc()
        logger.warning(
            "Mode 3 summary_blend timeout user_id=%s project_id=%s budget=%.3fs",
            user_id, project.project_id, settings.context_l3_timeout_s,
        )
        return []
    except Exception:
        logger.warning(
            "Mode 3 summary_blend failed user_id=%s project_id=%s — degrading",
            user_id, project.project_id, exc_info=True,
        )
        return []


def _render_facts_block(facts: L2FactResult) -> list[str]:
    """Render the `<facts>` block; empty if nothing to show."""
    if facts.total() == 0:
        return []
    lines = ["  <facts>"]
    for bucket_name, items in (
        ("current", facts.current),
        ("recent", facts.recent),
        ("background", facts.background),
    ):
        if not items:
            continue
        lines.append(f"    <{bucket_name}>")
        for f in items:
            lines.append(f"      <fact>{sanitize_for_xml(f)}</fact>")
        lines.append(f"    </{bucket_name}>")
    if facts.negative:
        lines.append("    <negative>")
        for f in facts.negative:
            lines.append(f"      <fact>{sanitize_for_xml(f)}</fact>")
        lines.append("    </negative>")
    lines.append("  </facts>")
    return lines


def _render_mode3(
    *,
    project: Project,
    l0,
    l1_summary,
    entities: list,
    l2_facts: L2FactResult,
    l3_passages: list[L3Passage],
    summary_hits: list[LevelSummaryHit],
    absences: list[str],
    intent_obj: IntentResult,
    entity_refs: list | None = None,
) -> tuple[str, str, str, dict[str, int]]:
    """Pure render of Mode 3 pieces → (stable, volatile, context, sections).

    Extracted so the budget enforcer can call us repeatedly with
    progressively trimmed pieces until the output fits. K18.9 returns
    the three strings so the final BuiltContext carries the cacheable
    prefix split — L0 and project instructions/summary don't change
    under budget trimming (they're protected), so the stable segment
    survives each re-render unchanged.

    W1: ``sections`` is the per-section token split of ``context``
    (estimate_tokens over each rendered block; a section absent from the
    render is absent from the map) — surfaced through BuiltContext so the
    chat context meter can show WHAT the memory block spends tokens on.
    """
    lines: list[str] = ['<memory mode="full">']
    sections: dict[str, int] = {}

    def _close_section(name: str, start: int) -> None:
        if len(lines) > start:
            sections[name] = estimate_tokens("\n".join(lines[start:]))

    _mark = len(lines)
    if l0 is not None and l0.content.strip():
        lines.append(f"  <user>{sanitize_for_xml(l0.content)}</user>")
        _close_section("user", _mark)

    _mark = len(lines)
    proj_attrs = f'name="{sanitize_for_xml(project.name)}"'
    lines.append(f"  <project {proj_attrs}>")
    if project.instructions and project.instructions.strip():
        lines.append(
            f"    <instructions>{sanitize_for_xml(project.instructions)}</instructions>"
        )
    if l1_summary is not None and l1_summary.content.strip():
        lines.append(
            f"    <summary>{sanitize_for_xml(l1_summary.content)}</summary>"
        )
    lines.append("  </project>")
    _close_section("project", _mark)
    # K18.9: snapshot stable boundary right after </project>. Glossary
    # onwards is message/intent-dependent and must not be cached.
    stable_line_count = len(lines)

    _mark = len(lines)
    if entities:
        lines.append("  <glossary>")
        for e in entities:
            attrs = (
                f'kind="{sanitize_for_xml(e.kind_code)}" '
                f'tier="{sanitize_for_xml(e.tier)}" '
                f'score="{e.rank_score:.2f}"'
            )
            lines.append(f"    <entity {attrs}>")
            if e.cached_name:
                lines.append(f"      <name>{sanitize_for_xml(e.cached_name)}</name>")
            if e.cached_aliases:
                joined = ", ".join(a for a in e.cached_aliases if a)
                if joined:
                    lines.append(
                        f"      <aliases>{sanitize_for_xml(joined)}</aliases>"
                    )
            if e.short_description:
                lines.append(
                    f"      <description>"
                    f"{sanitize_for_xml(e.short_description)}</description>"
                )
            lines.append("    </entity>")
        lines.append("  </glossary>")
        _close_section("glossary_entities", _mark)

    # Track 4 P4 (R-T4-05) — pointer tier: entities the budget enforcer demoted
    # out of the full glossary block. One compact line each keeps BREADTH (the
    # model knows they exist and can expand any of them via the existing
    # memory_recall_entity tool) at a fraction of the full-EAV token cost.
    _mark = len(lines)
    if entity_refs:
        lines.append(
            '  <entity_refs hint="more known entities; expand any with the '
            'memory_recall_entity tool">'
        )
        for e in entity_refs:
            name = sanitize_for_xml(e.cached_name or "")
            kind = sanitize_for_xml(e.kind_code)
            lines.append(f'    <ref name="{name}" kind="{kind}"/>')
        lines.append("  </entity_refs>")
        _close_section("entity_refs", _mark)

    _mark = len(lines)
    lines.extend(_render_facts_block(l2_facts))
    _close_section("facts", _mark)

    _mark = len(lines)
    if l3_passages:
        lines.append("  <passages>")
        for p in l3_passages:
            attrs = (
                f'source_type="{sanitize_for_xml(p.source_type)}" '
                f'source_id="{sanitize_for_xml(p.source_id)}" '
                f'score="{p.score:.2f}"'
            )
            lines.append(f"    <passage {attrs}>")
            lines.append(f"      {sanitize_for_xml(p.text)}")
            lines.append("    </passage>")
        lines.append("  </passages>")
        _close_section("passages", _mark)

    _mark = len(lines)
    if summary_hits:
        lines.append("  <summaries>")
        for h in summary_hits:
            attrs = (
                f'level="{sanitize_for_xml(h.level)}" '
                f'path="{sanitize_for_xml(h.node_path)}" '
                f'score="{h.weighted_score:.2f}"'
            )
            lines.append(f"    <summary {attrs}>")
            lines.append(f"      {sanitize_for_xml(h.summary_text)}")
            lines.append("    </summary>")
        lines.append("  </summaries>")
        _close_section("summaries", _mark)

    _mark = len(lines)
    if absences:
        lines.append("  <no_memory_for>")
        for name in absences:
            lines.append(f"    <entity>{sanitize_for_xml(name)}</entity>")
        lines.append("  </no_memory_for>")
        _close_section("absences", _mark)

    instructions = build_instructions_block(
        intent_obj.intent,
        has_facts=l2_facts.total() > 0,
        has_passages=bool(l3_passages),
        has_summaries=bool(summary_hits),
        has_absences=bool(absences),
    )
    _mark = len(lines)
    lines.append(f"  <instructions>{sanitize_for_xml(instructions)}</instructions>")
    _close_section("instructions", _mark)
    lines.append("</memory>")

    stable, volatile, context = split_at_boundary(lines, stable_line_count)
    return stable, volatile, context, sections


def _enforce_budget(
    *,
    project: Project,
    l0,
    l1_summary,
    entities: list,
    l2_facts: L2FactResult,
    l3_passages: list[L3Passage],
    summary_hits: list[LevelSummaryHit],
    absences: list[str],
    intent_obj: IntentResult,
    budget_tokens: int,
) -> tuple[str, str, str, int, dict[str, int]]:
    """K18.7 — trim in reverse priority until under budget.

    Returns `(stable_context, volatile_context, context, token_count,
    sections)` — ``sections`` (W1) is the per-section token split of the
    FINAL (post-trim) render. The passed-in lists are copied defensively;
    the caller's objects are not mutated.

    Drop order (KSA §4.4.4 + P3 D5, lowest priority first):
      1. `<passages>` — drop lowest-score entries
      2. `<summaries>` — drop lowest weighted-score entries (chapter
         goes first by weight, book sticks longest)
      3. `<no_memory_for>` — drop all
      4. background facts — drop all (keep current/recent/negative)
      5. glossary — drop lowest-scored entries
    Never dropped: L0, project instructions, L1 summary, current /
    recent / negative facts, mode-level instructions.

    K18.9: trimming only touches fields AFTER the </project> boundary
    (glossary, facts, passages, summaries, absences, instructions), so
    the stable prefix is identical across every retry — the split is
    consistent end-to-end regardless of how many budget passes it takes.
    """
    # Defensive copies so retries don't mutate caller state.
    passages = list(l3_passages)
    summaries = list(summary_hits)
    abs_list = list(absences)
    ent_list = list(entities)
    ent_refs: list = []  # P4 — entities demoted to one-line pointers
    facts = L2FactResult(
        current=list(l2_facts.current),
        recent=list(l2_facts.recent),
        background=list(l2_facts.background),
        negative=list(l2_facts.negative),
    )

    def render_and_count() -> tuple[str, str, str, int, dict[str, int]]:
        stable, volatile, context, sections = _render_mode3(
            project=project, l0=l0, l1_summary=l1_summary,
            entities=ent_list, l2_facts=facts,
            l3_passages=passages, summary_hits=summaries,
            absences=abs_list, intent_obj=intent_obj,
            entity_refs=ent_refs,
        )
        return stable, volatile, context, estimate_tokens(context), sections

    stable, volatile, rendered, tokens, sections = render_and_count()
    if tokens <= budget_tokens:
        return stable, volatile, rendered, tokens, sections

    # Pass 1: drop lowest-score passages progressively.
    if passages:
        # Sort by score descending so we drop from the tail (lowest score).
        passages.sort(key=lambda p: p.score, reverse=True)
        while passages and tokens > budget_tokens:
            passages.pop()
            stable, volatile, rendered, tokens, sections = render_and_count()
        if tokens <= budget_tokens:
            logger.info(
                "K18.7: budget enforced by trimming passages (final=%d, tokens=%d/%d)",
                len(passages), tokens, budget_tokens,
            )
            return stable, volatile, rendered, tokens, sections

    # Pass 2: drop lowest weighted-score summaries progressively.
    # Selector already returns them in descending weighted_score order,
    # so pop from the tail. Book-level (highest weight) survives longest.
    if summaries:
        summaries.sort(key=lambda h: h.weighted_score, reverse=True)
        while summaries and tokens > budget_tokens:
            summaries.pop()
            stable, volatile, rendered, tokens, sections = render_and_count()
        if tokens <= budget_tokens:
            logger.info(
                "K18.7: budget enforced by trimming summaries "
                "(final=%d, tokens=%d/%d)",
                len(summaries), tokens, budget_tokens,
            )
            return stable, volatile, rendered, tokens, sections

    # Pass 2: drop absences entirely.
    if abs_list:
        abs_list.clear()
        stable, volatile, rendered, tokens, sections = render_and_count()
        if tokens <= budget_tokens:
            logger.info(
                "K18.7: budget enforced by dropping absences (tokens=%d/%d)",
                tokens, budget_tokens,
            )
            return stable, volatile, rendered, tokens, sections

    # Pass 3: drop background facts (keep current/recent/negative).
    if facts.background:
        facts.background.clear()
        stable, volatile, rendered, tokens, sections = render_and_count()
        if tokens <= budget_tokens:
            logger.info(
                "K18.7: budget enforced by dropping background facts "
                "(tokens=%d/%d)",
                tokens, budget_tokens,
            )
            return stable, volatile, rendered, tokens, sections

    # Pass 4 (P4 / R-T4-05): DEMOTE glossary tail entities to one-line pointers
    # instead of dropping them — breadth survives (the model can expand any ref
    # via memory_recall_entity) at a fraction of the token cost. Entities arrive
    # in rank order; demote from the end.
    if ent_list:
        while ent_list and tokens > budget_tokens:
            ent_refs.insert(0, ent_list.pop())  # keep rank order within refs
            stable, volatile, rendered, tokens, sections = render_and_count()
        if tokens <= budget_tokens:
            logger.info(
                "K18.7: budget enforced by demoting glossary to refs "
                "(full=%d, refs=%d, tokens=%d/%d)",
                len(ent_list), len(ent_refs), tokens, budget_tokens,
            )
            return stable, volatile, rendered, tokens, sections

    # Pass 5: still over — drop the pointer refs themselves from the tail.
    if ent_refs:
        while ent_refs and tokens > budget_tokens:
            ent_refs.pop()
            stable, volatile, rendered, tokens, sections = render_and_count()
        if tokens <= budget_tokens:
            logger.info(
                "K18.7: budget enforced by dropping entity refs "
                "(final refs=%d, tokens=%d/%d)",
                len(ent_refs), tokens, budget_tokens,
            )
            return stable, volatile, rendered, tokens, sections

    # Couldn't fit even with everything trimmed — render what's left
    # (L0/L1/instructions are protected) and log the overshoot.
    logger.warning(
        "K18.7: block exceeds budget even after all drops "
        "(tokens=%d > budget=%d) — L0/L1/instructions only may still be too large",
        tokens, budget_tokens,
    )
    return stable, volatile, rendered, tokens, sections


async def build_full_mode(
    summaries_repo: SummariesRepo,
    glossary_client: GlossaryClient,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
    language: str | None = None,
    entity_access_repo=None,
    current_chapter_id: UUID | None = None,
    context_length: int | None = None,
) -> BuiltContext:
    """Build the Mode 3 memory block.

    Mirrors Mode 2's layer-timeout pattern for L0/L1/glossary, then
    adds the L2 fact selector, L3 semantic passages, and absence
    detection on top. Intent-aware CoT instructions close the block.
    Token budget enforcement (K18.7) trims in reverse priority when
    the full payload exceeds `settings.mode3_token_budget` (scaled up via
    `context_length` — the calling chat session's real model window — instead
    of every model being capped at the same flat number).

    `embedding_client` is optional — callers in Track 1 / no-Neo4j
    mode pass `None` and the L3 layer cleanly returns empty.
    """
    # ── L0 / L1 / glossary (reuse Mode-2 shape) ─────────────────────────
    try:
        l0 = await asyncio.wait_for(
            load_global_summary(summaries_repo, user_id),
            timeout=settings.context_l0_timeout_s,
        )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l0").inc()
        l0 = None

    try:
        l1_summary = await asyncio.wait_for(
            load_project_summary(summaries_repo, user_id, project.project_id),
            timeout=settings.context_l1_timeout_s,
        )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l1").inc()
        l1_summary = None

    try:
        entities = await asyncio.wait_for(
            select_glossary_for_context(
                glossary_client,
                user_id=user_id,
                project=project,
                message=message,
                embedding_client=embedding_client,  # mui #4 — semantic-first
                language=language,
            ),
            timeout=settings.context_glossary_timeout_s,
        )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="glossary").inc()
        # D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC. Downstream Mode-3 intent
        # classifier runs WITHOUT glossary input → falls back to the
        # less-precise long-query heuristic, which over-classifies as
        # "abstract" and triggers unnecessary summary_blend cost.
        mode3_intent_classifier_glossary_unavailable_total.inc()
        entities = []

    if l1_summary is not None and entities:
        entities = filter_entities_not_in_summary(
            entities,
            l1_summary.content,
            min_overlap=settings.dedup_min_overlap,
        )

    # Track 4 P1+P3a — re-rank by learned salience (P1 access frequency) and/or
    # graph-native promotion (P3a evidence/mention/edit-recency). Weight-guarded:
    # defaults 0.0 → no DB read, no Neo4j fetch, no re-order (byte-identical).
    # The Neo4j session is only opened when the promotion flag is on.
    if settings.salience_promote_weight > 0:
        async with neo4j_session() as _sal_session:
            entities = await apply_salience(
                entity_access_repo, entities, user_id, project.project_id,
                neo4j_session=_sal_session,
            )
    else:
        entities = await apply_salience(entity_access_repo, entities, user_id, project.project_id)

    # ── L2 facts + L3 passages + summary blend (Neo4j, parallel) ────────
    # Classify once: the same IntentResult drives both the L2 selector's
    # hop-count / recency gating AND the instruction-block hint text.
    intent_obj = classify(message)
    # M-recall — the classifier can't segment scriptio-continua (Chinese has no
    # spaces), so on a non-Latin message it emits whole clauses as "entities" and
    # select_l2_facts resolves nothing. Anchor instead on the project's KNOWN
    # entity dictionary (Aho-Corasick), UNIONed into intent.entities so the L2
    # facts + widened-retry + M1a bridge all see the real anchors. Degrade-safe:
    # no automaton / no match → intent_obj unchanged (classifier-only).
    if settings.context_dict_anchor_enabled and has_non_ascii_letter(message):
        # Bound the (cache-miss) dictionary load so a slow Neo4j can't delay the
        # whole build — degrade to classifier-only anchors on timeout/failure.
        try:
            _automaton = await asyncio.wait_for(
                get_anchor_index(
                    str(user_id), str(project.project_id),
                    ttl_s=settings.context_dict_anchor_ttl_s,
                    min_len=settings.context_dict_anchor_min_len,
                ),
                timeout=settings.context_l2_timeout_s,
            )
        except Exception:  # timeout or load error → classifier-only (degrade-safe)
            _automaton = None
        _dict_anchors = resolve_anchors(
            _automaton, message,
            max_anchors=settings.context_dict_anchor_cap,
            min_len=settings.context_dict_anchor_min_len,
        )
        if _dict_anchors:
            _merged = tuple(dict.fromkeys((*intent_obj.entities, *_dict_anchors)))
            if _merged != intent_obj.entities:
                intent_obj = replace(intent_obj, entities=_merged)
                logger.info(
                    "M-recall: +%d dict anchors (project=%s) — L2 anchors now %d",
                    len(_dict_anchors), project.project_id, len(_merged),
                )
    # M-recall role-resolution — when the message names the lead by ROLE ("主角"/
    # "the protagonist") rather than by name, the dictionary can't match it (the role
    # term isn't an entity name). Anchor the project's most-central entity so
    # select_l2_facts can resolve the role. Additive + gated on a strict protagonist-
    # term set (both languages, so not non-Latin-only); timeout-bounded, degrade-safe.
    if settings.context_role_anchor_enabled and has_protagonist_role(message):
        try:
            _protagonist = await asyncio.wait_for(
                get_project_protagonist(
                    str(user_id), str(project.project_id),
                    ttl_s=settings.context_dict_anchor_ttl_s,
                ),
                timeout=settings.context_l2_timeout_s,
            )
        except Exception:  # timeout or load error → no role-anchoring (degrade-safe)
            _protagonist = None
        if _protagonist and _protagonist not in intent_obj.entities:
            intent_obj = replace(
                intent_obj, entities=(*intent_obj.entities, _protagonist)
            )
            logger.info(
                "M-recall: role→protagonist anchor '%s' (project=%s)",
                _protagonist, project.project_id,
            )
    # D-K18.3-02: opt-in generative rerank via extraction_config. Absent
    # key or empty string = skip the LLM rerank hop, MMR order stands.
    rerank_model = (project.extraction_config or {}).get("rerank_model") or None
    # Track 4 P2: opt-in cross-encoder rerank via extraction_config. Absent/empty →
    # skip (no reranker client resolved), MMR order stands. Preferred over the
    # generative rerank when set. Provider-registry BYOK model_ref (no hardcode).
    cross_encoder_model = (project.extraction_config or {}).get("cross_encoder_rerank_model") or None
    reranker_client = get_reranker_client() if cross_encoder_model else None
    # P3 D5: glossary-entity names feed `is_abstract_query` inside the
    # summary_blend wrapper so a long query mentioning a known proper
    # noun stays specific (no abstract-blend trigger).
    glossary_entity_names = [
        e.cached_name for e in entities if getattr(e, "cached_name", None)
    ]
    l2_facts, l3_passages, summary_hits = await asyncio.gather(
        _safe_l2_facts(
            user_id=user_id, project=project, intent=intent_obj,
        ),
        _safe_l3_passages(
            embedding_client,
            user_id=user_id, project=project,
            message=message, intent=intent_obj,
            current_chapter_id=current_chapter_id,
            llm_client=llm_client,
            rerank_model=rerank_model,
            reranker_client=reranker_client,
            cross_encoder_model=cross_encoder_model,
        ),
        _safe_summary_blend(
            embedding_client,
            user_id=user_id, project=project,
            message=message,
            glossary_entities=glossary_entity_names,
        ),
    )
    mentioned_entities = list(intent_obj.entities)

    # Track 4 P4 (R-T4-06) — widened retry on a fact MISS. When the intent names
    # entities but the L2 selector came back EMPTY (e.g. a SPECIFIC_ENTITY query
    # whose 1-hop found nothing), retry ONCE with a relational 2-hop walk over the
    # same entities before concluding "no memory". Strictly additive recall on the
    # empty path only (never re-ranks a non-empty result); one bounded extra Neo4j
    # query; kill-switch via settings.context_l2_retry_widened.
    # WS-4C — key the miss-detection on the ENTITY-ANCHORED buckets, not total():
    # tool facts (in `current`) are project-level and would otherwise mask an empty
    # relation walk and suppress the widened retry that exists to recover relations.
    if (
        settings.context_l2_retry_widened
        and not l2_facts.background
        and not l2_facts.negative
        and intent_obj.entities
        and intent_obj.hop_count < 2
    ):
        widened = IntentResult(
            intent=Intent.RELATIONAL,
            entities=intent_obj.entities,
            signals=intent_obj.signals + ("l2_retry_widened",),
            hop_count=2,
            recency_weight=0.0,
        )
        l2_retry = await _safe_l2_facts(
            user_id=user_id, project=project, intent=widened,
        )
        if l2_retry.total():
            logger.info(
                "P4/R-T4-06: widened L2 retry recovered %d facts (project=%s)",
                l2_retry.total(), project.project_id,
            )
            l2_facts = l2_retry

    # M-recall — zero-anchor frequency meter. Measured HERE (after classifier + CJK
    # dict-anchor + protagonist role-resolution + widened retry, BEFORE the passage
    # bridge) so it reflects the ANCHOR path: a non-empty turn that grounded no L2
    # facts couldn't resolve any entity it referenced. `question="true"` is the
    # deferred generic-noun-coref frequency signal — production tells us how common
    # "那位重生的少年…"-style references really are before we invest in coref.
    if not l2_facts.total() and message.strip():
        mode3_grounding_zero_anchor_total.labels(
            question="true" if looks_like_question(message) else "false"
        ).inc()

    # M1a — passage→graph anchor bridge. The message-anchored L2 selector above
    # only expands `intent.entities`; on natural queries that name no entity it
    # yields nothing (M4: 6/6 such queries). Expand 1-hop from the entities the
    # retrieved PASSAGES surfaced that the message didn't anchor, and append the
    # new relations to the fact block. Strictly-additive recall, degrade-safe,
    # capped; deploy kill-switch `context_passage_graph_expansion_enabled`.
    if settings.context_passage_graph_expansion_enabled and l3_passages:
        _existing_facts = set(
            l2_facts.current + l2_facts.recent
            + l2_facts.background + l2_facts.negative
        )
        _bridge_facts = await _safe_expand_from_passages(
            user_id=user_id,
            project=project,
            passage_texts=[p.text for p in l3_passages],
            already_anchored_names={e.lower() for e in intent_obj.entities},
            existing_facts=_existing_facts,
        )
        if _bridge_facts:
            l2_facts.background.extend(_bridge_facts)
            logger.info(
                "M1a: passage→graph bridge added %d facts (project=%s)",
                len(_bridge_facts), project.project_id,
            )

    # K18.4: drop L2 rows already expressed by the L1 summary so the
    # graph doesn't duplicate authored prose.
    if l1_summary is not None and l2_facts.total():
        l2_facts = L2FactResult(
            current=filter_facts_not_in_summary(l2_facts.current, l1_summary.content),
            recent=filter_facts_not_in_summary(l2_facts.recent, l1_summary.content),
            background=filter_facts_not_in_summary(l2_facts.background, l1_summary.content),
            negative=filter_facts_not_in_summary(l2_facts.negative, l1_summary.content),
        )

    # ── absence detection ───────────────────────────────────────────────
    # L3 passages now feed into absence: an entity mentioned in a passage
    # counts as "covered" even if no L2 fact exists for it.
    l3_texts = [p.text for p in l3_passages]
    absences = detect_absences(mentioned_entities, l2_facts, l3_hits=l3_texts)

    # ── render + K18.7 budget enforcement ───────────────────────────────
    stable_context, volatile_context, context, token_count, sections = _enforce_budget(
        project=project,
        l0=l0,
        l1_summary=l1_summary,
        entities=list(entities),
        l2_facts=l2_facts,
        l3_passages=l3_passages,
        summary_hits=summary_hits,
        absences=absences,
        intent_obj=intent_obj,
        budget_tokens=scale_by_window(settings.mode3_token_budget, context_length),
    )

    return BuiltContext(
        mode="full",
        context=context,
        recent_message_count=_RECENT_MESSAGE_COUNT,
        token_count=token_count,
        stable_context=stable_context,
        volatile_context=volatile_context,
        # K21.12-BE (design D9): surface the project's tool-calling toggle.
        tool_calling_enabled=project.tool_calling_enabled,
        # WS-4C Half A: surface the project's canon auto-capture toggle. Chat ANDs
        # it with its own deploy ceiling before spending a model call.
        canon_capture_enabled=project.canon_capture_enabled,
        # Track 4 P0 — the entities the selector judged relevant to this query
        # (pre-budget-trim: budget trimming is a space artifact, not a relevance
        # signal). The router records these to entity_access_log fire-and-forget.
        surfaced_entity_ids=[
            e.entity_id for e in entities if getattr(e, "entity_id", None)
        ],
        # W1 — per-section token split of the FINAL (post-trim) rendered block.
        sections=sections,
    )
