"""Online LLM-as-judge (track phase Q4b).

When a sampled run carries the extracted items + source text (opted-in projects)
and a rule has a judge panel, the eval-runner judges the extraction via the
provider-registry gateway, reusing the lifted ``loreweave_eval.llm_judge`` (the
same judge that produced the locked F1). It scores PRECISION — does each
extracted item have support in the source? — which needs no gold (online
production chapters have none). Per-item verdicts are persisted so Q3.5
``calibrate_judge`` can run against human corrections later.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from loreweave_eval._client import JudgeLLMClient
from loreweave_eval.llm_judge import judge_precision

from app.db.eval_repo import _load_score_configs, _validate_score

_PRECISION_CREDIT = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0, "unjudged": 0.0}
_CATEGORIES = ("entity", "relation", "event")
_METRIC = "online_judge_precision"


async def run_online_judge(
    client: JudgeLLMClient,
    *,
    source_text: str,
    items_by_category: dict[str, list[Any]],
    judge_model: str,
    model_source: str,
    user_id: str,
) -> dict:
    """Judge each extracted item against the source. Returns
    ``{per_category: {precision, n_judged, verdicts}, overall_precision, n_judged}``.
    """
    per_category: dict[str, dict] = {}
    total_credit = 0.0
    total_judged = 0

    for category in _CATEGORIES:
        extracted = items_by_category.get(category) or []
        if not extracted:
            continue
        verdicts = await judge_precision(
            client,
            judge_model=judge_model,
            user_id=user_id,
            model_source=model_source,
            source_text=source_text,
            category=category,  # type: ignore[arg-type]
            extracted=extracted,
        )
        credits = [
            _PRECISION_CREDIT.get(v.verdict, 0.0)
            for v in verdicts
            if v.verdict != "unjudged"
        ]
        n = len(credits)
        per_category[category] = {
            "precision": (sum(credits) / n) if n else None,
            "n_judged": n,
            "verdicts": [{"idx": v.idx, "verdict": v.verdict} for v in verdicts],
        }
        total_credit += sum(credits)
        total_judged += n

    return {
        "per_category": per_category,
        "overall_precision": (total_credit / total_judged) if total_judged else None,
        "n_judged": total_judged,
    }


def aggregate_precision_dicts(verdicts_by_category: dict[str, list[dict]]) -> dict:
    """Build the ``run_online_judge``-shaped ``judge_result`` from per-category
    verdict DICTS (``{"idx","verdict"}``), for the decoupled judge SM finalize.

    The fan-out judge accumulates each batch's verdicts as JSON dicts in its
    resume_state (not ItemVerdict objects), so this mirrors ``run_online_judge``'s
    aggregation over the persisted shape — same credit map, same denominator
    (unjudged excluded), same ``per_category`` / ``overall_precision`` output that
    ``persist_online_judge`` consumes."""
    per_category: dict[str, dict] = {}
    total_credit = 0.0
    total_judged = 0
    for category in _CATEGORIES:
        verdicts = verdicts_by_category.get(category) or []
        if not verdicts:
            continue
        credits = [
            _PRECISION_CREDIT.get(v.get("verdict"), 0.0)
            for v in verdicts
            if v.get("verdict") != "unjudged"
        ]
        n = len(credits)
        per_category[category] = {
            "precision": (sum(credits) / n) if n else None,
            "n_judged": n,
            "verdicts": [{"idx": v.get("idx"), "verdict": v.get("verdict")} for v in verdicts],
        }
        total_credit += sum(credits)
        total_judged += n
    return {
        "per_category": per_category,
        "overall_precision": (total_credit / total_judged) if total_judged else None,
        "n_judged": total_judged,
    }


async def persist_online_judge(
    pool: asyncpg.Pool,
    *,
    run_id: str,
    user_id: UUID,
    judge_model: str,
    judge_result: dict,
    project_id: UUID | None = None,
    book_id: UUID | None = None,
    config_hash: str | None = None,
) -> UUID | None:
    """Persist an online LLM-judge result: an ``eval_runs`` row (source='online',
    idempotent ``online-judge:<run_id>:<judge>``) + per-category ``eval_results``
    + an ``online_judge_precision`` ``quality_scores`` row. Returns None when
    nothing was judged."""
    overall = judge_result.get("overall_precision")
    if overall is None:
        return None
    idem = f"online-judge:{run_id}:{judge_model}"
    judges_json = json.dumps([{"label": judge_model, "uuid": judge_model, "role": "online_judge"}])

    async with pool.acquire() as conn:
        cfgs = await _load_score_configs(conn)
        data_type = _validate_score(cfgs, _METRIC, overall, None)  # raises if bad
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO eval_runs (
                  user_id, project_id, book_id, source_extraction_run_id, config_hash,
                  source, judges, n_disjoint_judges, idempotency_key, origin_service,
                  panel_safe, panel_safety_reason
                ) VALUES (
                  $1, $2, $3, $4, $5, 'online', $6::jsonb, 1, $7, 'knowledge',
                  FALSE, 'single online judge (precision only, not the disjoint metric of record)'
                )
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO UPDATE SET judges = EXCLUDED.judges, config_hash = EXCLUDED.config_hash
                RETURNING eval_run_id
                """,
                user_id, project_id, book_id, UUID(str(run_id)), config_hash, judges_json, idem,
            )
            eval_run_id: UUID = row["eval_run_id"]
            await conn.execute("DELETE FROM eval_results WHERE eval_run_id = $1", eval_run_id)
            await conn.execute(
                "DELETE FROM quality_scores WHERE source_eval_run_id = $1", eval_run_id
            )
            for category, cat in judge_result.get("per_category", {}).items():
                await conn.execute(
                    """
                    INSERT INTO eval_results
                      (eval_run_id, category, judge_label, judge_uuid, precision, gold_projection)
                    VALUES ($1, $2, $3, $3, $4, $5::jsonb)
                    """,
                    eval_run_id, category, judge_model, cat.get("precision"),
                    json.dumps({"verdicts": cat.get("verdicts", [])}),
                )
            await conn.execute(
                """
                INSERT INTO quality_scores
                  (target_kind, target_id, user_id, metric_name, value_num, data_type,
                   source, judge_model, source_eval_run_id)
                VALUES ('extraction_run', $1, $2, $3, $4, $5, 'llm_judge', $6, $7)
                """,
                str(run_id), user_id, _METRIC, overall, data_type, judge_model, eval_run_id,
            )
    return eval_run_id
