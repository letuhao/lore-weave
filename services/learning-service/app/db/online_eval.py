"""Online structural eval (track phase Q4).

Online eval of a PRODUCTION extraction run has no gold and no source text, so the
golden-set P/R/F1 harness does not apply (PO-locked: structural-only first; the
LLM-judge path is Q4b, gated on ``save_raw_extraction``). The signal here is a
cheap structural-health score from the run's own metrics — it flags a run that
produced degenerate output (e.g. 0 relations) without needing source or gold,
catching pipeline-health regressions online.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

import asyncpg

from app.db.eval_repo import _load_score_configs, _validate_score

_CORE_CATEGORIES = ("entities_merged", "relations_created", "events_merged")
_METRIC = "online_structural_completeness"
_DEFAULT_RULE_NAME = "global-structural-default"


def structural_completeness(metrics: dict | None) -> float:
    """Fraction of the core categories (entity / relation / event) that produced
    at least one item. 1.0 = full yield across all three; 0.0 = degenerate or
    broken run. Facts are excluded (writer-autocreate-gated, optional)."""
    m = metrics or {}
    produced = sum(1 for k in _CORE_CATEGORIES if (m.get(k) or 0) > 0)
    return produced / len(_CORE_CATEGORIES)


def should_sample(run_id: str, sampling_rate: float) -> bool:
    """Deterministic sampling — the SAME ``run_id`` always yields the same
    decision, so a re-delivered event re-samples identically (idempotent with
    the ``online:<run_id>`` eval-run key). ``hash(run_id) mod 10000 < rate*10000``."""
    if sampling_rate >= 1.0:
        return True
    if sampling_rate <= 0.0:
        return False
    h = int(hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) < int(sampling_rate * 10000)


async def ensure_default_online_eval_rule(pool: asyncpg.Pool) -> None:
    """Seed the global structural-only default rule (idempotent, boot-time)."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO online_eval_rule (user_id, name, sampling_rate, judge_panel_id, enabled)
            VALUES (NULL, $1, 0.1, NULL, true)
            ON CONFLICT (name) DO NOTHING
            """,
            _DEFAULT_RULE_NAME,
        )


async def get_active_rule(pool: asyncpg.Pool) -> dict | None:
    """The active GLOBAL rule (Q4a uses one global rule; per-user / per-filter
    rules + the LLM-judge panel are Q4b). None when disabled/absent — the
    consumer then samples nothing (XACKs everything)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT rule_id, sampling_rate, judge_panel_id, enabled "
            "FROM online_eval_rule WHERE user_id IS NULL AND enabled = true "
            "ORDER BY created_at LIMIT 1"
        )
    return dict(row) if row else None


async def persist_online_eval(
    pool: asyncpg.Pool,
    *,
    run_id: str,
    user_id: UUID,
    project_id: UUID | None = None,
    book_id: UUID | None = None,
    config_hash: str | None = None,
    completeness: float,
    origin_event_id: str | None = None,
) -> UUID:
    """Persist a structural online eval: one ``eval_runs`` row (``source='online'``,
    idempotent on ``online:<run_id>``) + a validated ``quality_scores`` row.
    Re-sampling the same run updates in place (no duplicate)."""
    idem = f"online:{run_id}"
    source_run = UUID(str(run_id))
    async with pool.acquire() as conn:
        cfgs = await _load_score_configs(conn)
        data_type = _validate_score(cfgs, _METRIC, completeness, None)  # raises if bad
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO eval_runs (
                  user_id, project_id, book_id, source_extraction_run_id, config_hash,
                  source, judges, n_chapters, idempotency_key, origin_service,
                  origin_event_id, panel_safe, panel_safety_reason
                ) VALUES (
                  $1, $2, $3, $4, $5, 'online', '[]'::jsonb, 1, $6, 'knowledge',
                  $7, TRUE, 'structural-only (no judge panel)'
                )
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO UPDATE SET
                  source_extraction_run_id = EXCLUDED.source_extraction_run_id,
                  config_hash = EXCLUDED.config_hash
                RETURNING eval_run_id
                """,
                user_id, project_id, book_id, source_run, config_hash,
                idem, origin_event_id,
            )
            eval_run_id: UUID = row["eval_run_id"]
            # Re-sample replaces the prior score (idempotent).
            await conn.execute(
                "DELETE FROM quality_scores WHERE source_eval_run_id = $1", eval_run_id
            )
            await conn.execute(
                """
                INSERT INTO quality_scores
                  (target_kind, target_id, user_id, metric_name, value_num, data_type,
                   source, judge_model, source_eval_run_id)
                VALUES ('extraction_run', $1, $2, $3, $4, $5, 'heuristic', '', $6)
                """,
                str(run_id), user_id, _METRIC, completeness, data_type, eval_run_id,
            )
    return eval_run_id


def extract_run_fields(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the fields the online eval needs from an ``extraction_run_completed``
    payload. Returns None when the run_id/user_id are missing or unparseable
    (the consumer then skips + acks — best-effort)."""
    run_id = payload.get("run_id")
    raw_user = payload.get("user_id")
    if not run_id or not raw_user:
        return None
    try:
        user_id = UUID(str(raw_user))
        UUID(str(run_id))  # validate run_id is a UUID
    except (ValueError, TypeError):
        return None

    def _opt_uuid(v: Any) -> UUID | None:
        if not v:
            return None
        try:
            return UUID(str(v))
        except (ValueError, TypeError):
            return None

    return {
        "run_id": str(run_id),
        "user_id": user_id,
        "project_id": _opt_uuid(payload.get("project_id")),
        "book_id": _opt_uuid(payload.get("book_id")),
        "config_hash": payload.get("config_hash"),
        "metrics": payload.get("metrics") or {},
    }
