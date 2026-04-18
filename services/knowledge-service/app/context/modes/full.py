"""K18.1 — Mode 3 builder scaffold (full extraction-enabled context).

Assembles the Mode 3 memory block used when a chat session is attached
to a project with ``extraction_enabled=true``. Builds on Mode 2 by
adding L2 facts (from the Neo4j graph), absence hints, and
intent-aware CoT instructions.

**Commit 1 scaffold scope:**

  - Uses the K18.2a intent classifier to route.
  - Runs the K18.2 L2 fact selector (1-hop always, 2-hop on
    relational intent, + negations).
  - Runs K18.5 absence detection (no L3 yet).
  - Emits K18.6 intent-aware instructions.
  - Falls back gracefully to a Mode-2-shaped block if Neo4j is
    unavailable or the L2 query fails.

**Out of scope for Commit 1 (handled by later commits):**

  - L3 semantic passage selector (K18.3 → Commit 2).
  - Final token budget enforcement (K18.7 → Commit 3).
  - Dispatcher flip (K18.8 → Commit 3). The dispatcher in
    ``builder.py`` still raises ``NotImplementedError``; this
    scaffold is callable directly from tests and from Commit 3's
    router change.

Recent-message count is 20 (down from Mode 2's 50) — the graph
itself carries the durable memory, so chat history can be tighter.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.config import settings
from app.context.formatters.dedup import (
    filter_entities_not_in_summary,
    filter_facts_not_in_summary,
)
from app.context.formatters.instructions import build_instructions_block
from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.intent.classifier import IntentResult, classify
from app.context.modes.no_project import BuiltContext
from app.context.selectors.absence import detect_absences
from app.context.selectors.facts import L2FactResult, select_l2_facts
from app.context.selectors.glossary import select_glossary_for_context
from app.context.selectors.passages import L3Passage, select_l3_passages
from app.context.selectors.projects import load_project_summary
from app.context.selectors.summaries import load_global_summary
from app.db.models import Project
from app.db.neo4j import neo4j_session
from app.db.repositories.summaries import SummariesRepo
from app.metrics import layer_timeout_total

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


async def _safe_l3_passages(
    embedding_client: EmbeddingClient | None,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    intent: IntentResult,
) -> list[L3Passage]:
    """Run the L3 selector under a Neo4j session with a timeout.

    Returns `[]` when embedding is not configured, the embedding
    call fails, the vector search returns nothing, or any exception
    propagates. The selector itself handles most of these; this
    wrapper adds the timeout ceiling and the session plumbing.
    """
    from app.context.selectors.passages import (
        EMBEDDING_MODEL_TO_DIM,
        select_l3_passages,
    )

    if embedding_client is None or not project.embedding_model:
        return []

    embedding_dim = EMBEDDING_MODEL_TO_DIM.get(project.embedding_model)
    if embedding_dim is None:
        logger.debug(
            "Mode 3 L3 skipped: unknown embedding_model=%s",
            project.embedding_model,
        )
        return []

    try:
        async with neo4j_session() as session:
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


async def build_full_mode(
    summaries_repo: SummariesRepo,
    glossary_client: GlossaryClient,
    *,
    user_id: UUID,
    project: Project,
    message: str,
    embedding_client: EmbeddingClient | None = None,
) -> BuiltContext:
    """Build the Mode 3 memory block.

    Mirrors Mode 2's layer-timeout pattern for L0/L1/glossary, then
    adds the L2 fact selector, L3 semantic passages, and absence
    detection on top. Intent-aware CoT instructions close the block.

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
            ),
            timeout=settings.context_glossary_timeout_s,
        )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="glossary").inc()
        entities = []

    if l1_summary is not None and entities:
        entities = filter_entities_not_in_summary(
            entities,
            l1_summary.content,
            min_overlap=settings.dedup_min_overlap,
        )

    # ── L2 facts + L3 passages (Neo4j, parallel) ────────────────────────
    # Classify once: the same IntentResult drives both the L2 selector's
    # hop-count / recency gating AND the instruction-block hint text.
    intent_obj = classify(message)
    l2_facts, l3_passages = await asyncio.gather(
        _safe_l2_facts(
            user_id=user_id, project=project, intent=intent_obj,
        ),
        _safe_l3_passages(
            embedding_client,
            user_id=user_id, project=project,
            message=message, intent=intent_obj,
        ),
    )
    mentioned_entities = list(intent_obj.entities)

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

    # ── render ──────────────────────────────────────────────────────────
    lines: list[str] = ['<memory mode="full">']

    if l0 is not None and l0.content.strip():
        lines.append(f"  <user>{sanitize_for_xml(l0.content)}</user>")

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

    if entities:
        lines.append("  <glossary>")
        for e in entities:
            # Reuse Mode 2's entity renderer inline — duplicating the
            # 15-line helper is less churn than exposing it cross-module
            # for a scaffold that'll change in Commit 3.
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

    lines.extend(_render_facts_block(l2_facts))

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

    if absences:
        lines.append("  <no_memory_for>")
        for name in absences:
            lines.append(f"    <entity>{sanitize_for_xml(name)}</entity>")
        lines.append("  </no_memory_for>")

    instructions = build_instructions_block(
        intent_obj.intent,
        has_facts=l2_facts.total() > 0,
        has_passages=bool(l3_passages),
        has_absences=bool(absences),
    )
    lines.append(f"  <instructions>{sanitize_for_xml(instructions)}</instructions>")
    lines.append("</memory>")

    context = "\n".join(lines)
    return BuiltContext(
        mode="full",
        context=context,
        recent_message_count=_RECENT_MESSAGE_COUNT,
        token_count=estimate_tokens(context),
    )
