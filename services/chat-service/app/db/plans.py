"""CP-3.1 · the plan, made durable. **One live plan per session; STATE is append-only.**

§0.11's storage clause. This module is the ONLY writer of `chat_plans` and `chat_plan_events`, and
the direction of dependency matters: `app.db` imports `app.agentruntime`, never the reverse. The
membrane gate enforces that the package imports nothing but stdlib and itself, so the plan mechanism
cannot acquire a database — it stays a pure function of its inputs and this file carries the effects.

🔴 **WHY A ROUND-TRIP AND NOT A PICKLE.** `Spec` is frozen and validating: rebuilding one from JSON
re-runs `check_bindings`, so a row edited in the database is refused on the way OUT, exactly as a
hand-typed manifest row is. Serialising the object graph would skip every clause and hand the
executor a plan nothing checked — which is the shape §6.1 layer 3 exists to refuse at the other
boundary.
"""
from __future__ import annotations

import json
from types import MappingProxyType

import asyncpg

from app.agentruntime.plan import Binding, Event, Spec, State, Step, Termination


def _spec_to_json(spec: Spec) -> str:
    return json.dumps({
        "goal": spec.goal,
        "done_when": spec.done_when,
        "template_id": spec.template_id,
        "template_version": spec.template_version,
        "replan_budget": spec.replan_budget,
        "version": spec.version,
        "steps": [{
            "declaration": s.declaration,
            "contract_version": s.contract_version,
            "emits": list(s.emits),
            "done_when": s.done_when,
            "gated": s.gated,
            "accepts": {k: {"from_step": b.from_step, "from_emit": b.from_emit,
                            "literal": b.literal} for k, b in s.accepts.items()},
        } for s in spec.steps],
    }, ensure_ascii=False)


def _spec_from_json(raw) -> Spec:
    """Rebuild through the real constructors, so every clause runs again on the way out."""
    d = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    steps = tuple(
        Step(
            declaration=s["declaration"],
            contract_version=s["contract_version"],
            accepts=MappingProxyType({
                k: Binding(from_step=b["from_step"], from_emit=b["from_emit"],
                           literal=b["literal"])
                for k, b in (s.get("accepts") or {}).items()
            }),
            emits=tuple(s.get("emits") or ()),
            done_when=s.get("done_when", ""),
            gated=bool(s.get("gated")),
        )
        for s in d["steps"]
    )
    return Spec(
        goal=d["goal"], steps=steps, done_when=d.get("done_when", ""),
        template_id=d.get("template_id", ""), template_version=d.get("template_version", ""),
        replan_budget=d.get("replan_budget", 3), version=d.get("version", 1),
    )


async def save_spec(conn: asyncpg.Connection, session_id, spec: Spec) -> str:
    """Persist a SPEC as this session's live plan, superseding whatever was live.

    🔴 **THE SUPERSEDE AND THE INSERT ARE ONE STATEMENT PAIR IN ONE TRANSACTION**, because the
    partial unique index means a gap between them is not a race that produces two live plans — it is
    a race that produces an INSERT failure under concurrency. Both orders are safe with the index;
    doing it in a transaction is what makes the failure atomic rather than leaving a session with no
    live plan at all after a partial write.

    A revision is a NEW VERSION, never an UPDATE: the old row stays readable so §0.8's
    approval-invalidation can be inspected after the fact rather than reconstructed from memory.
    """
    async with conn.transaction():
        await conn.execute(
            "UPDATE chat_plans SET status = 'superseded' "
            "WHERE session_id = $1 AND status = 'live'",
            session_id,
        )
        row = await conn.fetchrow(
            "INSERT INTO chat_plans "
            "  (session_id, version, spec_hash, gated_hash, spec, status) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, 'live') "
            "RETURNING plan_id",
            session_id, spec.version, spec.hashed(), spec.gated_hash(), _spec_to_json(spec),
        )
    return str(row["plan_id"])


async def append_event(conn: asyncpg.Connection, plan_id, event: Event) -> int:
    """Append one fact. Returns its sequence number.

    `seq` is allocated from the plan's own history rather than from a global sequence, so a replay
    reads positions that mean something within the plan. The `(plan_id, seq)` primary key turns a
    duplicate — the shape a retry produces — into a constraint violation instead of a silent
    overwrite of somebody else's fact.
    """
    if type(event) is not Event:
        raise TypeError(
            f"{type(event).__name__} is not an Event. STATE is the record recovery replays; a duck "
            f"type here is a fact nobody validated.")
    async with conn.transaction():
        # 🔴 **TWO CONCURRENT APPENDS COMPUTE THE SAME `seq` AND ONE OF THEM FAILS.** That is the
        # intended behaviour and it is why the primary key carries the invariant: the alternative —
        # a sequence that always succeeds — would let a second writer interleave into a history the
        # executor is supposed to own alone (§0.11: *"the executor is the only writer of STATE"*).
        # A `UniqueViolationError` here means someone else wrote; retrying blindly would append the
        # fact twice, so the caller is told rather than helped.
        seq = await conn.fetchval(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM chat_plan_events WHERE plan_id = $1", plan_id)
        await conn.execute(
            "INSERT INTO chat_plan_events "
            "  (plan_id, seq, kind, step_index, payload, error_class, undo_hint, committed) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)",
            plan_id, seq, event.kind, event.step_index,
            json.dumps(dict(event.values), ensure_ascii=False),
            event.error_class, event.undo_hint, event.committed,
        )
    return int(seq)


async def load_live(conn: asyncpg.Connection, session_id):
    """This session's live plan as `(plan_id, Spec, State)`, or None.

    The `State` is **replayed** from the event rows, which is the whole point of storing them: the
    identifiers a later step binds to come back exactly as they were recorded, where the
    conversation would have evicted them.
    """
    row = await conn.fetchrow(
        "SELECT plan_id, spec, spec_hash FROM chat_plans "
        "WHERE session_id = $1 AND status = 'live'",
        session_id,
    )
    if row is None:
        return None
    spec = _spec_from_json(row["spec"])
    # 🔴 The STORED hash, not a fresh one. If the code's hash of this spec has moved, that is a
    # finding about an approval that was bound to the old value — surfacing it belongs to the caller,
    # and silently re-binding here is exactly §0.8's laundering.
    state = State(row["spec_hash"])
    events = await conn.fetch(
        "SELECT kind, step_index, payload, error_class, undo_hint, committed "
        "FROM chat_plan_events WHERE plan_id = $1 ORDER BY seq ASC",
        row["plan_id"],
    )
    for e in events:
        payload = e["payload"]
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
        state.append(Event(
            kind=e["kind"], step_index=e["step_index"],
            values=MappingProxyType(dict(payload or {})),
            error_class=e["error_class"], undo_hint=e["undo_hint"], committed=e["committed"],
        ))
    return str(row["plan_id"]), spec, state


async def record_termination(conn: asyncpg.Connection, plan_id, term: Termination) -> None:
    """Close the plan. §3: the scope and the hand-off are COLUMNS, so a person can query for them.

    Exits #2 and #4 went silent by recording a status somewhere nobody looked. `terminal_scope` and
    `hand_to_human` are on the row that a session's plan lookup already reads.
    """
    if type(term) is not Termination:
        raise TypeError(f"{type(term).__name__} is not a Termination")
    await conn.execute(
        "UPDATE chat_plans SET status = 'terminated', terminal_scope = $2, hand_to_human = $3 "
        "WHERE plan_id = $1",
        plan_id, term.scope, term.hand_to_human,
    )


async def live_plan_id(conn: asyncpg.Connection, session_id):
    """S3-M4 — *is there a live plan for this session?* A second message routes INTO it."""
    return await conn.fetchval(
        "SELECT plan_id FROM chat_plans WHERE session_id = $1 AND status = 'live'", session_id)
