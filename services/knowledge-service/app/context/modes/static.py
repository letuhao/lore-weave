"""Mode 2 — static (project linked, extraction disabled).

Builds a memory block containing:
  - L0 global bio (optional, from knowledge_summaries scope='global')
  - project block: name + instructions + L1 summary
  - glossary block: entities selected by K2b's tiered selector
  - mode-level instructions for the LLM

Graceful-degradation rules:
  - L0 missing                  → <user> omitted
  - L1 summary missing          → <summary> omitted, <project> still emitted
  - project.book_id is None     → <glossary> omitted
  - glossary-service down       → <glossary> omitted (client returns [])
  - empty glossary result       → <glossary> omitted (no empty element)

All user content is XML-escaped via sanitize_for_xml().

The builder receives an already-fetched Project (the dispatcher is
responsible for the fetch + ProjectNotFound handling). This avoids a
double-fetch and keeps Mode 2's responsibility tight: take a project,
produce a context block.
"""

from uuid import UUID

from app.clients.glossary_client import GlossaryClient, GlossaryEntityForContext
from app.config import settings
from app.context.formatters.dedup import filter_entities_not_in_summary
from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.modes.no_project import BuiltContext
from app.context.selectors.glossary import select_glossary_for_context
from app.context.selectors.summaries import load_global_summary
from app.context.selectors.projects import load_project_summary
from app.db.models import Project
from app.db.repositories.summaries import SummariesRepo

__all__ = ["build_static_mode"]

_RECENT_MESSAGE_COUNT = 50

_INSTRUCTIONS = (
    "This session is attached to a project. Use the <project> instructions "
    "and <summary> as durable context, and the <glossary> entries as "
    "authoritative facts about named characters, places, and concepts. "
    "Prefer glossary details over anything you might have inferred from "
    "the recent messages."
)


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())


def _render_entity(e: GlossaryEntityForContext) -> str:
    # Attributes: kind + tier + score. score rounded to 2dp for readability.
    attrs = (
        f'kind="{sanitize_for_xml(e.kind_code)}" '
        f'tier="{sanitize_for_xml(e.tier)}" '
        f'score="{e.rank_score:.2f}"'
    )
    lines = [f"<entity {attrs}>"]
    name = sanitize_for_xml(e.cached_name or "")
    if name:
        lines.append(f"  <name>{name}</name>")
    if e.cached_aliases:
        joined = ", ".join(a for a in e.cached_aliases if a)
        if joined:
            lines.append(f"  <aliases>{sanitize_for_xml(joined)}</aliases>")
    if e.short_description:
        lines.append(
            f"  <description>{sanitize_for_xml(e.short_description)}</description>"
        )
    lines.append("</entity>")
    return "\n".join(lines)


async def build_static_mode(
    summaries_repo: SummariesRepo,
    glossary_client: GlossaryClient,
    *,
    user_id: UUID,
    project: Project,
    message: str,
) -> BuiltContext:
    """Build a Mode 2 memory block for a user + project + current message.

    `project` is pre-fetched by the dispatcher (the dispatcher also
    handles cross-user and extraction-enabled checks). `message` is
    the user's current turn, used as the glossary FTS query.
    """
    # Fetch all the pieces in parallel-friendly order. We don't actually
    # parallelise with asyncio.gather because the Postgres pool and
    # HTTP client have separate connection pools — sequential is fine
    # and simpler. Track 2 can revisit if latency matters.
    l0 = await load_global_summary(summaries_repo, user_id)
    l1_summary = await load_project_summary(summaries_repo, user_id, project.project_id)
    entities = await select_glossary_for_context(
        glossary_client,
        user_id=user_id,
        project=project,
        message=message,
    )
    # K4.12: drop glossary rows whose keywords already overlap the L1
    # summary — the summary is authored prose and richer, the glossary
    # row would be redundant. Pinned entities are never dropped. The
    # min_overlap threshold is tunable via settings (K4-I7).
    if l1_summary is not None and entities:
        entities = filter_entities_not_in_summary(
            entities,
            l1_summary.content,
            min_overlap=settings.dedup_min_overlap,
        )

    lines: list[str] = ['<memory mode="static">']

    # ── L0 (optional) ───────────────────────────────────────────────────
    if l0 is not None and l0.content.strip():
        lines.append(f"  <user>{sanitize_for_xml(l0.content)}</user>")

    # ── project block ──────────────────────────────────────────────────
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

    # ── glossary (optional) ────────────────────────────────────────────
    if entities:
        lines.append("  <glossary>")
        for e in entities:
            lines.append(_indent(_render_entity(e), 4))
        lines.append("  </glossary>")

    # ── mode-level instructions (always) ───────────────────────────────
    lines.append(f"  <instructions>{sanitize_for_xml(_INSTRUCTIONS)}</instructions>")
    lines.append("</memory>")

    context = "\n".join(lines)
    return BuiltContext(
        mode="static",
        context=context,
        recent_message_count=_RECENT_MESSAGE_COUNT,
        token_count=estimate_tokens(context),
    )
