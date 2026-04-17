"""K17.10 — End-to-end golden-set quality eval.

Runs the full K17.4–K17.7 LLM extraction pipeline against every
chapter under ``tests/fixtures/golden_chapters/`` and asserts
aggregate precision / recall / FP-trap-rate against configurable
thresholds.

**Opt-in.** Skipped unless pytest is invoked with ``--run-quality``
(see [tests/quality/conftest.py](./conftest.py)). The eval hits a
real LLM via ``ProviderClient`` — CI cannot run it without a
provider-registry-backed user and BYOK credentials.

### Running locally

    # Requires LM Studio or similar with KNOWLEDGE_EVAL_MODEL available.
    export KNOWLEDGE_EVAL_MODEL="lmstudio/qwen-3.5-9b"
    export KNOWLEDGE_EVAL_MODEL_SOURCE="user_model"
    export KNOWLEDGE_EVAL_USER_ID="your-user-uuid"

    cd services/knowledge-service
    pytest tests/quality/ --run-quality -v

### Thresholds

Default per KSA §9.9 (GPT-4o-mini-calibrated — treat as upper bar,
tune down for local models). Override via env:

    KNOWLEDGE_EVAL_MIN_PRECISION  default 0.80
    KNOWLEDGE_EVAL_MIN_RECALL     default 0.70
    KNOWLEDGE_EVAL_MAX_FP_TRAP    default 0.15

Reference: KSA §9.9, K17.10 plan row.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal, cast

import pytest

from app.extraction.llm_entity_extractor import extract_entities
from app.extraction.llm_event_extractor import extract_events
from app.extraction.llm_relation_extractor import extract_relations
from tests.quality.eval_harness import (
    ActualExtraction,
    AggregateScore,
    ChapterScore,
    aggregate_scores,
    iter_chapter_fixtures,
    score_chapter,
)

logger = logging.getLogger(__name__)

GOLDEN_ROOT = (
    Path(__file__).resolve().parent.parent / "fixtures" / "golden_chapters"
)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        pytest.fail(f"env {name}={raw!r} is not a valid float")


def _format_score(score: ChapterScore) -> str:
    return (
        f"{score.chapter:<30} "
        f"P={score.precision:.2f} R={score.recall:.2f} "
        f"FP-trap={score.fp_trap_rate:.2f} "
        f"(tp={score.tp} fp={score.fp} fn={score.fn} "
        f"trap={score.fp_trap}/{score.trap_total})"
    )


def _write_report(agg: AggregateScore, report_path: Path) -> None:
    payload = {
        "avg_precision": agg.avg_precision,
        "avg_recall": agg.avg_recall,
        "avg_fp_trap_rate": agg.avg_fp_trap_rate,
        "per_chapter": [
            {
                "chapter": s.chapter,
                "precision": s.precision,
                "recall": s.recall,
                "fp_trap_rate": s.fp_trap_rate,
                "tp": s.tp,
                "fp": s.fp,
                "fn": s.fn,
                "fp_trap": s.fp_trap,
                "trap_total": s.trap_total,
            }
            for s in agg.per_chapter
        ],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.mark.quality
@pytest.mark.asyncio
async def test_extraction_quality_meets_thresholds(tmp_path: Path) -> None:
    """Full K17.4–K17.7 pipeline vs golden set, threshold-gated."""
    model_ref = _env("KNOWLEDGE_EVAL_MODEL")
    if not model_ref:
        pytest.skip("KNOWLEDGE_EVAL_MODEL env var required for quality eval")
    model_source = cast(
        Literal["user_model", "platform_model"],
        _env("KNOWLEDGE_EVAL_MODEL_SOURCE", "user_model"),
    )
    user_id = _env("KNOWLEDGE_EVAL_USER_ID")
    if not user_id:
        pytest.skip("KNOWLEDGE_EVAL_USER_ID env var required for quality eval")
    project_id = _env("KNOWLEDGE_EVAL_PROJECT_ID")

    min_precision = _env_float("KNOWLEDGE_EVAL_MIN_PRECISION", 0.80)
    min_recall = _env_float("KNOWLEDGE_EVAL_MIN_RECALL", 0.70)
    max_fp_trap = _env_float("KNOWLEDGE_EVAL_MAX_FP_TRAP", 0.15)

    assert GOLDEN_ROOT.is_dir(), f"Missing golden fixtures: {GOLDEN_ROOT}"

    scores: list[ChapterScore] = []
    for fixture in iter_chapter_fixtures(GOLDEN_ROOT):
        logger.info("Extracting chapter: %s", fixture.name)

        entities = await extract_entities(
            text=fixture.text,
            known_entities=[],
            user_id=user_id,
            project_id=project_id,
            model_source=model_source,
            model_ref=model_ref,
        )
        known_names = [e.name for e in entities]

        if entities:
            relations = await extract_relations(
                text=fixture.text,
                entities=entities,
                known_entities=known_names,
                user_id=user_id,
                project_id=project_id,
                model_source=model_source,
                model_ref=model_ref,
            )
            events = await extract_events(
                text=fixture.text,
                entities=entities,
                known_entities=known_names,
                user_id=user_id,
                project_id=project_id,
                model_source=model_source,
                model_ref=model_ref,
            )
        else:
            relations = []
            events = []

        actual = ActualExtraction(
            entities=[(e.name, e.kind) for e in entities],
            relations=[(r.subject, r.predicate, r.object) for r in relations],
            events=[(ev.summary, tuple(ev.participants)) for ev in events],
        )
        score = score_chapter(fixture, actual)
        scores.append(score)
        print(_format_score(score))  # visible with pytest -s

    agg = aggregate_scores(scores)
    _write_report(agg, tmp_path / "eval_report.json")

    print(
        f"\nAggregate: P={agg.avg_precision:.3f} "
        f"R={agg.avg_recall:.3f} "
        f"FP-trap={agg.avg_fp_trap_rate:.3f} "
        f"(model={model_ref})"
    )

    assert agg.avg_precision >= min_precision, (
        f"Precision {agg.avg_precision:.3f} < gate {min_precision:.2f} "
        f"(model={model_ref})"
    )
    assert agg.avg_recall >= min_recall, (
        f"Recall {agg.avg_recall:.3f} < gate {min_recall:.2f} "
        f"(model={model_ref})"
    )
    assert agg.avg_fp_trap_rate <= max_fp_trap, (
        f"FP-trap rate {agg.avg_fp_trap_rate:.3f} > gate {max_fp_trap:.2f} "
        f"(model={model_ref})"
    )
