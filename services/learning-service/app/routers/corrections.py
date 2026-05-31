"""Corrections read API — `/v1/learning/corrections*`.

STRICT per-owner isolation: every query filters on `user_id = JWT.sub`. A user
only ever sees their own corpus's corrections (cross-user → empty). No raw novel
text is exposed (redact-by-default — only structural fields + content hashes).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user, get_db
from app.models import Correction, CorrectionPage, CorrectionStats

router = APIRouter(prefix="/v1/learning", tags=["learning"])

_MAX_LIMIT = 200


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts_str, id_str = raw.rsplit("|", 1)
        return datetime.fromisoformat(ts_str), uuid.UUID(id_str)
    except (binascii.Error, ValueError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail="invalid cursor") from e


def _row_to_correction(row: asyncpg.Record) -> Correction:
    d = dict(row)
    # JSONB columns come back as str via asyncpg unless a codec is set; the
    # read path uses ::jsonb-less SELECT so they are returned as text — decode.
    import json
    for k in ("before_structural", "after_structural", "source_span"):
        v = d.get(k)
        if isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except (ValueError, TypeError):
                d[k] = None
    for k in ("id", "user_id", "project_id", "book_id", "actor_id", "source_extraction_run_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    return Correction(**d)


@router.get("/corrections", response_model=CorrectionPage)
async def list_corrections(
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
    project_id: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    diff_class: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> CorrectionPage:
    """List the caller's corrections, newest first, keyset-paginated.

    All filters are applied in SQL (no row-level post-filtering), so a simple
    peek-ahead of `limit+1` is correct — no rows-scanned/items skew."""
    where = ["user_id = $1"]
    params: list[object] = [uuid.UUID(user_id)]

    def _add(clause: str, value: object) -> None:
        params.append(value)
        where.append(clause.replace("$N", f"${len(params)}"))

    if project_id is not None:
        _add("project_id = $N", uuid.UUID(project_id))
    if target_type is not None:
        _add("target_type = $N", target_type)
    if diff_class is not None:
        _add("diff_class = $N", diff_class)
    if cursor is not None:
        c_ts, c_id = _decode_cursor(cursor)
        params.extend([c_ts, c_id])
        where.append(
            f"(created_at < ${len(params) - 1} OR "
            f"(created_at = ${len(params) - 1} AND id < ${len(params)}))"
        )

    params.append(limit + 1)  # peek-ahead
    sql = (
        "SELECT id, user_id, project_id, book_id, target_type, target_id, op, "
        "before_structural, after_structural, before_content_hash, after_content_hash, "
        "diff_class, source_extraction_run_id, source_chapter, "
        "actor_type, actor_id, origin_service, origin_event_type, emitted_at, created_at "
        "FROM corrections WHERE " + " AND ".join(where) +
        f" ORDER BY created_at DESC, id DESC LIMIT ${len(params)}"
    )
    rows = await pool.fetch(sql, *params)

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last["created_at"], last["id"])

    return CorrectionPage(
        items=[_row_to_correction(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.get("/corrections/stats", response_model=CorrectionStats)
async def correction_stats(
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
    project_id: str | None = Query(default=None),
) -> CorrectionStats:
    """Aggregate counts (by diff_class / target_type) for the caller's corpus —
    feeds the future eval-gold / few-shot tiers."""
    where = ["user_id = $1"]
    params: list[object] = [uuid.UUID(user_id)]
    if project_id is not None:
        params.append(uuid.UUID(project_id))
        where.append(f"project_id = ${len(params)}")
    clause = " AND ".join(where)

    total = await pool.fetchval(
        f"SELECT count(*) FROM corrections WHERE {clause}", *params
    )
    by_diff = await pool.fetch(
        f"SELECT coalesce(diff_class, 'other') AS k, count(*) AS n "
        f"FROM corrections WHERE {clause} GROUP BY 1", *params
    )
    by_target = await pool.fetch(
        f"SELECT target_type AS k, count(*) AS n "
        f"FROM corrections WHERE {clause} GROUP BY 1", *params
    )
    return CorrectionStats(
        total=total or 0,
        by_diff_class={r["k"]: r["n"] for r in by_diff},
        by_target_type={r["k"]: r["n"] for r in by_target},
    )
