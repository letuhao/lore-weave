"""Mode 1 — no project.

Builds the smallest possible memory block: just the user's global
identity (L0) plus a short instruction telling the LLM this session
isn't attached to any project. No glossary, no project-level context,
no extraction.

Invoked when the chat session has `project_id IS NULL`. The caller's
recent_message_count is 50 — chat-service replays the last 50 messages
as usual.
"""

from dataclasses import dataclass
from uuid import UUID

from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.selectors.summaries import load_global_summary
from app.db.repositories.summaries import SummariesRepo

__all__ = ["BuiltContext", "build_no_project_mode"]

_RECENT_MESSAGE_COUNT = 50

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
    """
    summary = await load_global_summary(repo, user_id)
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
        recent_message_count=_RECENT_MESSAGE_COUNT,
        token_count=estimate_tokens(context),
    )
