"""ARCH-1 C6 — suspended-run persistence for AG-UI frontend-tool-calls.

When the model calls a frontend tool, the turn pauses and the in-flight
conversation state is stored here keyed by run_id (see migrate.py
chat_suspended_runs). The resume endpoint loads it, appends the tool result,
runs a 2nd LLM pass, then deletes it. Plain async functions to match the
service's inline-SQL style (chat-service has no repository layer).

Security: load/delete are scoped by owner_user_id so one user can't resume
another user's suspended run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg


@dataclass
class SuspendedRun:
    run_id: str
    session_id: str
    owner_user_id: str
    message_id: str
    working: list[dict]
    pending_tool_call: dict  # {id, name, args}
    input_tokens: int
    output_tokens: int
    model_source: str
    model_ref: str
    parent_message_id: str | None
    user_message_content: str
    # RAID Wave C2 (DR-C2) — the permission mode the turn ran under; the resume
    # pass continues under the SAME mode (default keeps pre-C2 rows on 'write').
    permission_mode: str = "write"


async def save_suspended_run(
    pool: asyncpg.Pool,
    *,
    run_id: str,
    session_id: str,
    owner_user_id: str,
    message_id: str,
    working: list[dict],
    pending_tool_call: dict,
    input_tokens: int,
    output_tokens: int,
    model_source: str,
    model_ref: str,
    parent_message_id: str | None,
    user_message_content: str,
    permission_mode: str = "write",
) -> None:
    await pool.execute(
        """
        INSERT INTO chat_suspended_runs
          (run_id, session_id, owner_user_id, message_id, working,
           pending_tool_call, input_tokens, output_tokens, model_source,
           model_ref, parent_message_id, user_message_content, permission_mode)
        VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9,$10,$11,$12,$13)
        """,
        run_id, session_id, owner_user_id, message_id,
        json.dumps(working), json.dumps(pending_tool_call),
        input_tokens, output_tokens, model_source, model_ref,
        parent_message_id, user_message_content, permission_mode,
    )


def _parse_json(raw: object) -> object:
    return json.loads(raw) if isinstance(raw, str) else raw


async def load_suspended_run(
    pool: asyncpg.Pool, run_id: str, owner_user_id: str
) -> SuspendedRun | None:
    """Load a suspended run scoped to its owner. Returns None if missing,
    expired, or owned by another user (all surfaced uniformly as "not found")."""
    row = await pool.fetchrow(
        """
        SELECT run_id, session_id, owner_user_id, message_id, working,
               pending_tool_call, input_tokens, output_tokens, model_source,
               model_ref, parent_message_id, user_message_content,
               permission_mode
        FROM chat_suspended_runs
        WHERE run_id = $1 AND owner_user_id = $2 AND expires_at > now()
        """,
        run_id, owner_user_id,
    )
    if row is None:
        return None
    return SuspendedRun(
        run_id=str(row["run_id"]),
        session_id=str(row["session_id"]),
        owner_user_id=str(row["owner_user_id"]),
        message_id=str(row["message_id"]),
        working=_parse_json(row["working"]),
        pending_tool_call=_parse_json(row["pending_tool_call"]),
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        model_source=row["model_source"],
        model_ref=str(row["model_ref"]),
        parent_message_id=str(row["parent_message_id"]) if row["parent_message_id"] else None,
        user_message_content=row["user_message_content"],
        permission_mode=str(row["permission_mode"] or "write"),
    )


async def delete_suspended_run(pool: asyncpg.Pool, run_id: str) -> None:
    await pool.execute("DELETE FROM chat_suspended_runs WHERE run_id = $1", run_id)


async def sweep_expired_runs(pool: asyncpg.Pool) -> int:
    """Delete abandoned suspended runs (proposals the user never acted on).
    Returns the number swept. Called periodically from the lifespan."""
    status = await pool.execute(
        "DELETE FROM chat_suspended_runs WHERE expires_at <= now()"
    )
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0
