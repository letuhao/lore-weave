"""LLM-as-judge extraction eval — runner.

Judges an existing extraction dump (produced by
`test_extraction_eval.py` with `KNOWLEDGE_EVAL_DUMP_PATH` set) against
the fixture source text, using a judge model that reads the text and
decides semantic correctness — see [llm_judge.py](./llm_judge.py) for
why this complements the rule-based [eval_harness.py](./eval_harness.py).

**Decoupled from extraction on purpose.** Reads `actual.json` /
`expected.json` from the dump and `chapter.txt` from the fixtures — does
NOT re-run the extraction LLM. So you can run extraction on one model
(e.g. Qwen, loaded in LM Studio), unload it, load the judge model (e.g.
gemma), and judge — never needing both in VRAM at once.

**Opt-in.** Skipped unless invoked with `--run-quality` AND
`KNOWLEDGE_EVAL_JUDGE_MODEL` is set.

### Running

    # 1. produce an extraction dump (extraction model loaded):
    KNOWLEDGE_EVAL_MODEL=<extraction_model> ... \
    KNOWLEDGE_EVAL_DUMP_PATH=/path/to/dump \
      pytest tests/quality/test_extraction_eval.py --run-quality -s

    # 2. load the JUDGE model in LM Studio, then:
    KNOWLEDGE_EVAL_JUDGE_MODEL=<judge_model_uuid> \
    KNOWLEDGE_EVAL_USER_ID=<uuid> \
    KNOWLEDGE_JUDGE_DUMP_PATH=/path/to/dump \
      pytest tests/quality/test_judge_eval.py --run-quality -s

The judge model MUST differ from the extraction model (anti
self-reinforcement bias).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import cast

import pytest

from app.clients.llm_client import get_llm_client
from tests.quality.llm_judge import ChapterJudgement, judge_chapter

logger = logging.getLogger(__name__)

GOLDEN_ROOT = (
    Path(__file__).resolve().parent.parent / "fixtures" / "golden_chapters"
)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


def _load_source_text(chapter: str) -> str | None:
    """Source chapter text lives in the fixtures, not the dump."""
    path = GOLDEN_ROOT / chapter / "chapter.txt"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _fmt(x: float | None) -> str:
    return "n/a " if x is None else f"{x:.2f}"


def _format_chapter(j: ChapterJudgement) -> str:
    cov = ""
    if j.precision_coverage < 1.0 or j.recall_coverage < 1.0:
        cov = (
            f" [cov P={j.precision_coverage:.0%} R={j.recall_coverage:.0%}]"
        )
    return (
        f"{j.chapter:<30} "
        f"P={_fmt(j.precision)} R={_fmt(j.recall)} "
        f"| ent P={_fmt(j.entity.precision)}/R={_fmt(j.entity.recall)} "
        f"rel P={_fmt(j.relation.precision)}/R={_fmt(j.relation.recall)} "
        f"evt P={_fmt(j.event.precision)}/R={_fmt(j.event.recall)}"
        + cov
    )


def _write_chapter_verdicts(chapter_dir: Path, j: ChapterJudgement) -> None:
    payload = {
        "chapter": j.chapter,
        "precision": j.precision,
        "recall": j.recall,
        "categories": {
            c.category: {
                "n_extracted": c.n_extracted,
                "n_gold": c.n_gold,
                "precision": c.precision,
                "recall": c.recall,
                "n_unjudged": c.n_unjudged,
                "precision_verdicts": [asdict(v) for v in c.precision_verdicts],
                "recall_verdicts": [asdict(v) for v in c.recall_verdicts],
            }
            for c in j.categories
        },
    }
    (chapter_dir / "judge_verdicts.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.quality
@pytest.mark.asyncio
async def test_llm_judge_extraction_quality() -> None:
    judge_model = _env("KNOWLEDGE_EVAL_JUDGE_MODEL")
    if not judge_model:
        pytest.skip("KNOWLEDGE_EVAL_JUDGE_MODEL env var required for judge eval")
    user_id = _env("KNOWLEDGE_EVAL_USER_ID")
    if not user_id:
        pytest.skip("KNOWLEDGE_EVAL_USER_ID env var required for judge eval")
    model_source = _env("KNOWLEDGE_EVAL_JUDGE_MODEL_SOURCE", "user_model")
    dump_root_env = _env("KNOWLEDGE_JUDGE_DUMP_PATH") or _env("KNOWLEDGE_EVAL_DUMP_PATH")
    if not dump_root_env:
        pytest.skip(
            "KNOWLEDGE_JUDGE_DUMP_PATH (or KNOWLEDGE_EVAL_DUMP_PATH) required — "
            "point it at an extraction dump produced by test_extraction_eval.py"
        )
    dump_root = Path(dump_root_env).resolve()
    assert dump_root.is_dir(), f"dump path not found: {dump_root}"

    chapter_dirs = sorted(
        p for p in dump_root.iterdir()
        if p.is_dir() and (p / "actual.json").is_file()
    )
    assert chapter_dirs, f"no extraction dumps under {dump_root}"

    client = get_llm_client()

    judgements: list[ChapterJudgement] = []
    for chapter_dir in chapter_dirs:
        chapter = chapter_dir.name
        source_text = _load_source_text(chapter)
        if source_text is None:
            logger.warning("judge: no source text for %s — skipping", chapter)
            continue
        actual = json.loads((chapter_dir / "actual.json").read_text(encoding="utf-8"))
        expected_path = chapter_dir / "expected.json"
        expected = (
            json.loads(expected_path.read_text(encoding="utf-8"))
            if expected_path.is_file()
            else {"entities": [], "relations": [], "events": []}
        )
        logger.info("judging chapter: %s", chapter)
        j = await judge_chapter(
            client,
            judge_model=judge_model,
            user_id=user_id,
            model_source=cast(str, model_source),
            chapter=chapter,
            source_text=source_text,
            actual=actual,
            expected=expected,
        )
        _write_chapter_verdicts(chapter_dir, j)
        print(_format_chapter(j))  # visible with pytest -s
        judgements.append(j)

    assert judgements, "no chapters judged"

    # Macro-mean over chapters, skipping None (chapters where nothing could
    # be judged — they would otherwise corrupt the average).
    p_vals = [j.precision for j in judgements if j.precision is not None]
    r_vals = [j.recall for j in judgements if j.recall is not None]
    agg_p = mean(p_vals) if p_vals else None
    agg_r = mean(r_vals) if r_vals else None
    mean_pcov = mean(j.precision_coverage for j in judgements)
    mean_rcov = mean(j.recall_coverage for j in judgements)
    print(
        f"\nJudge aggregate (macro): P={_fmt(agg_p)} R={_fmt(agg_r)} "
        f"| coverage P={mean_pcov:.0%} R={mean_rcov:.0%} "
        f"(judge_model={judge_model}, chapters={len(judgements)}, "
        f"P over {len(p_vals)} ch, R over {len(r_vals)} ch)"
    )

    # Write an aggregate report next to the dump for later comparison.
    report = {
        "judge_model": judge_model,
        "chapters": len(judgements),
        "macro_precision": agg_p,
        "macro_recall": agg_r,
        "mean_precision_coverage": mean_pcov,
        "mean_recall_coverage": mean_rcov,
        "per_chapter": [
            {
                "chapter": j.chapter,
                "precision": j.precision,
                "recall": j.recall,
                "precision_coverage": j.precision_coverage,
                "recall_coverage": j.recall_coverage,
            }
            for j in judgements
        ],
    }
    (dump_root / "judge_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # This is a measurement run, not a gate — assert only that judging
    # actually produced verdicts (catches a silently-broken judge call).
    total_verdicts = sum(
        len(c.precision_verdicts) + len(c.recall_verdicts)
        for j in judgements for c in j.categories
    )
    assert total_verdicts > 0, "judge produced zero verdicts across all chapters"
