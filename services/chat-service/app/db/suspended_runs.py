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
    # WS-3 — the PINNED rail's step tools, carried across the suspend.
    #
    # The rail's TEXT survives a suspend for free (it lives in the system message, which
    # is persisted in `working`), but its TOOLS did not: the resume pass re-derives the
    # tool surface from scratch and has no book_id to re-fetch the binding with. So the
    # resumed turn read a recipe naming tools it could not call — and a rail whose FIRST
    # gate is a confirm (vision-to-book step 3 of 12) hits that on its very first gate. A rail that
    # looks runnable but cannot run is the worst failure shape there is.
    pinned_step_tools: list[str] | None = None
    # P-1 step-runner — the rail's book, carried across the suspend so the RESUME pass can
    # re-fetch the pinned workflows + re-probe the book and KEEP DRIVING the rail. Without it
    # the rail dead-ends at its confirm gate: the assent turn drives up to the confirm, the
    # turn suspends, and the resumed turn (which had no book_id) could not continue — measured
    # as S06 stalling at 2/5 (categories + cast land, connections/plan/chapters never do).
    book_id: str | None = None


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
    pinned_step_tools: list[str] | None = None,
    book_id: str | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO chat_suspended_runs
          (run_id, session_id, owner_user_id, message_id, working,
           pending_tool_call, input_tokens, output_tokens, model_source,
           model_ref, parent_message_id, user_message_content, permission_mode,
           pinned_step_tools, book_id)
        VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15)
        """,
        run_id, session_id, owner_user_id, message_id,
        json.dumps(working), json.dumps(pending_tool_call),
        input_tokens, output_tokens, model_source, model_ref,
        parent_message_id, user_message_content, permission_mode,
        json.dumps(list(pinned_step_tools or [])),
        book_id,
    )


def _parse_json(raw: object) -> object:
    return json.loads(raw) if isinstance(raw, str) else raw


def _str_list(raw: object) -> list[str]:
    """Defensive: a pre-WS-3 row has NULL here, and a malformed blob must not reach the
    tool surface."""
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, str) and s]


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
               permission_mode, pinned_step_tools, book_id
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
        pinned_step_tools=_str_list(_parse_json(row["pinned_step_tools"])),
        book_id=str(row["book_id"]) if row["book_id"] else None,
    )


async def load_suspended_run_any(
    pool: asyncpg.Pool, run_id: str, owner_user_id: str
) -> SuspendedRun | None:
    """DBT-CHAT-PERSIST — like `load_suspended_run` but IGNORES the TTL.

    `load_suspended_run` hides expired rows (correct: an expired card must not
    re-execute). But the trapped assistant content of an expired/abandoned run
    must still be recoverable so it can be materialized into a visible
    'interrupted' message instead of vanishing. Owner-scoped, same as the live
    loader; returns None only when the row is truly gone or another user's."""
    row = await pool.fetchrow(
        """
        SELECT run_id, session_id, owner_user_id, message_id, working,
               pending_tool_call, input_tokens, output_tokens, model_source,
               model_ref, parent_message_id, user_message_content,
               permission_mode, pinned_step_tools, book_id
        FROM chat_suspended_runs
        WHERE run_id = $1 AND owner_user_id = $2
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
        pinned_step_tools=_str_list(_parse_json(row["pinned_step_tools"])),
        book_id=str(row["book_id"]) if row["book_id"] else None,
    )


async def delete_suspended_run(pool: asyncpg.Pool, run_id: str) -> None:
    await pool.execute("DELETE FROM chat_suspended_runs WHERE run_id = $1", run_id)


async def sweep_expired_runs(pool: asyncpg.Pool, *, retention_days: int) -> int:
    """Reclaim abandoned suspended runs — **but never one whose turn is still unresolved.**

    🔴 **THIS FUNCTION SAT HERE WITH ZERO CALLERS AND A DOCSTRING SAYING IT RAN PERIODICALLY.**
    Silent exit #2. The docstring was the only evidence anyone had, and it was false, so the
    `expires_at` sweep `migrate.py` promises never happened: measured 2026-08-09, **175 of 175**
    suspended runs were past their 6-hour TTL, the oldest by 68 days.

    Two clauses, and the second is the one that matters:

    * **retention** — `expires_at` plus a window, not `expires_at` itself. A row becomes unresumable
      the instant it expires, which is the moment its *evidence* is most needed, not least;
    * 🔴 **the turn must already read as resolved.** `resolve_expired_suspends` moves a stuck
      `awaiting_input` turn to `abandoned_by_user`, and the ONLY thing that justifies it is this
      row's existence (`EXISTS (… r.expires_at <= now())`). Delete the run first and that turn keeps
      advertising a success state forever, with the fact that would have repaired it gone. **The
      hazard is an ordering, and the guard makes the ordering irrelevant** — no interleaving of the
      resolver and the sweeper can destroy a record a reader still needs, so this is a property of
      the statement rather than a convention two callers have to remember.

    "Resolved" tests BOTH columns, per F-38: a row whose `outcome` moved while `finish_reason` stayed
    at `awaiting_input` is self-contradicting, not resolved. Measured live, that is not hypothetical
    — 33 rows are in exactly that state, and this guard is what preserves them (175 expired → 142
    deletable → 33 held back).

    A run with no `chat_messages` row at all IS deletable: there is no turn to repair, and 137 of the
    175 are that shape. Returns the number swept.
    """
    if int(retention_days) < 0:
        raise ValueError("retention_days must not be negative")
    status = await pool.execute(
        "DELETE FROM chat_suspended_runs r "
        "WHERE r.expires_at <= now() - make_interval(days => $1::int) "
        "  AND NOT EXISTS ("
        "        SELECT 1 FROM chat_messages m "
        "        WHERE m.message_id = r.message_id "
        "          AND (m.outcome IS NULL OR m.finish_reason = 'awaiting_input'))",
        int(retention_days),
    )
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0
