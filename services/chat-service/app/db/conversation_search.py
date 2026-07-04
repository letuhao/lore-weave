"""T6 (Context Budget Law D6) — conversation_search recovery engine.

Lossy compaction is safe ONLY if a fact dropped from the rolling summary is still
RECOVERABLE: the raw turns stay in Postgres, so the agent can pull one back. This is
the search half of that safety net — a session-scoped lookup over the CURRENT
conversation's message history (the tool wiring that exposes it to the agent is a
separate slice).

Match is a case-insensitive SUBSTRING (`ILIKE`), NOT `to_tsvector('english', …)`:
this is a multilingual novel workspace, and a recovery query is almost always a NAME
(`Lâm Uyển`, `万古神帝`) that English FTS stems/tokenizes wrong. Over a single
session's bounded message set (tens–hundreds of rows) a substring scan needs no
trigram index and finds the exact mention every time — correctness over cleverness.
Session + owner scoped (tenancy; matches every sibling query — not join-only).
"""
from __future__ import annotations

from dataclasses import dataclass

import asyncpg

# A recovered hit carries just enough to re-ground: where it was + a focused snippet.
_SNIPPET_RADIUS = 160  # chars of context on each side of the match


@dataclass(frozen=True)
class ConversationHit:
    sequence_num: int
    role: str
    snippet: str


def _snippet(content: str, needle: str) -> str:
    """A window of `content` centered on the first case-insensitive match of
    `needle` (so the caller sees the fact in context, not the whole turn)."""
    if not content:
        return ""
    idx = content.lower().find(needle.lower())
    if idx < 0:  # matched on a different field/normalization — return the head
        return content[: _SNIPPET_RADIUS * 2].strip()
    start = max(0, idx - _SNIPPET_RADIUS)
    end = min(len(content), idx + len(needle) + _SNIPPET_RADIUS)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end].strip()}{suffix}"


async def search_session_messages(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    owner_user_id: str,
    query: str,
    limit: int = 8,
) -> list[ConversationHit]:
    """Recover turns in THIS session whose content mentions `query`, oldest-first
    (so the agent reads them in narrative order). Empty query / no match → ``[]``.

    Scoped to `session_id AND owner_user_id` (tenancy) and the live branch (0). Only
    non-error rows with real text are searched. `limit` is clamped to a sane cap so a
    recovery pull can never dump the whole transcript back into context.
    """
    q = (query or "").strip()
    if not q:
        return []
    lim = max(1, min(int(limit or 8), 25))
    # Escape LIKE metacharacters so a query containing % or _ matches LITERALLY
    # (a name is data, not a pattern) — ESCAPE '\' below pairs with this.
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = await pool.fetch(
        """
        SELECT sequence_num, role, content
        FROM chat_messages
        WHERE session_id = $1 AND owner_user_id = $2 AND branch_id = 0
          AND is_error = false AND content IS NOT NULL AND content <> ''
          AND content ILIKE '%' || $3 || '%' ESCAPE '\\'
        ORDER BY sequence_num ASC
        LIMIT $4
        """,
        session_id, owner_user_id, like, lim,
    )
    return [
        ConversationHit(
            sequence_num=r["sequence_num"],
            role=r["role"],
            snippet=_snippet(r["content"], q),
        )
        for r in rows
    ]
