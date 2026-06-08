"""Quality-plane persistence (track phase Q1).

Writes a scored ``loreweave_eval.EvalResult`` into the three-object quality
schema: one ``eval_runs`` row + N ``eval_results`` rows (per judge) + per-judge
& run-level ``quality_scores`` rows, all validated at write time against
``score_config``. Idempotent: re-scoring the same ``idempotency_key`` updates the
run in place and replaces its children.

Metric names mirror the OTel ``gen_ai.evaluation.*`` semantic conventions so the
persisted scores stay portable to Phoenix/Grafana later.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

import asyncpg

from loreweave_eval.scorer import EvalResult


def _jsonb(value: Any) -> str | None:
    return None if value is None else json.dumps(value, default=str)


def _unjson(value: Any) -> Any:
    """asyncpg returns jsonb columns as str (no codec) — decode for responses."""
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    return value


class ScoreValidationError(ValueError):
    """A quality_score failed validation against its score_config."""


# ── score_config seed — the metric-of-record ─────────────────────────
# (mirrors OTel gen_ai.evaluation.* semantics; numeric F1/P/R in [0,1],
# Fleiss kappa in [-1,1].)
SCORE_CONFIG_SEED: list[dict[str, Any]] = [
    {"name": "disjoint_median_f1", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Disjoint median-of-record F1 (judges excluding the extractor + filter)."},
    {"name": "full_panel_median_f1", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Full-panel median F1 (includes self-grading judges; comparison only)."},
    {"name": "macro_f1", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Per-judge macro F1 over chapters."},
    {"name": "macro_precision", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Per-judge macro precision over chapters."},
    {"name": "macro_recall", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Per-judge macro recall over chapters."},
    {"name": "fleiss_kappa", "data_type": "numeric", "min_value": -1.0, "max_value": 1.0,
     "description": "Inter-judge agreement (Fleiss kappa)."},
    {"name": "chat_user_rating", "data_type": "numeric", "min_value": -1.0, "max_value": 1.0,
     "description": "Explicit user rating of a chat turn (+1 up / -1 down; regenerate = -1)."},
    {"name": "online_structural_completeness", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Online structural health of an extraction run: fraction of core "
                    "categories (entity/relation/event) that produced output. No source/gold needed."},
    {"name": "online_judge_precision", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "Online LLM-judge precision: per-item supported-credit of an extraction "
                    "vs its source text (Q4b; needs items + source from an opted-in run)."},
    {"name": "translation_quality_score", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "M7a (Channel 2): the V3 translation verifier's per-chapter overall "
                    "quality score (auto/LLM-action log). Breakdown (unresolved-high, qa "
                    "rounds, issue-type counts) carried in the score comment."},
    {"name": "translation_human_accept", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "M7b (Channel 1a): a human set this chapter-translation version active "
                    "(=1.0, a publish judgment). The verifier-calibration detail "
                    "(acknowledged_issues + unresolved_high at accept) rides in the comment."},
    {"name": "glossary_name_confirmed", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "M7c-3: a human verified a glossary name's target rendering (the M6a "
                    "confirm-a-name action) =1.0 — a canonical source→target pair (in the "
                    "comment) for name-rendering tuning."},
    {"name": "translation_judge_fidelity", "data_type": "numeric", "min_value": 0.0, "max_value": 1.0,
     "description": "M7d: online LLM-judge fidelity of a translation vs its source [0,1] "
                    "(source=auto, panel_safe=false — a single online judge). Reason + judge "
                    "model in the comment."},
]


async def ensure_score_configs(pool: asyncpg.Pool) -> None:
    """Idempotently seed the metric-of-record score_config rows (boot-time)."""
    async with pool.acquire() as conn:
        for sc in SCORE_CONFIG_SEED:
            await conn.execute(
                """
                INSERT INTO score_config (name, data_type, min_value, max_value, categories, description)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT (name) DO NOTHING
                """,
                sc["name"], sc["data_type"], sc.get("min_value"), sc.get("max_value"),
                _jsonb(sc.get("categories")), sc.get("description"),
            )


async def _load_score_configs(conn: asyncpg.Connection) -> dict[str, dict]:
    rows = await conn.fetch(
        "SELECT name, data_type, min_value, max_value, categories "
        "FROM score_config WHERE NOT is_archived"
    )
    return {r["name"]: dict(r) for r in rows}


def _validate_score(
    cfgs: dict[str, dict], metric_name: str, value_num: float | None, value_label: str | None
) -> str:
    """Validate one score against its registered config. Returns the data_type.
    Raises ScoreValidationError on an unregistered metric or out-of-range value."""
    cfg = cfgs.get(metric_name)
    if cfg is None:
        raise ScoreValidationError(
            f"unknown metric_name {metric_name!r} (no score_config registered)"
        )
    dt = cfg["data_type"]
    if dt == "numeric":
        if value_num is None:
            raise ScoreValidationError(f"{metric_name}: numeric score requires value_num")
        lo, hi = cfg["min_value"], cfg["max_value"]
        if (lo is not None and value_num < lo) or (hi is not None and value_num > hi):
            raise ScoreValidationError(
                f"{metric_name}={value_num} out of range [{lo}, {hi}]"
            )
    elif dt == "categorical":
        cats = _unjson(cfg.get("categories")) or []
        if value_label not in cats:
            raise ScoreValidationError(
                f"{metric_name}: label {value_label!r} not in {cats}"
            )
    elif dt == "boolean":
        if value_label not in ("true", "false"):
            raise ScoreValidationError(f"{metric_name}: boolean label must be 'true'/'false'")
    return dt


def _build_scores(result: EvalResult) -> list[tuple[str, float | None, str | None, str, str]]:
    """(metric_name, value_num, value_label, source, judge_model) tuples to persist
    as quality_scores: per-judge macro_f1 + the run-level aggregates."""
    scores: list[tuple[str, float | None, str | None, str, str]] = []
    for js in result.per_judge:
        if js.macro_f1 is not None:
            scores.append(("macro_f1", js.macro_f1, None, "llm_judge", js.uuid or ""))
    if result.disjoint_median_f1 is not None:
        scores.append(("disjoint_median_f1", result.disjoint_median_f1, None, "heuristic", ""))
    if result.full_panel_median_f1 is not None:
        scores.append(("full_panel_median_f1", result.full_panel_median_f1, None, "heuristic", ""))
    if result.fleiss_kappa is not None:
        scores.append(("fleiss_kappa", result.fleiss_kappa, None, "heuristic", ""))
    return scores


async def persist_eval_result(
    pool: asyncpg.Pool,
    result: EvalResult,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    book_id: UUID | None = None,
    source_extraction_run_id: UUID | None = None,
    config_hash: str | None = None,
    judge_panel_id: UUID | None = None,
    dataset_version: str | None = None,
    source: str = "offline",
    idempotency_key: str | None = None,
    origin_service: str | None = None,
    origin_event_id: str | None = None,
) -> UUID:
    """Persist a scored EvalResult. Validates every score BEFORE any write
    (fail-fast, no partial rows). Idempotent on ``idempotency_key``.
    """
    scores = _build_scores(result)
    judges_json = _jsonb([asdict(j) for j in result.per_judge])
    ci_json = _jsonb(
        {
            "low": result.disjoint_ci_low,
            "high": result.disjoint_ci_high,
            "n_common_chapters": result.n_common_chapters,
        }
    )

    async with pool.acquire() as conn:
        cfgs = await _load_score_configs(conn)
        for metric, vnum, vlabel, _src, _jm in scores:
            _validate_score(cfgs, metric, vnum, vlabel)  # raises before any write

        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO eval_runs (
                  user_id, project_id, book_id, source_extraction_run_id, config_hash,
                  judge_panel_id, dataset_version, source, judges, disjoint_median_f1,
                  full_panel_median_f1, fleiss_kappa, bootstrap_ci, n_chapters,
                  n_disjoint_judges, idempotency_key, origin_service, origin_event_id,
                  panel_safe, panel_safety_reason
                ) VALUES (
                  $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10,
                  $11, $12, $13::jsonb, $14, $15, $16, $17, $18, $19, $20
                )
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO UPDATE SET
                  judges = EXCLUDED.judges,
                  disjoint_median_f1 = EXCLUDED.disjoint_median_f1,
                  full_panel_median_f1 = EXCLUDED.full_panel_median_f1,
                  fleiss_kappa = EXCLUDED.fleiss_kappa,
                  bootstrap_ci = EXCLUDED.bootstrap_ci,
                  n_chapters = EXCLUDED.n_chapters,
                  n_disjoint_judges = EXCLUDED.n_disjoint_judges,
                  source = EXCLUDED.source,
                  dataset_version = EXCLUDED.dataset_version,
                  panel_safe = EXCLUDED.panel_safe,
                  panel_safety_reason = EXCLUDED.panel_safety_reason
                RETURNING eval_run_id
                """,
                user_id, project_id, book_id, source_extraction_run_id, config_hash,
                judge_panel_id, dataset_version, source, judges_json,
                result.disjoint_median_f1, result.full_panel_median_f1, result.fleiss_kappa,
                ci_json, result.n_common_chapters, result.n_disjoint_judges,
                idempotency_key, origin_service, origin_event_id,
                getattr(result, "panel_safe", None), getattr(result, "panel_safety_reason", None),
            )
            eval_run_id: UUID = row["eval_run_id"]
            run_id_str = str(eval_run_id)

            # Re-score replaces children (idempotent under DO UPDATE).
            await conn.execute("DELETE FROM eval_results WHERE eval_run_id = $1", eval_run_id)
            await conn.execute(
                "DELETE FROM quality_scores WHERE source_eval_run_id = $1", eval_run_id
            )

            for js in result.per_judge:
                await conn.execute(
                    """
                    INSERT INTO eval_results
                      (eval_run_id, category, judge_label, judge_uuid, precision, recall, f1)
                    VALUES ($1, 'all', $2, $3, $4, $5, $6)
                    """,
                    eval_run_id, js.label, js.uuid, js.macro_p, js.macro_r, js.macro_f1,
                )

            for metric, vnum, vlabel, src, jm in scores:
                dt = cfgs[metric]["data_type"]
                await conn.execute(
                    """
                    INSERT INTO quality_scores
                      (target_kind, target_id, user_id, book_id, metric_name, value_num,
                       value_label, data_type, source, judge_model, source_eval_run_id)
                    VALUES ('eval_run', $1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    run_id_str, user_id, book_id, metric, vnum, vlabel, dt, src, jm, eval_run_id,
                )

    return eval_run_id


async def persist_consumed_score(
    pool: asyncpg.Pool,
    *,
    target_kind: str,
    target_id: str,
    user_id: UUID,
    metric_name: str,
    source: str,
    origin_service: str,
    origin_event_id: str,
    value_num: float | None = None,
    value_label: str | None = None,
    book_id: UUID | None = None,
    comment: str | None = None,
    judge_model: str = "",
) -> bool:
    """Persist a quality_score from a CONSUMED event (chat feedback Q3; future
    human/heuristic signals). Validated against score_config; idempotent on the
    relay's ``(origin_service, origin_event_id)`` dedup key. Returns True if a
    new row was inserted, False on conflict. An empty ``origin_event_id`` is a
    hard error (the handler lets it bubble to the DLQ rather than collapse the
    log with "")."""
    if not origin_event_id:
        raise ValueError(
            f"consumed score from {origin_service} has empty origin_event_id — refusing to insert"
        )
    async with pool.acquire() as conn:
        cfgs = await _load_score_configs(conn)
        data_type = _validate_score(cfgs, metric_name, value_num, value_label)
        status = await conn.execute(
            """
            INSERT INTO quality_scores
              (target_kind, target_id, user_id, book_id, metric_name, value_num,
               value_label, data_type, source, judge_model, comment,
               origin_service, origin_event_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (origin_service, origin_event_id)
              WHERE origin_event_id IS NOT NULL DO NOTHING
            """,
            target_kind, target_id, user_id, book_id, metric_name, value_num,
            value_label, data_type, source, judge_model, comment,
            origin_service, origin_event_id,
        )
    return status.endswith(" 1")  # "INSERT 0 1" inserted vs "INSERT 0 0" conflict


def _parse_eval_run_row(row: asyncpg.Record) -> dict:
    d = dict(row)
    for k in ("judges", "bootstrap_ci", "bias_metrics"):
        if k in d:
            d[k] = _unjson(d[k])
    return d


async def list_eval_runs(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    config_hash: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Per-owner list of eval runs, newest first."""
    sql = """
        SELECT eval_run_id, user_id, project_id, book_id, source_extraction_run_id,
               config_hash, dataset_version, source, judges, disjoint_median_f1,
               full_panel_median_f1, fleiss_kappa, bootstrap_ci, bias_metrics,
               n_chapters, n_disjoint_judges, created_at
        FROM eval_runs
        WHERE user_id = $1
          AND ($2::uuid IS NULL OR project_id = $2)
          AND ($3::text IS NULL OR config_hash = $3)
          AND ($4::text IS NULL OR source = $4)
        ORDER BY created_at DESC
        LIMIT $5 OFFSET $6
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, project_id, config_hash, source, limit, offset)
    return [_parse_eval_run_row(r) for r in rows]


async def get_eval_run(
    pool: asyncpg.Pool, *, user_id: UUID, eval_run_id: UUID
) -> dict | None:
    """Fetch one eval run (owner-scoped) with its per-judge results."""
    async with pool.acquire() as conn:
        run = await conn.fetchrow(
            """
            SELECT eval_run_id, user_id, project_id, book_id, source_extraction_run_id,
                   config_hash, dataset_version, source, judges, disjoint_median_f1,
                   full_panel_median_f1, fleiss_kappa, bootstrap_ci, bias_metrics,
                   n_chapters, n_disjoint_judges, created_at
            FROM eval_runs WHERE eval_run_id = $1 AND user_id = $2
            """,
            eval_run_id, user_id,
        )
        if run is None:
            return None
        results = await conn.fetch(
            "SELECT category, judge_label, judge_uuid, precision, recall, f1, chapter_ref "
            "FROM eval_results WHERE eval_run_id = $1 ORDER BY judge_label",
            eval_run_id,
        )
    out = _parse_eval_run_row(run)
    out["results"] = [dict(r) for r in results]
    return out
