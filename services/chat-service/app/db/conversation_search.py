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

# ── the agent-facing tool (chat-native, server-executed — like find_tools) ────
CONVERSATION_SEARCH_NAME = "conversation_search"

# LLM-client-first (frontend-tool contract): self-describing, tells the model WHEN
# to reach for it. `query` is free-form (a name/phrase) — no enum; `limit` is an int.
CONVERSATION_SEARCH_TOOL: dict = {
    "type": "function",
    "function": {
        "name": CONVERSATION_SEARCH_NAME,
        "description": (
            "Search EARLIER messages in THIS conversation for a fact you no longer "
            "see in context (a name, a decision, a number established before). Older "
            "turns scroll out / get compacted but are kept — call this to pull one "
            "back instead of guessing or asking the user to repeat themselves. Give "
            "the exact name/phrase to look for. Returns matching earlier turns "
            "(oldest-first) with a snippet; empty means it was never discussed here."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The exact name or phrase to find (e.g. a character name).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max earlier turns to return (default 8, max 25).",
                    "default": 8,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

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


async def run_conversation_search(
    pool: asyncpg.Pool,
    *,
    session_id: str,
    owner_user_id: str,
    args: dict,
) -> dict:
    """Execute the conversation_search tool and shape an LLM-client-first result —
    a plain dict the model reads directly (mirrors ``find_tools_result``).

    NEVER a silent no-op (H6/H10): a missing query, an empty result, and a DB
    error each return a distinct, self-correcting payload so the agent can react
    (rephrase / conclude "not discussed" / not falsely deny) instead of guessing.
    A DB blip surfaces as ``{"error": …}`` (the tool loop marks the call not-ok);
    the read carries no write → the caller must NOT decrement the write budget.
    """
    query = str(args.get("query", "") or "").strip()
    if not query:
        return {
            "query": "", "count": 0, "hits": [],
            "message": "Provide the exact name or phrase to search for.",
        }
    try:
        limit = int(args.get("limit", 8))
    except (TypeError, ValueError):
        limit = 8
    try:
        hits = await search_session_messages(
            pool, session_id=session_id, owner_user_id=owner_user_id,
            query=query, limit=limit,
        )
    except Exception as exc:  # a DB blip must surface, never read as "not discussed"
        return {"error": f"conversation_search could not read the history: {exc}"}
    if not hits:
        return {
            "query": query, "count": 0, "hits": [],
            "message": (
                f"No earlier message in this conversation mentions '{query}'. "
                "It may not have been discussed here."
            ),
        }
    return {
        "query": query,
        "count": len(hits),
        "hits": [
            {"turn": h.sequence_num, "role": h.role, "snippet": h.snippet}
            for h in hits
        ],
    }
