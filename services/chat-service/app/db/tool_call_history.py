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
import re
from collections import Counter
from functools import lru_cache

import asyncpg

logger = logging.getLogger(__name__)


async def succeeded_tool_counts(pool: asyncpg.Pool, session_id: str) -> Counter:
    """How many times each tool has run SUCCESSFULLY in this session.

    A COUNT, not a set, so a rail that uses the same tool in two steps (e.g. two confirm
    gates) can tell "the first one ran" from "both ran" — a set would mark the later step
    done the moment the earlier one succeeded (a review finding)."""
    counts: Counter = Counter()
    for name in await _iter_succeeded(pool, session_id):
        counts[name] += 1
    return counts


async def succeeded_tools(pool: asyncpg.Pool, session_id: str) -> set[str]:
    """The set of tool names that have run SUCCESSFULLY at least once in this session."""
    return set(await _iter_succeeded(pool, session_id))


#: Identical failures of one tool tolerated across the session before the rail stops driving
#: the step that needs it. Mirrors chat-service's in-turn REPEATED_FAILURE_CAP so the two
#: breakers agree on what "stuck" means; kept as its own name because this one is CROSS-turn.
STUCK_TOOL_CAP = 2


def stuck_tools_from_calls(calls: "list[tuple[str, bool, str]]") -> set[str]:
    """Which tools are stuck: the same error, ``STUCK_TOOL_CAP`` times, with no success since.

    ``calls`` is the session's tool calls in order, as ``(tool, ok, error)``.

    🔴 WHY THIS IS CROSS-TURN, MEASURED 2026-08-13. chat-service already had the right RULE —
    the repeated-failure breaker keys on (tool → error → count), tolerates 2, and a success
    clears the tool's whole map. But `fail_by_tool_error` is declared inside the per-turn
    stream function, and so are the rail's own `nudge_counts`/`nudged_out`, even though the
    SDK harness documents those two as "the consumer's cross-turn state". All three reset
    every turn.

    So a step could fail twice per turn forever and neither breaker would ever fire. It did:
    session 019ff929, `plan_propose_spec` refused "not found or not accessible" 4 times across
    2 turns, the rail re-drove it to its cap each turn, and the author's actual question was
    answered three times over with the same stale apology. The rule was right; only its
    LIFETIME was wrong.

    A pure function over the call list so the rule is testable without a database, and so the
    "a success clears it" clause is visible rather than implied by a query.
    """
    fails: dict[str, dict[str, int]] = {}
    for tool, ok, error in calls:
        if not tool:
            continue
        if ok:
            # A success means the model changed something that worked — the loop is broken,
            # exactly as the in-turn breaker treats it. Clearing the whole map (not just this
            # error) is deliberate: the tool is demonstrably reachable again.
            fails.pop(tool, None)
            continue
        sig = (error or "")[:200]
        if not sig:
            # No error text is not evidence of a repeat. Counting it would let a denied or
            # gated call — which records no error — read as a wall.
            continue
        per = fails.setdefault(tool, {})
        per[sig] = per.get(sig, 0) + 1
    return {t for t, per in fails.items() if any(n >= STUCK_TOOL_CAP for n in per.values())}


async def stuck_tools(pool: asyncpg.Pool, session_id: str) -> set[str]:
    """The session's stuck tools — see `stuck_tools_from_calls` for the rule and the incident.

    Best-effort like every other reader here: a failure to read degrades to "nothing is
    stuck", which is exactly the pre-fix behaviour and can never break a turn.
    """
    return stuck_tools_from_calls(await _iter_calls(pool, session_id))


async def _iter_calls(pool: asyncpg.Pool, session_id: str) -> list[tuple[str, bool, str]]:
    """Every recorded tool call this session, in order, as ``(tool, ok, error)``.

    Deliberately unfiltered — unlike `_iter_succeeded`, whose whole point is the `ok` filter.
    The failures ARE the signal here.
    """
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
    except Exception:  # noqa: BLE001 — best-effort; never break the turn
        logger.warning("tool-call history unavailable for session=%s", session_id, exc_info=True)
        return []

    out: list[tuple[str, bool, str]] = []
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
            if isinstance(tc, dict) and tc.get("tool"):
                out.append((
                    str(tc["tool"]), bool(tc.get("ok")), str(tc.get("error") or ""),
                ))
    return out


async def _iter_succeeded(pool: asyncpg.Pool, session_id: str) -> list[str]:
    """The ordered list of successful tool names this session (one entry per success)."""
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
        return []

    out: list[str] = []
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
                out.append(str(tc["tool"]))
    return out


@lru_cache(maxsize=64)
def _uuid_under_key(key: str):
    """Compiled per key and cached — this runs on a refusal path, but the same handful of
    argument names recur, and rebuilding the pattern each time is pure waste."""
    return re.compile(
        r'"' + re.escape(key) + r'"\s*:\s*"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"'
    )


async def ids_returned_under_key(pool: asyncpg.Pool, session_id: str, key: str) -> list[str]:
    """Every DISTINCT uuid a SUCCESSFUL tool call in this SESSION returned under `key`.

    🔴 THE SESSION, NOT THE TURN, and that distinction is the entire reason this exists.
    A first attempt at D-THE-OWED-REFUSAL-DENIES-AN-ID-THE-MODEL-WAS-JUST-HANDED scanned the
    turn's own message list for role="tool" entries. Those exist only WITHIN a turn: chat_messages
    holds ZERO role='tool' rows — a tool result is stored on the ASSISTANT row, in this very
    column. So the scan found nothing across turns and the new branch fired 0 times in 10 live
    runs, on a defect whose recorded instance spans exactly two turns.

    `ok` only, for the reason this module's docstring already gives: a failed call has not handed
    anything over, and quoting a value out of a failure would be worse than saying nothing.

    Returns EVERY distinct value so the caller can refuse to speak when there is more than one —
    a session holding two runs makes "the" id a fabrication.

    ⚠️ NOT built on `_iter_calls`: that yields ``(tool, ok, ERROR)`` — the failure text, which is
    the opposite of what is wanted here. Reading the rows directly is the only way to reach
    ``result``.
    """
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
    except Exception:  # noqa: BLE001 — a refusal's wording must never take the turn down
        logger.warning("tool-call history unavailable for session=%s", session_id, exc_info=True)
        return []

    pat = _uuid_under_key(key)
    out: list[str] = []
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
            if not isinstance(tc, dict) or not tc.get("ok"):
                continue
            res = tc.get("result")
            if res is None:
                continue
            for v in pat.findall(res if isinstance(res, str) else json.dumps(res)):
                if v not in out:
                    out.append(v)
    return out


# ── DQ-T88 (a) WITH A CEILING — replaying prior turns' tool RESULTS ──────────────────────────
#
# OWNER 2026-09-01: "try claude code idea" — replay tool results across turns, in the shape the
# Messages API uses, where a result is a content block in the transcript and survives to the next
# turn by construction. THEN THE OWNER CORRECTED THE BUILD, and the correction is why the caps
# below exist: "i don't think problem only come from resent or store but the tool return so much
# data and it cause context bloated, that why the tool result is not store".
#
# That account is causal in the opposite direction to the one I had: results are not stored
# BECAUSE they are large, so replaying them unbounded relocates the problem into every turn.
# MEASURED over 5,182 sessions that made a tool call:
#     average tool_calls bytes per session   10,346      (author+assistant PROSE: 1,759)
#     median                                  3,270
#     p95                                    38,369
#     MAX                                   890,805
# The replay is ~6x everything anyone actually said, and the tail is nearly a megabyte. So a
# trimmed projection is not a refinement of the ruling — it is the only affordable form of it,
# which is what "(a) WITH A CEILING" means.
#
# AND THE COST IS CONCENTRATED, which is what makes a per-result cap effective rather than
# arbitrary: FIVE tools are 64.6% of all result bytes (tool_list 21.4%, glossary_book_ontology_read
# 20.1%, glossary_list_system_standards 10.0%, glossary_task_provide_input 7.9%, world_list 5.2%).

#: Bytes of a single result carried verbatim before it is projected. Chosen from the measured
#: distribution, not by taste: the per-session MEDIAN is 3,270 bytes across ALL of a session's
#: calls, so 2 kB per result leaves a typical session untouched while the p95/max tail — which is
#: one or two enormous results, never many small ones — is projected.
#: Any uuid in a result body. Used ONLY to preserve ids when a result is projected — an id is the
#: one thing a later turn cannot re-derive from a trimmed payload.
_ANY_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

REPLAY_RESULT_CAP = 2_048

#: Total bytes of replayed results per turn. p95 of a whole session is 38 kB, so 16 kB admits the
#: great majority of sessions whole and bounds the 890 kB worst case at ~2% of itself.
REPLAY_SESSION_BUDGET = 16_384


def project_result(tool: str, result, cap: int = REPLAY_RESULT_CAP) -> str:
    """A result small enough to replay, preserving what the next turn actually needs.

    🔴 WHAT IS PRESERVED IS NOT THE PREFIX. Truncating to the first N bytes keeps the opening
    brace and loses the ids, and an id is the one thing a later turn cannot re-derive — it is the
    whole subject of the fabricated-id work. So an oversized result keeps every uuid it returned
    and says what was dropped, rather than keeping a readable head and a useless tail.

    A result that already fits is returned unchanged: the common case must cost nothing.
    """
    blob = result if isinstance(result, str) else json.dumps(result, default=str)
    if len(blob) <= cap:
        return blob
    ids: list[str] = []
    for v in _ANY_UUID.findall(blob):
        if v not in ids:
            ids.append(v)
    # 🔴 THE NOTE IS BUILT FIRST AND THE HEAD IS SIZED TO WHAT IS LEFT. A first version reserved
    # a fixed 240 bytes for it and appended afterwards, which OVERSHOT the cap whenever a result
    # carried many ids — measured at 2,416 bytes against a 2,048 cap, on the very payload shape
    # (an ontology read) that made the cap necessary. A ceiling that the worst case walks through
    # is not a ceiling, and the whole point of this function is that the caller can trust `cap`.
    note = (f'… [{tool}: {len(blob)} bytes, trimmed to fit the turn. '
            f'{len(ids)} id(s) returned: {", ".join(ids[:12])}'
            f'{" …" if len(ids) > 12 else ""}. '
            f'Call {tool} again if you need the rest.]')
    if len(note) >= cap:
        # Pathological: more ids than the cap can hold. The IDS are what matter, so keep the note
        # and drop the body entirely rather than returning a head with no explanation.
        return note[:cap]
    return blob[: cap - len(note)] + note


async def results_for_replay(
    pool: "asyncpg.Pool", session_id: str, *,
    budget: int = REPLAY_SESSION_BUDGET, cap: int = REPLAY_RESULT_CAP,
) -> list[dict]:
    """Prior turns' SUCCESSFUL tool results, newest first, within a byte budget.

    NEWEST FIRST is the retention rule and it is deliberate: when the budget binds, the results a
    turn is most likely to need are the ones it just produced. The list is returned in
    chronological order so a caller can append it as transcript.

    `ok` only — a failed call handed nothing over, and replaying its error text would re-teach the
    model a wall it already hit (the repeated-failure breaker is the mechanism for that, and it
    works on THIS turn's evidence).
    """
    try:
        rows = await pool.fetch(
            """
            SELECT tool_calls
              FROM chat_messages
             WHERE session_id = $1::uuid
               AND tool_calls IS NOT NULL
             ORDER BY sequence_num DESC
            """,
            session_id,
        )
    except Exception:  # noqa: BLE001 — replay is an enrichment; a turn must never die for it
        logger.warning("replay history unavailable for session=%s", session_id, exc_info=True)
        return []

    out: list[dict] = []
    spent = 0
    for r in rows:
        raw = r["tool_calls"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                continue
        if not isinstance(raw, list):
            continue
        for tc in reversed(raw):
            if not isinstance(tc, dict) or not tc.get("ok") or tc.get("result") is None:
                continue
            tool = str(tc.get("tool") or "")
            body = project_result(tool, tc.get("result"), cap)
            if spent + len(body) > budget:
                return list(reversed(out))
            spent += len(body)
            out.append({"tool": tool, "id": tc.get("id"), "result": body})
    return list(reversed(out))
