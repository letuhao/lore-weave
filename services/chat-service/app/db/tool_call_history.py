"""Track C Phase 2 — which of this session's tool calls actually SUCCEEDED.

The server already records every executed tool call on the assistant message
(``chat_messages.tool_calls`` JSONB: an ordered list of ``{iteration, tool, args, ok,
result|error}``). It has always been there, for UI replay — and it is exactly the record the
rail driver needs, because it answers "what have I already done?" from the SERVER's memory
instead of the model's.

Note the ``ok`` filter. A tool that was called and FAILED has not done its step; counting the
attempt would march the agent past the very thing it needs to retry. (And even a successful
call is not the last word — a tool can return success having written nothing, which is why
the book-state artifact outranks this signal wherever an artifact exists. See
``rail_progress.compute_rail_progress``.)
"""

from __future__ import annotations

import json
import logging

import asyncpg

logger = logging.getLogger(__name__)


async def succeeded_tools(pool: asyncpg.Pool, session_id: str) -> set[str]:
    """The set of tool names that have run SUCCESSFULLY at least once in this session."""
    try:
        rows = await pool.fetch(
            """
            SELECT tool_calls
              FROM chat_messages
             WHERE session_id = $1::uuid
               AND tool_calls IS NOT NULL
             ORDER BY sequence_num
            """,
            session_id,
        )
    except Exception:  # noqa: BLE001 — grounding is best-effort; never break the turn
        logger.warning("tool-call history unavailable for session=%s", session_id, exc_info=True)
        return set()

    out: set[str] = set()
    for r in rows:
        raw = r["tool_calls"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                continue
        if not isinstance(raw, list):
            continue
        for tc in raw:
            if isinstance(tc, dict) and tc.get("ok") and tc.get("tool"):
                out.add(str(tc["tool"]))
    return out
