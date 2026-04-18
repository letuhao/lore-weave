"""Mode 1 — no project.

Builds the smallest possible memory block: just the user's global
identity (L0) plus a short instruction telling the LLM this session
isn't attached to any project. No glossary, no project-level context,
no extraction.

Invoked when the chat session has `project_id IS NULL`. The caller's
recent_message_count is 50 — chat-service replays the last 50 messages
as usual.
"""

import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID

from app.config import settings
from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.selectors.summaries import load_global_summary
from app.db.repositories.summaries import SummariesRepo
from app.metrics import layer_timeout_total

logger = logging.getLogger(__name__)

__all__ = ["BuiltContext", "build_no_project_mode"]

# D-T2-03 — was a module-level 50. Now reads from settings so a
# tune via RECENT_MESSAGE_COUNT env var applies here AND in
# chat-service's KnowledgeClient fallback in one change.

# Two instruction variants — the with-bio text references "above" which
# is only accurate when a <user> element was actually emitted.
_INSTRUCTIONS_WITH_BIO = (
    "When the user references their identity or goals, use the information "
    "in the <user> element above. This session is not attached to any "
    "project, so no project memory or glossary is available."
)

_INSTRUCTIONS_NO_BIO = (
    "This session is not attached to any project, so no project memory or "
    "glossary is available. The user has not provided any global bio."
)


@dataclass
class BuiltContext:
    mode: str
    context: str
    recent_message_count: int
    token_count: int


async def build_no_project_mode(
    repo: SummariesRepo, user_id: UUID
) -> BuiltContext:
    """Return a Mode 1 memory block for `user_id`.

    If the user has no global summary, the `<user>` element is omitted
    and only `<instructions>` is returned — the block is still valid
    XML and chat-service can inject it unchanged.

    K6.1: L0 load is wrapped in asyncio.wait_for(context_l0_timeout_s).
    On timeout we skip the bio and keep building — the no-bio path
    is already supported and produces a valid block.
    """
    try:
        summary = await asyncio.wait_for(
            load_global_summary(repo, user_id),
            timeout=settings.context_l0_timeout_s,
        )
    except asyncio.TimeoutError:
        layer_timeout_total.labels(layer="l0").inc()
        logger.warning(
            "context builder L0 timeout user_id=%s budget=%.3fs",
            user_id, settings.context_l0_timeout_s,
        )
        summary = None
    has_bio = summary is not None and summary.content.strip() != ""
    lines = ['<memory mode="no_project">']
    if has_bio:
        lines.append(f"  <user>{sanitize_for_xml(summary.content)}</user>")
    instructions = _INSTRUCTIONS_WITH_BIO if has_bio else _INSTRUCTIONS_NO_BIO
    lines.append(f"  <instructions>{sanitize_for_xml(instructions)}</instructions>")
    lines.append("</memory>")
    context = "\n".join(lines)
    return BuiltContext(
        mode="no_project",
        context=context,
        recent_message_count=settings.recent_message_count,
        token_count=estimate_tokens(context),
    )
