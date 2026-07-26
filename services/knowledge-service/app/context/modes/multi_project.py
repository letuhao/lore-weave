"""Track B B1(2) — multi-project (multi-KG) context mode.

Unions the glossary entities + L2 facts + L3 passages + summary hits of a SET of
projects into ONE memory block under a SHARED token budget, with cross-project
DEDUP + GLOBAL rank (EC-B3/B4). This is the "agent loads several KGs into one chat
session" path.

Design (reuse-heavy — the deep single-project pipeline stays authoritative):
  - Per project, fan out the SAME Mode-3 retrieval the single-project builder uses
    (``_safe_l2_facts`` / ``_safe_l3_passages`` / ``_safe_summary_blend`` +
    ``select_glossary_for_context`` + ``apply_salience``). All the timeout / degrade
    safety comes for free.
  - MERGE across projects: entities dedup by name (keep the highest-salience copy —
    the world-bible entity that also appears in a member book collapses to one),
    facts dedup by text, passages dedup by source_id, summaries dedup by (level, path).
    Everything is then GLOBALLY re-sorted by its own score so the shared budget spends
    on the most relevant items regardless of which project they came from.
  - RENDER one block: a ``<projects>`` header (name + instructions + summary per
    project) then the merged ``<glossary>/<facts>/<passages>/<summaries>``, each item
    tagged with its ``project`` so the model can attribute cross-book facts.
  - BUDGET: one shared ``settings.mode3_token_budget`` trimmed in reverse priority
    (passages → summaries → background facts → glossary tail), mirroring the
    single-project enforcer's order.

Single project in the set → this still works (a union of one), but the dispatcher
routes a lone project to the richer single-project full mode; this mode is for N≥2.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.clients.llm_client import LLMClient
from app.config import settings
from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.intent.classifier import classify
from loreweave_context import scale_by_window
from app.context.modes.full import (
    _safe_l2_facts,
    _safe_l3_passages,
    _safe_summary_blend,
)
from app.context.modes.no_project import BuiltContext
from app.context.selectors.glossary import select_glossary_for_context
from app.context.selectors.salience import apply_salience
from app.db.models import Project
from app.db.repositories.summaries import SummariesRepo
from app.context.selectors.projects import load_project_summary
from app.context.selectors.summaries import load_global_summary
from app.metrics import layer_timeout_total

logger = logging.getLogger(__name__)

__all__ = ["build_multi_project_mode"]

# Same tighter history window as single-project full mode — the graphs carry the
# durable memory.
_RECENT_MESSAGE_COUNT = 20


async def _retrieve_one(
    *,
    project: Project,
    user_id: UUID,
    message: str,
    intent,
    embedding_client: EmbeddingClient | None,
    llm_client: LLMClient | None,
    glossary_client: GlossaryClient,
    language: str | None,
    entity_access_repo,
) -> dict:
    """Run one project's Mode-3 retrieval (glossary + L2 + L3 + summary), returning
    the raw scored pieces tagged with the project. Degrade-safe throughout."""
    try:
        entities = await asyncio.wait_for(
            select_glossary_for_context(
                glossary_client,
                user_id=user_id,
                project=project,
                message=message,
                embedding_client=embedding_client,
                language=language,
            ),
            timeout=settings.context_glossary_timeout_s,
        )
    except (asyncio.TimeoutError, Exception):
        layer_timeout_total.labels(layer="glossary").inc()
        entities = []

    entities = await apply_salience(entity_access_repo, entities, user_id, project.project_id)

    l2_facts, l3_passages, summary_hits = await asyncio.gather(
        _safe_l2_facts(user_id=user_id, project=project, intent=intent),
        _safe_l3_passages(
            embedding_client,
            user_id=user_id, project=project, message=message, intent=intent,
            llm_client=llm_client,
        ),
        _safe_summary_blend(
            embedding_client,
            user_id=user_id, project=project, message=message,
            glossary_entities=[e.cached_name for e in entities if getattr(e, "cached_name", None)],
        ),
    )
    return {
        "project": project,
        "entities": list(entities),
        "l2": l2_facts,
        "l3": list(l3_passages),
        "summaries": list(summary_hits),
    }


def _merge_entities(per_project: list[dict]) -> list[tuple[Project, object]]:
    """Dedup entities by lowercased name across projects (keep the highest
    rank_score copy), then GLOBAL-sort by rank_score desc. Returns (project, entity)
    so the render can attribute each. EC-B4: the world-bible entity that also appears
    in a member book collapses to ONE row (highest salience wins)."""
    best: dict[str, tuple[float, Project, object]] = {}
    for pp in per_project:
        proj = pp["project"]
        for e in pp["entities"]:
            name = (getattr(e, "cached_name", "") or "").strip().lower()
            key = name or f"__id:{getattr(e, 'entity_id', id(e))}"
            score = float(getattr(e, "rank_score", 0.0) or 0.0)
            if key not in best or score > best[key][0]:
                best[key] = (score, proj, e)
    ranked = sorted(best.values(), key=lambda t: t[0], reverse=True)
    return [(proj, e) for _score, proj, e in ranked]


def _merge_facts(per_project: list[dict]) -> list[tuple[str, str]]:
    """Dedup facts by text across all projects + buckets, keeping the FIRST
    (highest-priority) bucket a fact appeared in. Returns (project_name, fact_text),
    ordered current → recent → background (negatives folded into background here —
    the multi-project block keeps one flat, budget-trimmable fact list)."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    # bucket priority high→low; negatives last (still shown, they're corrective)
    for bucket in ("current", "recent", "background", "negative"):
        for pp in per_project:
            pname = pp["project"].name
            for f in getattr(pp["l2"], bucket, []) or []:
                k = f.strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    out.append((pname, f))
    return out


def _merge_passages(per_project: list[dict]) -> list[tuple[str, object]]:
    """Dedup passages by source_id, keep highest score, GLOBAL-sort by score desc."""
    best: dict[str, tuple[float, str, object]] = {}
    for pp in per_project:
        pname = pp["project"].name
        for p in pp["l3"]:
            key = getattr(p, "source_id", None) or id(p)
            score = float(getattr(p, "score", 0.0) or 0.0)
            if key not in best or score > best[key][0]:
                best[key] = (score, pname, p)
    ranked = sorted(best.values(), key=lambda t: t[0], reverse=True)
    return [(pname, p) for _s, pname, p in ranked]


def _merge_summaries(per_project: list[dict]) -> list[tuple[str, object]]:
    """Dedup summaries by (level, node_path), GLOBAL-sort by weighted_score desc."""
    best: dict[tuple, tuple[float, str, object]] = {}
    for pp in per_project:
        pname = pp["project"].name
        for h in pp["summaries"]:
            key = (getattr(h, "level", ""), getattr(h, "node_path", ""))
            score = float(getattr(h, "weighted_score", 0.0) or 0.0)
            if key not in best or score > best[key][0]:
                best[key] = (score, pname, h)
    ranked = sorted(best.values(), key=lambda t: t[0], reverse=True)
    return [(pname, h) for _s, pname, h in ranked]


def _render(
    *,
    projects: list[Project],
    l0,
    entities: list[tuple[Project, object]],
    facts: list[tuple[str, str]],
    passages: list[tuple[str, object]],
    summaries: list[tuple[str, object]],
    project_summaries: dict[str, object],
) -> tuple[str, dict[str, int]]:
    """Render the merged pieces into one multi-project ``<memory>`` block +
    per-section token split (W1)."""
    lines: list[str] = [f'<memory mode="multi" projects="{len(projects)}">']
    sections: dict[str, int] = {}

    def _close(name: str, start: int) -> None:
        if len(lines) > start:
            sections[name] = estimate_tokens("\n".join(lines[start:]))

    _m = len(lines)
    if l0 is not None and l0.content.strip():
        lines.append(f"  <user>{sanitize_for_xml(l0.content)}</user>")
        _close("user", _m)

    _m = len(lines)
    lines.append("  <projects>")
    for proj in projects:
        lines.append(f'    <project name="{sanitize_for_xml(proj.name)}">')
        if proj.instructions and proj.instructions.strip():
            lines.append(f"      <instructions>{sanitize_for_xml(proj.instructions)}</instructions>")
        ps = project_summaries.get(str(proj.project_id))
        if ps is not None and ps.content.strip():
            lines.append(f"      <summary>{sanitize_for_xml(ps.content)}</summary>")
        lines.append("    </project>")
    lines.append("  </projects>")
    _close("project", _m)

    _m = len(lines)
    if entities:
        lines.append("  <glossary>")
        for proj, e in entities:
            attrs = (
                f'project="{sanitize_for_xml(proj.name)}" '
                f'kind="{sanitize_for_xml(e.kind_code)}" '
                f'score="{float(getattr(e, "rank_score", 0.0) or 0.0):.2f}"'
            )
            lines.append(f"    <entity {attrs}>")
            if getattr(e, "cached_name", None):
                lines.append(f"      <name>{sanitize_for_xml(e.cached_name)}</name>")
            if getattr(e, "short_description", None):
                lines.append(f"      <description>{sanitize_for_xml(e.short_description)}</description>")
            lines.append("    </entity>")
        lines.append("  </glossary>")
        _close("glossary_entities", _m)

    _m = len(lines)
    if facts:
        lines.append("  <facts>")
        for pname, f in facts:
            lines.append(f'    <fact project="{sanitize_for_xml(pname)}">{sanitize_for_xml(f)}</fact>')
        lines.append("  </facts>")
        _close("facts", _m)

    _m = len(lines)
    if passages:
        lines.append("  <passages>")
        for pname, p in passages:
            attrs = (
                f'project="{sanitize_for_xml(pname)}" '
                f'source_id="{sanitize_for_xml(getattr(p, "source_id", ""))}" '
                f'score="{float(getattr(p, "score", 0.0) or 0.0):.2f}"'
            )
            lines.append(f"    <passage {attrs}>")
            lines.append(f"      {sanitize_for_xml(p.text)}")
            lines.append("    </passage>")
        lines.append("  </passages>")
        _close("passages", _m)

    _m = len(lines)
    if summaries:
        lines.append("  <summaries>")
        for pname, h in summaries:
            attrs = (
                f'project="{sanitize_for_xml(pname)}" '
                f'level="{sanitize_for_xml(getattr(h, "level", ""))}" '
                f'score="{float(getattr(h, "weighted_score", 0.0) or 0.0):.2f}"'
            )
            lines.append(f"    <summary {attrs}>")
            lines.append(f"      {sanitize_for_xml(h.summary_text)}")
            lines.append("    </summary>")
        lines.append("  </summaries>")
        _close("summaries", _m)

    _m = len(lines)
    lines.append(
        "  <instructions>You are grounded on SEVERAL knowledge graphs (worlds/books) "
        "at once. Each fact/entity/passage is tagged with its project — attribute "
        "cross-book claims to the right source and note when books disagree.</instructions>"
    )
    _close("instructions", _m)
    lines.append("</memory>")
    return "\n".join(lines), sections


def _enforce_shared_budget(
    *,
    projects: list[Project],
    l0,
    entities: list[tuple[Project, object]],
    facts: list[tuple[str, str]],
    passages: list[tuple[str, object]],
    summaries: list[tuple[str, object]],
    project_summaries: dict[str, object],
    budget_tokens: int,
) -> tuple[str, int, dict[str, int]]:
    """One SHARED budget across all projects — trim in reverse priority (passages →
    summaries → glossary tail → facts tail), mirroring the single-project order. The
    <projects> header (names + instructions + summaries) is protected."""
    ents, facts_l, pass_l, summ_l = list(entities), list(facts), list(passages), list(summaries)

    def render_count():
        ctx, sections = _render(
            projects=projects, l0=l0, entities=ents, facts=facts_l,
            passages=pass_l, summaries=summ_l, project_summaries=project_summaries,
        )
        return ctx, estimate_tokens(ctx), sections

    ctx, tokens, sections = render_count()
    # already-sorted lists → pop() removes the lowest-scored tail item.
    for _drop in (
        lambda: pass_l.pop() if pass_l else None,
        lambda: summ_l.pop() if summ_l else None,
        lambda: ents.pop() if ents else None,
        lambda: facts_l.pop() if facts_l else None,
    ):
        while tokens > budget_tokens and (pass_l or summ_l or ents or facts_l):
            before = (len(pass_l), len(summ_l), len(ents), len(facts_l))
            _drop()
            if (len(pass_l), len(summ_l), len(ents), len(facts_l)) == before:
                break  # this list is empty; move to the next drop tier
            ctx, tokens, sections = render_count()
        if tokens <= budget_tokens:
            break
    return ctx, tokens, sections


async def build_multi_project_mode(
    summaries_repo: SummariesRepo,
    glossary_client: GlossaryClient,
    *,
    user_id: UUID,
    projects: list[Project],
    message: str,
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
    language: str | None = None,
    entity_access_repo=None,
    context_length: int | None = None,
) -> BuiltContext:
    """Union the Mode-3 retrieval of ``projects`` into one shared-budget memory block.

    `context_length` (the calling chat session's real model window) scales the shared
    `mode3_token_budget` instead of every model being capped at the same flat number."""
    try:
        l0 = await asyncio.wait_for(
            load_global_summary(summaries_repo, user_id),
            timeout=settings.context_l0_timeout_s,
        )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l0").inc()
        l0 = None

    project_summaries: dict[str, object] = {}
    for proj in projects:
        try:
            ps = await asyncio.wait_for(
                load_project_summary(summaries_repo, user_id, proj.project_id),
                timeout=settings.context_l1_timeout_s,
            )
            if ps is not None:
                project_summaries[str(proj.project_id)] = ps
        except asyncio.TimeoutError:
            layer_timeout_total.labels(layer="l1").inc()

    intent = classify(message)
    per_project = await asyncio.gather(*[
        _retrieve_one(
            project=proj, user_id=user_id, message=message, intent=intent,
            embedding_client=embedding_client, llm_client=llm_client,
            glossary_client=glossary_client, language=language,
            entity_access_repo=entity_access_repo,
        )
        for proj in projects
    ])

    entities = _merge_entities(per_project)
    facts = _merge_facts(per_project)
    passages = _merge_passages(per_project)
    summaries = _merge_summaries(per_project)

    context, token_count, sections = _enforce_shared_budget(
        projects=projects, l0=l0, entities=entities, facts=facts,
        passages=passages, summaries=summaries, project_summaries=project_summaries,
        budget_tokens=scale_by_window(settings.mode3_token_budget, context_length),
    )

    # Track B B1(2) — keep each surfaced entity's SOURCE project (it's right here in
    # the (proj, e) tuple) so the router can record salience PER-PROJECT in multi mode
    # (D-MULTI-SALIENCE-WRITEBACK); a flat list can't be attributed off req.project_id
    # (None in multi). surfaced stays the flat list for back-compat.
    surfaced: list[str] = []
    surfaced_by_project: dict[str, list[str]] = {}
    for _proj, e in entities:
        eid = getattr(e, "entity_id", None)
        if eid:
            surfaced.append(eid)
            surfaced_by_project.setdefault(str(_proj.project_id), []).append(eid)
    # tool-calling enabled if ANY project allows it (union is permissive; the caller
    # already owns every project in the set).
    tool_calling = any(getattr(p, "tool_calling_enabled", True) for p in projects)
    return BuiltContext(
        mode="multi",
        context=context,
        recent_message_count=_RECENT_MESSAGE_COUNT,
        token_count=token_count,
        stable_context="",
        volatile_context=context,
        tool_calling_enabled=tool_calling,
        # WS-4C Half A: capture writes into ONE book's glossary inbox, and a multi-project
        # turn grounds on a UNION of projects with no single book. There is no correct
        # target, so capture is OFF here — stated explicitly rather than left to inherit
        # the dataclass default. (Chat independently requires a single resolved project.)
        canon_capture_enabled=False,
        surfaced_entity_ids=surfaced,
        surfaced_by_project=surfaced_by_project,
        sections=sections,
    )
