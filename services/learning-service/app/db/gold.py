"""Gold-label projection over the corrections log (track phase Q2).

A user correction is a triple signal — the user's ``after`` is *preferred* over
the extractor's ``before`` (preference), ``after`` is the supervised target
(supervision), and the edit magnitude is a reward signal. This projects the
redact-by-default corrections log into that shape so the judge-calibration gate
(Q3.5) and the eval-case dataset (Q5) can consume human corrections as gold.

Both correction routes converge here: ``knowledge.{entity,relation,event}_corrected``
(origin_service='knowledge', may carry source_extraction_run_id) and
``glossary.entity_updated`` (origin_service='glossary', always target_type=entity,
source run NULL). ``origin_service`` is surfaced so consumers can tell them apart;
no cross-route dedup yet (volume is tiny — deferred to Q5 when it matters).

Structural + content-hash only (no raw novel text) — inherited from corrections.
Strict per-owner isolation: every query filters on ``user_id``.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


def _unjson(value: Any) -> Any:
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value


def _change_magnitude(before: Any, after: Any) -> int:
    """Number of top-level structural keys that differ between before/after.

    A create (before is None) counts the keys introduced; a delete (after None)
    counts the keys removed; an edit counts the changed/added/removed keys.
    """
    b = before if isinstance(before, dict) else {}
    a = after if isinstance(after, dict) else {}
    keys = set(b) | set(a)
    return sum(1 for k in keys if b.get(k) != a.get(k))


def _project(row: asyncpg.Record) -> dict:
    d = dict(row)
    before = _unjson(d.get("before_structural"))
    after = _unjson(d.get("after_structural"))
    return {
        "target_type": d["target_type"],
        "target_id": d["target_id"],
        "op": d["op"],
        "diff_class": d.get("diff_class"),
        "non_preferred": before,  # the extractor's original output
        "preferred": after,        # the user's correction (the gold target)
        "before_content_hash": d.get("before_content_hash"),
        "after_content_hash": d.get("after_content_hash"),
        "change_magnitude": _change_magnitude(before, after),
        "source_chapter": d.get("source_chapter"),
        "source_extraction_run_id": (
            str(d["source_extraction_run_id"])
            if d.get("source_extraction_run_id") is not None
            else None
        ),
        "origin_service": d["origin_service"],
        "created_at": d["created_at"],
    }


async def get_gold_labels(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    target_type: str | None = None,
    diff_class: str | None = None,
    exclude_noop: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Project the caller's corrections into gold-label triples, newest first.

    ``exclude_noop`` drops corrections where the content hash is unchanged AND
    the structural snapshot is identical (no signal). ``create`` ops are kept —
    a user-added item the extractor missed is a recall gold (before = absent).
    """
    where = ["user_id = $1", "actor_type = 'user'"]
    params: list[Any] = [user_id]

    def _add(clause: str, value: Any) -> None:
        params.append(value)
        where.append(clause.replace("$N", f"${len(params)}"))

    if project_id is not None:
        _add("project_id = $N", project_id)
    if target_type is not None:
        _add("target_type = $N", target_type)
    if diff_class is not None:
        _add("diff_class = $N", diff_class)
    if exclude_noop:
        # A pure no-op = identical content hash AND identical structural. Keep
        # rows where EITHER differs (an edit), and always keep create/delete
        # (one side NULL).
        where.append(
            "(before_content_hash IS DISTINCT FROM after_content_hash "
            "OR before_structural IS DISTINCT FROM after_structural)"
        )

    clause = " AND ".join(where)
    count_sql = f"SELECT count(*) FROM corrections WHERE {clause}"

    params.append(limit)
    params.append(offset)
    data_sql = (
        "SELECT target_type, target_id, op, diff_class, "
        "before_structural, after_structural, before_content_hash, after_content_hash, "
        "source_chapter, source_extraction_run_id, origin_service, created_at "
        f"FROM corrections WHERE {clause} "
        f"ORDER BY created_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}"
    )

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_sql, *params[:-2])
        rows = await conn.fetch(data_sql, *params)
    return {"items": [_project(r) for r in rows], "total": total or 0}
