"""`intent_run` / `intent_slot_record` persistence — thin asyncpg, owner-scoped everywhere.

The `transition` shape is lifted from `glossary_build/service.py`: an OPTIMISTIC update that names
the states it is willing to move from and returns ``None`` when the row is not in one of them. That
`None` is the 409, and it is what makes a double-click, a double-delivered event, or two devices
unable to advance the same run twice — without a lock, and without the FSM having to read-then-write.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

_JSONB_FIELDS = ("slot_plan", "candidates", "params", "verdicts")


def _row(record) -> dict | None:
    """Decode jsonb ONCE at the repo boundary.

    No jsonb codec is registered on this pool, so asyncpg hands these back as TEXT. Decoding here
    means nothing downstream has to guess whether a field is a str or a dict — the exact drift that
    made a glossary-build bug visible only against real Postgres, never against the dict-storing
    fake.
    """
    if record is None:
        return None
    out = dict(record)
    for k in _JSONB_FIELDS:
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except ValueError:
                pass
    return out


class IntentRepo:
    def __init__(self, pool) -> None:
        self._pool = pool

    # ── runs ────────────────────────────────────────────────────────────────────────────────────
    async def create_run(self, *, owner: UUID, book_id: UUID, project_id: UUID, node_id: UUID,
                         slot_plan: list[str], params: dict) -> dict:
        row = await self._pool.fetchrow(
            """INSERT INTO intent_run
                 (owner_user_id, book_id, project_id, node_id, slot_plan, slot_cursor, params)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb)
               RETURNING *""",
            owner, book_id, project_id, node_id,
            json.dumps(slot_plan), slot_plan[0] if slot_plan else None, json.dumps(params),
        )
        return _row(row)

    async def get_run(self, run_id: UUID, owner: UUID) -> dict | None:
        return _row(await self._pool.fetchrow(
            "SELECT * FROM intent_run WHERE run_id=$1 AND owner_user_id=$2", run_id, owner,
        ))

    async def active_for_node(self, node_id: UUID, owner: UUID) -> dict | None:
        return _row(await self._pool.fetchrow(
            """SELECT * FROM intent_run
               WHERE node_id=$1 AND owner_user_id=$2
                 AND status NOT IN ('done','cancelled','failed')""",
            node_id, owner,
        ))

    async def list_runs(self, *, owner: UUID, book_id: UUID, limit: int = 20) -> list[dict]:
        rows = await self._pool.fetch(
            """SELECT * FROM intent_run WHERE owner_user_id=$1 AND book_id=$2
               ORDER BY created_at DESC LIMIT $3""",
            owner, book_id, limit,
        )
        return [_row(r) for r in rows]

    async def transition(self, run_id: UUID, owner: UUID, from_status: list[str],
                         to_status: str, **fields: Any) -> dict | None:
        """Optimistic transition — ``None`` when the run is not in `from_status` (→ 409)."""
        sets, args = ["status=$3", "updated_at=now()"], [run_id, owner, to_status]
        for k, v in fields.items():
            args.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
            cast = "::jsonb" if isinstance(v, (dict, list)) else ""
            sets.append(f"{k}=${len(args)}{cast}")
        return _row(await self._pool.fetchrow(
            f"""UPDATE intent_run SET {', '.join(sets)}
                WHERE run_id=$1 AND owner_user_id=$2 AND status = ANY(${len(args) + 1}::text[])
                RETURNING *""",
            *args, from_status,
        ))

    # ── the instrument ──────────────────────────────────────────────────────────────────────────
    async def record_slot(self, run: dict, *, slot: str, position: int, constraint_class: str,
                          outcome: str, candidates: list | None = None,
                          author_value: str | None = None, applied_value: str | None = None,
                          llm_calls: int = 0, retried: bool = False) -> dict:
        """Upsert the instrument row for one slot (spec §8).

        UPSERT rather than INSERT because a slot is visited more than once in the ordinary case: a
        `proposal_failed` that the author retries, or a re-proposal after a decline. The row records
        how the slot ENDED, and `llm_calls` accumulates across those visits — reporting only the
        last attempt's cost would under-count exactly the runs that cost the most.
        """
        return _row(await self._pool.fetchrow(
            """INSERT INTO intent_slot_record
                 (run_id, owner_user_id, book_id, node_id, slot, position, constraint_class, arm,
                  candidates, author_value, applied_value, outcome, llm_calls, retried)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14)
               ON CONFLICT ON CONSTRAINT uq_intent_slot_record DO UPDATE SET
                 constraint_class = EXCLUDED.constraint_class,
                 candidates       = EXCLUDED.candidates,
                 author_value     = EXCLUDED.author_value,
                 applied_value    = EXCLUDED.applied_value,
                 outcome          = EXCLUDED.outcome,
                 llm_calls        = intent_slot_record.llm_calls + EXCLUDED.llm_calls,
                 retried          = intent_slot_record.retried OR EXCLUDED.retried,
                 updated_at       = now()
               RETURNING *""",
            run["run_id"], run["owner_user_id"], run["book_id"], run["node_id"],
            slot, position, constraint_class, (run.get("params") or {}).get("arm", "constrained_first"),
            json.dumps(candidates or []), author_value, applied_value, outcome,
            llm_calls, retried,
        ))

    async def list_records(self, run_id: UUID, owner: UUID) -> list[dict]:
        rows = await self._pool.fetch(
            """SELECT * FROM intent_slot_record WHERE run_id=$1 AND owner_user_id=$2
               ORDER BY position""",
            run_id, owner,
        )
        return [_row(r) for r in rows]

    async def set_verdicts(self, run_id: UUID, owner: UUID, slot: str,
                           verdicts: list[dict]) -> dict | None:
        """Metric A — scored by the AUTHOR, never by a judge model (spec §8)."""
        return _row(await self._pool.fetchrow(
            """UPDATE intent_slot_record SET verdicts=$4::jsonb, updated_at=now()
               WHERE run_id=$1 AND owner_user_id=$2 AND slot=$3 RETURNING *""",
            run_id, owner, slot, json.dumps(verdicts),
        ))
