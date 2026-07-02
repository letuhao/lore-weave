"""RAID Wave C2 (DR-C2) — per-user Tier-A tool approval allowlist.

In Write mode, the tool loop suspends on a Tier-A server tool the user has
not allowlisted; the FE renders approve-once / always-allow / deny. "Always
allow" persists a row here (per-USER tier — a tool's trustworthiness is not
book-specific), so the tool never prompts again for this user.

Plain async functions to match the service's inline-SQL style (chat-service
has no repository layer). Every query is scoped by user_id (tenancy).

Failure semantics (DR-C2 reversibility): callers treat a READ failure as
fail-OPEN — a DB blip must not brick tool calling. The read helper itself
raises; the call site in the tool loop catches + degrades to "approved".
"""
from __future__ import annotations

import asyncpg


async def is_tool_approved(pool: asyncpg.Pool, user_id: str, tool_name: str) -> bool:
    """True when the user has an "Always allow" row for this tool."""
    row = await pool.fetchval(
        "SELECT 1 FROM user_tool_approvals WHERE user_id = $1 AND tool_name = $2",
        user_id, tool_name,
    )
    return row is not None


async def approve_tool(pool: asyncpg.Pool, user_id: str, tool_name: str) -> None:
    """Persist an "Always allow" row (idempotent — re-approving is a no-op)."""
    await pool.execute(
        """
        INSERT INTO user_tool_approvals (user_id, tool_name)
        VALUES ($1, $2)
        ON CONFLICT (user_id, tool_name) DO NOTHING
        """,
        user_id, tool_name,
    )
