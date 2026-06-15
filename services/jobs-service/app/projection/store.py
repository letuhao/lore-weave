"""The projection store — the only writer of `job_projection`.

`upsert_job_event` applies ONE inbound `JobEvent` to the mirror. It is the
correctness core of P2: events arrive at-least-once and can be REORDERED
(redelivery, the XAUTOCLAIM reclaim, the reconcile sweep racing the live
stream), so the upsert must be **idempotent + monotonic**:

  - a terminal status (completed/failed/cancelled) always wins over a
    non-terminal one — a completed job is never resurrected to "running" by a
    late-arriving running event;
  - among non-terminal events, a newer `occurred_at` wins (forward-only);
  - among terminal events, a newer `occurred_at` wins (a cancelled-then-completed
    race resolves to whichever the producer stamped later — both terminal, no
    resurrection either way).

`job_id` is UUID-coercible (the emit contract guarantees it). `occurred_at` is
the event's stamp; the consumer always supplies one (emit defaults it to now()).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Optional

from loreweave_jobs import JobEvent

# Monotonic upsert. The ON CONFLICT WHERE clause encodes the ordering rules above
# so an out-of-order / replayed event can never regress the row.
_UPSERT = """
INSERT INTO job_projection (
  service, job_id, owner_user_id, kind, status, parent_job_id,
  detail_status, progress, title, error, job_created_at, job_updated_at
) VALUES (
  $1, $2::uuid, $3::uuid, $4, $5, $6::uuid,
  $7, $8::jsonb, $9, $10::jsonb, $11::timestamptz, $11::timestamptz
)
ON CONFLICT (service, job_id) DO UPDATE SET
  status         = EXCLUDED.status,
  owner_user_id  = EXCLUDED.owner_user_id,
  kind           = EXCLUDED.kind,
  parent_job_id  = COALESCE(EXCLUDED.parent_job_id, job_projection.parent_job_id),
  detail_status  = EXCLUDED.detail_status,
  progress       = COALESCE(EXCLUDED.progress, job_projection.progress),
  title          = COALESCE(EXCLUDED.title, job_projection.title),
  error          = EXCLUDED.error,
  job_created_at = LEAST(job_projection.job_created_at, EXCLUDED.job_created_at),
  job_updated_at = EXCLUDED.job_updated_at,
  projected_at   = now()
WHERE
  -- terminal incoming: always apply, UNLESS it is an OLDER terminal landing on a
  -- newer terminal (don't let a stale cancelled clobber a later completed).
  ( EXCLUDED.status IN ('completed','failed','cancelled')
    AND NOT ( job_projection.status IN ('completed','failed','cancelled')
              AND EXCLUDED.job_updated_at < job_projection.job_updated_at ) )
  OR
  -- non-terminal incoming: only over a non-terminal current row, and only forward
  -- in time (>= so an equal-stamp replay of the same status is a harmless no-op write).
  ( EXCLUDED.status NOT IN ('completed','failed','cancelled')
    AND job_projection.status NOT IN ('completed','failed','cancelled')
    AND EXCLUDED.job_updated_at >= job_projection.job_updated_at )
"""


def _jsonb(value: Any) -> Optional[str]:
    """asyncpg needs a str for a ::jsonb cast (None passes through as SQL NULL)."""
    if value is None:
        return None
    return json.dumps(value)


def _ts(value: Any) -> datetime:
    """Coerce an ISO-8601 string (the event's occurred_at) to a tz-aware
    datetime. asyncpg binds a timestamptz param as a datetime, NOT a str (a raw
    str → "expected a datetime instance" — caught in the M3 live-smoke). Missing
    /unparseable → now() so the NOT NULL job_updated_at column is always set."""
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


async def upsert_job_event(conn: Any, event: JobEvent) -> bool:
    """Apply one `JobEvent` to the projection (idempotent + monotonic). `conn` is
    an asyncpg pool or connection (anything with `execute`).

    Returns True if the row was actually written (inserted or a monotonic-forward
    update), False if the monotonic WHERE skipped it (a stale/older/duplicate
    event). The consumer uses this to suppress an SSE push for a no-op — so a
    redelivered `running` after `completed` never flips the GUI to a stale state.
    """
    status_value = event.status.value if hasattr(event.status, "value") else str(event.status)
    tag = await conn.execute(
        _UPSERT,
        event.service,
        str(event.job_id),
        str(event.owner_user_id),
        event.kind,
        status_value,
        str(event.parent_job_id) if event.parent_job_id else None,
        event.detail_status,
        _jsonb(event.progress),
        event.title,
        _jsonb(event.error),
        _ts(event.occurred_at),
    )
    # asyncpg command tag: "INSERT 0 1" (applied) / "INSERT 0 0" (WHERE-skipped).
    # A mock pool may return a non-tag (e.g. an AsyncMock) — treat that as applied.
    try:
        return int(str(tag).split()[-1]) > 0
    except (ValueError, IndexError, AttributeError):
        return True


# ── read side (M2) ────────────────────────────────────────────────────────────
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Columns returned to the API (control_caps are derived at the router layer).
_COLS = (
    "service, job_id, owner_user_id, kind, status, parent_job_id, detail_status, "
    "progress, title, error, job_created_at, job_updated_at"
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """asyncpg.Record → JSON-safe dict. progress/error are jsonb (asyncpg returns
    them as str when the column type is jsonb without a codec) — normalize to dict."""
    def _json(v: Any) -> Any:
        if v is None or isinstance(v, (dict, list)):
            return v
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return None

    created = row["job_created_at"]
    updated = row["job_updated_at"]
    return {
        "service": row["service"],
        "job_id": str(row["job_id"]),
        "owner_user_id": str(row["owner_user_id"]),
        "kind": row["kind"],
        "status": row["status"],
        "parent_job_id": str(row["parent_job_id"]) if row["parent_job_id"] else None,
        "detail_status": row["detail_status"],
        "progress": _json(row["progress"]),
        "title": row["title"],
        "error": _json(row["error"]),
        "created_at": created.isoformat() if created else None,
        "updated_at": updated.isoformat() if updated else None,
        "child_count": int(row["child_count"]) if "child_count" in row and row["child_count"] is not None else None,
    }


def _encode_cursor(row: dict[str, Any]) -> str:
    raw = f"{row['updated_at']}|{row['service']}|{row['job_id']}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> Optional[tuple[str, str, str]]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, service, job_id = raw.split("|", 2)
        return ts, service, job_id
    except (ValueError, TypeError):
        return None


async def list_jobs(
    conn: Any,
    owner_user_id: str,
    *,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    parent: Optional[str] = None,
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """A user's jobs, most-recently-updated first. Owner-scoped (security).

    Default (no `parent`): TOP-LEVEL jobs only (parent_job_id IS NULL) each with a
    `child_count` — the GUI shows a campaign once + lazy-loads its children via
    `?parent=<job_id>` (H3 grouping, pagination never splits a family). `?parent`
    returns that parent's children. Keyset cursor on (job_updated_at, service,
    job_id) DESC — stable + no offset drift. Returns (rows, next_cursor)."""
    limit = max(1, min(limit, MAX_LIMIT))
    where = ["j.owner_user_id = $1::uuid"]
    args: list[Any] = [owner_user_id]

    if parent:
        args.append(parent)
        where.append(f"j.parent_job_id = ${len(args)}::uuid")
    else:
        where.append("j.parent_job_id IS NULL")
    if status:
        args.append(status)
        where.append(f"j.status = ${len(args)}")
    if kind:
        args.append(kind)
        where.append(f"j.kind = ${len(args)}")
    if q:
        args.append(f"%{q}%")
        where.append(f"j.title ILIKE ${len(args)}")
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            ts, c_service, c_job = decoded
            # ts is the ISO str off the cursor — asyncpg rejects a str for a
            # ::timestamptz param (same trap as upsert), so coerce to datetime.
            args.extend([_ts(ts), c_service, c_job])
            n = len(args)
            where.append(
                f"(j.job_updated_at, j.service, j.job_id) "
                f"< (${n-2}::timestamptz, ${n-1}, ${n}::uuid)"
            )

    # child_count: only meaningful for the top-level view; a child row's children
    # (none in practice — the tree is 1 level) still computes harmlessly.
    child_count_expr = (
        "(SELECT count(*) FROM job_projection c "
        " WHERE c.parent_job_id = j.job_id AND c.owner_user_id = j.owner_user_id)"
    )
    args.append(limit + 1)  # fetch one extra to know if there's a next page
    sql = (
        f"SELECT {', '.join('j.' + c for c in _COLS.split(', '))}, "
        f"{child_count_expr} AS child_count "
        f"FROM job_projection j WHERE {' AND '.join(where)} "
        f"ORDER BY j.job_updated_at DESC, j.service DESC, j.job_id DESC "
        f"LIMIT ${len(args)}"
    )
    rows = await conn.fetch(sql, *args)
    items = [_row_to_dict(r) for r in rows]
    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        next_cursor = _encode_cursor(items[-1])
    return items, next_cursor


async def get_job(conn: Any, owner_user_id: str, service: str, job_id: str) -> Optional[dict[str, Any]]:
    """One job's detail, owner-scoped. Returns None if not found OR not owned
    (the router maps None → 404, an anti-oracle — never reveal another user's job)."""
    child_count_expr = (
        "(SELECT count(*) FROM job_projection c "
        " WHERE c.parent_job_id = j.job_id AND c.owner_user_id = j.owner_user_id)"
    )
    row = await conn.fetchrow(
        f"SELECT {', '.join('j.' + c for c in _COLS.split(', '))}, "
        f"{child_count_expr} AS child_count "
        f"FROM job_projection j "
        f"WHERE j.service = $1 AND j.job_id = $2::uuid AND j.owner_user_id = $3::uuid",
        service, job_id, owner_user_id,
    )
    return _row_to_dict(row) if row else None
