"""Phase E2 — config data-mining queries.

Four query functions covering the §2.4 mining outputs:
  1. get_config_quality  — genre × config_hash success rate (outcome-gated)
  2. get_model_matrix    — model_ref × scope weighted outcome
  3. get_default_drift   — convergent vs divergent param changes
  4. get_outcome_recompute — correction-join recipe (returns empty at cold-start)

All guardrails from plan §2.4 are baked in:
  - Popularity ≠ quality: success_rate = succeeded/total (never raw count).
  - Explore/exploit: get_config_quality returns a separate `exploration` list
    sampled from the tail of the ranking.
  - Selection bias: power-user segmentation param on get_config_quality.
"""
from __future__ import annotations

import math
from typing import Any
from uuid import UUID

import asyncpg


async def get_config_quality(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    genre: str | None = None,
    limit: int = 20,
    exploration_fraction: float = 0.1,
    segment_power_users: bool = False,
    power_user_threshold: int = 10,
) -> dict[str, list[dict]]:
    """Genre × config_hash quality ranking.

    Returns:
        {"items": top-N by success_rate, "exploration": random sample from the tail}
    """
    base_sql = """
        SELECT er.genre,
               er.config_hash,
               count(*)                                             AS run_count,
               count(*) FILTER (WHERE er.outcome = 'succeeded')    AS succeeded,
               avg((er.metrics->>'entities_merged')::int)
                   FILTER (WHERE er.outcome = 'succeeded')         AS avg_entities_on_success,
               count(*) FILTER (WHERE er.outcome = 'succeeded')::float
                   / NULLIF(count(*), 0)                           AS success_rate
        FROM extraction_runs er
        WHERE er.user_id = $1
          AND ($2::text IS NULL OR er.genre = $2)
          AND (
            NOT $3::bool
            OR (
                SELECT count(*) FROM config_adjustment_events cae
                WHERE cae.user_id = er.user_id
                  AND cae.project_id = er.project_id
            ) <= $4
          )
        GROUP BY er.genre, er.config_hash
        HAVING count(*) >= 2
    """
    top_sql = base_sql + " ORDER BY success_rate DESC NULLS LAST LIMIT $5"
    exploration_limit = max(1, math.ceil(limit * exploration_fraction))
    explore_sql = base_sql + " ORDER BY random() LIMIT $5 OFFSET $6"

    async with pool.acquire() as conn:
        top_rows = await conn.fetch(
            top_sql,
            user_id, genre, segment_power_users, power_user_threshold, limit,
        )
        # Exploration: random sample from rows BEYOND the top-N window.
        explore_rows = await conn.fetch(
            explore_sql,
            user_id, genre, segment_power_users, power_user_threshold,
            exploration_limit, limit,
        )

    return {
        "items": [dict(r) for r in top_rows],
        "exploration": [dict(r) for r in explore_rows],
    }


async def get_model_matrix(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    """Model × task matrix weighted by outcome.

    weighted_outcome: succeeded=1.0, skipped=0.3, failed=0.0.
    """
    sql = """
        SELECT er.model_ref,
               er.scope,
               (cr.resolved_config->>'precision_filter') IS NOT NULL AS has_filter,
               count(*)                                               AS run_count,
               count(*) FILTER (WHERE er.outcome = 'succeeded')      AS succeeded,
               avg(CASE er.outcome
                     WHEN 'succeeded' THEN 1.0
                     WHEN 'skipped'   THEN 0.3
                     ELSE 0.0
                   END)                                               AS weighted_outcome
        FROM extraction_runs er
        JOIN config_registry cr USING (config_hash)
        WHERE er.user_id = $1
          AND ($2::text IS NULL OR er.scope = $2)
        GROUP BY er.model_ref, er.scope, has_filter
        HAVING count(*) >= 2
        ORDER BY weighted_outcome DESC NULLS LAST
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, scope)
    return [dict(r) for r in rows]


async def get_default_drift(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    target: str | None = None,
    base_default_version: str | None = None,
) -> list[dict[str, Any]]:
    """Which config params deviate from the global default, and how consistently.

    drift_pattern:
      'convergent'  — all projects changed this param to the SAME value
      'divergent'   — multiple different after-values (per-novel setting)

    Guardrail: popularity ≠ quality — joins extraction_runs to confirm the
    adjusted config was actually used in runs with an outcome.
    """
    sql = """
        SELECT cae.target,
               cae.base_default_version,
               count(DISTINCT cae.project_id)              AS affected_projects,
               count(DISTINCT cae.after_structural::text)  AS distinct_after_values,
               CASE WHEN count(DISTINCT cae.after_structural::text) = 1
                    THEN 'convergent' ELSE 'divergent'
               END                                         AS drift_pattern,
               count(DISTINCT er.run_id)                   AS runs_with_outcome
        FROM config_adjustment_events cae
        JOIN extraction_runs er
          ON er.user_id = cae.user_id AND er.project_id = cae.project_id
        WHERE cae.user_id = $1
          AND cae.before_structural IS DISTINCT FROM cae.after_structural
          AND ($2::text IS NULL OR cae.target = $2)
          AND ($3::text IS NULL OR cae.base_default_version = $3)
        GROUP BY cae.target, cae.base_default_version
        ORDER BY affected_projects DESC, drift_pattern
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, target, base_default_version)
    return [dict(r) for r in rows]


async def get_outcome_recompute(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    window_days: int = 30,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Correction-join outcome recompute recipe (§2.4 / track Q2).

    Joins extraction_runs to corrections arriving AFTER the run within
    `window_days`. Attribution is by **time-window** (PO-locked Q2 decision):
    the `c.source_extraction_run_id = er.run_id OR c.source_extraction_run_id
    IS NULL` join means corrections without a run back-pointer (all of them
    today) are attributed to runs of the same owner+project inside the window.
    So this returns one row PER RUN (not empty) — runs with 0 post-window
    corrections keep their pipeline outcome; runs with corrections get
    minor/major_corrected. A precise node->run provenance link is a deferred
    refinement (only needed if time-window attribution proves too coarse).

    recomputed_outcome:
      original pipeline outcome when 0 corrections
      'minor_corrected' for 1–3 post-run corrections
      'major_corrected' for 4+ corrections
    """
    count_sql = """
        SELECT count(*) FROM extraction_runs
        WHERE user_id = $1
          AND ($2::uuid IS NULL OR project_id = $2)
    """
    data_sql = """
        SELECT er.run_id,
               er.project_id,
               er.outcome                                       AS pipeline_outcome,
               er.created_at,
               count(c.id)                                      AS post_run_corrections,
               CASE
                 WHEN count(c.id) = 0    THEN er.outcome
                 WHEN count(c.id) <= 3   THEN 'minor_corrected'
                 ELSE                         'major_corrected'
               END                                             AS recomputed_outcome
        FROM extraction_runs er
        LEFT JOIN corrections c
          ON  c.user_id   = er.user_id
          AND (c.project_id = er.project_id OR c.project_id IS NULL)
          AND c.created_at > er.created_at
          AND c.created_at
                <= er.created_at + ($3 * INTERVAL '1 day')
          AND (c.source_extraction_run_id = er.run_id
               OR c.source_extraction_run_id IS NULL)
          -- EXTRACTION corrections only. Composition co-write corrections
          -- (target_type='generation') share the book's knowledge project_id +
          -- carry source_extraction_run_id IS NULL, so without this filter they
          -- would be miscounted as extraction corrections and falsely degrade an
          -- extraction run's recomputed_outcome (/review-impl slice-2 HIGH#1).
          AND c.target_type IN ('entity', 'relation', 'event', 'fact')
        WHERE er.user_id = $1
          AND ($2::uuid IS NULL OR er.project_id = $2)
        GROUP BY er.run_id, er.project_id, er.outcome, er.created_at
        ORDER BY er.created_at DESC
        LIMIT $4 OFFSET $5
    """
    async with pool.acquire() as conn:
        total = await conn.fetchval(count_sql, user_id, project_id)
        rows = await conn.fetch(data_sql, user_id, project_id, window_days, limit, offset)
    return {
        "items": [dict(r) for r in rows],
        "total": total,
    }
