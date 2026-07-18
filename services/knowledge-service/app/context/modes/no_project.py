"""Mode 1 — no project.

Builds the smallest possible memory block: just the user's global
identity (L0) plus a short instruction telling the LLM this session
isn't attached to any project. No glossary, no project-level context,
no extraction.

Invoked when the chat session has `project_id IS NULL`. The returned
`recent_message_count` comes from `settings.recent_message_count`
(D-T2-03; default 50, env `RECENT_MESSAGE_COUNT`) — chat-service
replays the last N messages as usual.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.config import settings
from app.context.formatters.token_counter import estimate_tokens
from app.context.formatters.xml_escape import sanitize_for_xml
from app.context.selectors.summaries import load_global_summary
from app.db.repositories.summaries import SummariesRepo
from app.metrics import layer_timeout_total

logger = logging.getLogger(__name__)

__all__ = ["BuiltContext", "build_no_project_mode", "split_at_boundary"]

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
    # K18.9 — split of `context` into a cacheable prefix and a
    # per-message suffix. chat-service uses these to emit structured
    # Anthropic system content with `cache_control` on the stable part
    # so subsequent turns in the session re-use the cached prefix
    # instead of re-tokenising. Invariant: context == stable + volatile
    # (byte-for-byte, no separator loss). For modes where the whole
    # block is message-independent (Mode 1), volatile stays "" and
    # stable carries everything; for Mode 2/3 stable ends at </project>.
    stable_context: str = ""
    volatile_context: str = ""
    # K21.12-BE (design D9): per-project tool-calling toggle, surfaced
    # to chat-service so it can gate its tool-calling loop. Mode 1
    # (no_project) has no project row, so the default `True` stands;
    # Mode 2/3 overwrite it from the loaded project. Defaulting True
    # also keeps any degraded path tool-enabled rather than silently
    # disabling tools.
    tool_calling_enabled: bool = True
    # WS-4C Half A: per-project canon auto-capture toggle, surfaced to chat so it
    # can gate its post-turn capture task. Defaults FALSE — the opposite of
    # tool_calling_enabled, deliberately: capture spends the user's tokens, so a
    # mode with no project row (Mode 1) or a degraded build must fail CLOSED. Mode
    # 2 overwrites it from the loaded project; MULTI leaves it false (no single
    # book to capture into).
    canon_capture_enabled: bool = False
    # Track 4 P0 — the glossary entity ids that actually reached the rendered
    # block (post-budget-trim). The router records these to `entity_access_log`
    # fire-and-forget (off the latency path) so retrieval salience can be
    # LEARNED (P1). Empty for Mode 1 (no project → no entities).
    surfaced_entity_ids: list[str] = field(default_factory=list)
    # Track B B1(2) — in MULTI mode the surfaced entities span several projects and
    # `surfaced_entity_ids` is a merged flat list, so the router can't attribute
    # salience per-project off `req.project_id` (which is None in multi). This maps
    # each surfaced entity to its SOURCE project so the router records salience
    # per-project (D-MULTI-SALIENCE-WRITEBACK). Empty for single/no-project modes.
    surfaced_by_project: dict[str, list[str]] = field(default_factory=dict)
    # Chat Quality Wave W1 — per-section token split of `context` (estimate_tokens
    # over each rendered section, POST-budget-trim), e.g. {"user": ..,
    # "project": .., "glossary_entities": .., "facts": .., "passages": ..,
    # "summaries": .., "instructions": ..}. Additive: older callers ignore it;
    # chat-service nests it under the contextBudget frame's memory_knowledge.
    # Section keys are omitted when the section wasn't rendered.
    sections: dict[str, int] = field(default_factory=dict)


def split_at_boundary(lines: list[str], stable_line_count: int) -> tuple[str, str, str]:
    """Produce `(stable_context, volatile_context, context)` from a
    line-accumulated block by splitting at `stable_line_count`.

    The tricky bit is the newline that would separate `lines[n-1]`
    from `lines[n]` in the original `"\n".join(lines)` output. Without
    handling it explicitly, `stable + volatile` loses that byte and
    the K18.9 invariant `context == stable + volatile` breaks. We put
    the separator on the tail of stable so both halves concat cleanly.

    When `stable_line_count == len(lines)` (all-stable case, e.g.
    Mode 1), stable is the full blob without a trailing newline and
    volatile is the empty string — matches the pre-K18.9 shape.
    """
    if stable_line_count >= len(lines):
        stable = "\n".join(lines)
        volatile = ""
    elif stable_line_count <= 0:
        stable = ""
        volatile = "\n".join(lines)
    else:
        stable = "\n".join(lines[:stable_line_count]) + "\n"
        volatile = "\n".join(lines[stable_line_count:])
    return stable, volatile, stable + volatile


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
    sections: dict[str, int] = {}  # W1 — per-section token split
    if has_bio:
        user_line = f"  <user>{sanitize_for_xml(summary.content)}</user>"
        lines.append(user_line)
        sections["user"] = estimate_tokens(user_line)
    instructions = _INSTRUCTIONS_WITH_BIO if has_bio else _INSTRUCTIONS_NO_BIO
    instructions_line = f"  <instructions>{sanitize_for_xml(instructions)}</instructions>"
    lines.append(instructions_line)
    sections["instructions"] = estimate_tokens(instructions_line)
    lines.append("</memory>")
    # K18.9: Mode 1 has no message-dependent content, so the whole block
    # is cacheable. stable carries everything; volatile stays "".
    stable, volatile, context = split_at_boundary(lines, len(lines))
    return BuiltContext(
        mode="no_project",
        context=context,
        recent_message_count=settings.recent_message_count,
        token_count=estimate_tokens(context),
        stable_context=stable,
        volatile_context=volatile,
        sections=sections,
    )
