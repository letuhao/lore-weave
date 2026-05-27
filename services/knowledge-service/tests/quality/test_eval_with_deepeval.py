"""DeepEval wrap of the narrative-fiction extraction quality eval (cycle 2026-05-27).

Per spec D1 + D5: a DeepEval-orchestrated PARALLEL path to the legacy
`test_extraction_eval.py` + `test_judge_eval.py`. Runs the same extractor
on the same golden-set fixtures, scores with 3 G-Eval metrics (each pinned
to a DISTINCT judge per D5 — no circular judging), and emits DeepEval's
structured run report. Runnable side-by-side with the legacy eval for
methodology validation before any retirement decision.

This test does NOT replace the legacy harness. It's an additive validation
that the new framework produces directionally-consistent signal.

ENV:
    KNOWLEDGE_EVAL_MODEL=<extractor_user_model_uuid>
    KNOWLEDGE_EVAL_USER_ID=<user_uuid>
    KNOWLEDGE_EVAL_MODEL_SOURCE=user_model     (default)
    KNOWLEDGE_EVAL_MODEL_CONTEXT=<int>         (default 40000)
    KNOWLEDGE_EVAL_DEEPEVAL_CHAPTERS=alice_ch01,...  (comma-sep; default: alice_ch01 only)
    KNOWLEDGE_EVAL_DUMP_PATH=<dir>             (DeepEval results written here)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal, cast

import pytest

from loreweave_extraction import ContextBudget
from loreweave_extraction.extractors.entity import extract_entities

logger = logging.getLogger(__name__)

# Path to golden chapters (matches conventions used elsewhere in tests/quality)
_GOLDEN_ROOT = (
    Path(__file__).resolve().parent.parent / "fixtures" / "golden_chapters"
)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


def _load_chapter_text(chapter: str) -> str | None:
    """Load a chapter's source text from golden_chapters/."""

    path = _GOLDEN_ROOT / chapter / "chapter.txt"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _load_chapter_expected(chapter: str) -> dict:
    """Load a chapter's gold extraction (expected.yaml or expected.json)."""

    yaml_path = _GOLDEN_ROOT / chapter / "expected.yaml"
    if yaml_path.is_file():
        import yaml  # type: ignore[import-not-found]
        with yaml_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    json_path = _GOLDEN_ROOT / chapter / "expected.json"
    if json_path.is_file():
        return json.loads(json_path.read_text(encoding="utf-8"))
    return {"entities": [], "relations": [], "events": []}


@pytest.mark.quality
@pytest.mark.asyncio
async def test_deepeval_narrative_metrics() -> None:
    """Run the 3 narrative G-Eval metrics on one or more chapters.

    Default: alice_ch01 only (smallest English fixture; ~1.4KB). Override
    via `KNOWLEDGE_EVAL_DEEPEVAL_CHAPTERS=alice_ch01,journey_west_zh_ch01`.
    """

    model_ref = _env("KNOWLEDGE_EVAL_MODEL")
    if not model_ref:
        pytest.skip("KNOWLEDGE_EVAL_MODEL required for DeepEval eval")
    user_id = _env("KNOWLEDGE_EVAL_USER_ID")
    if not user_id:
        pytest.skip("KNOWLEDGE_EVAL_USER_ID required for DeepEval eval")
    model_source = cast(
        Literal["user_model", "platform_model"],
        _env("KNOWLEDGE_EVAL_MODEL_SOURCE", "user_model"),
    )
    model_context = int(_env("KNOWLEDGE_EVAL_MODEL_CONTEXT", "40000") or 40000)
    chapter_csv = _env("KNOWLEDGE_EVAL_DEEPEVAL_CHAPTERS", "alice_ch01")
    chapters = [c.strip() for c in cast(str, chapter_csv).split(",") if c.strip()]

    # Deferred imports — DeepEval module pulls a lot
    from deepeval import evaluate
    from deepeval.test_case import LLMTestCase

    from app.clients.llm_client import get_llm_client
    from app.extraction.pass2_orchestrator import gather_relations_events_facts
    from tests.quality.deepeval_metrics import build_all_metrics

    client = get_llm_client()
    budget = ContextBudget(model_context=model_context)
    metrics = build_all_metrics(client, cast(str, user_id))

    test_cases: list[LLMTestCase] = []
    for chapter in chapters:
        text = _load_chapter_text(chapter)
        if text is None:
            logger.warning("DeepEval: chapter %s not found, skipping", chapter)
            continue
        expected = _load_chapter_expected(chapter)

        # Run extraction
        entities = await extract_entities(
            text=text,
            known_entities=[],
            user_id=cast(str, user_id),
            project_id=None,
            model_source=model_source,
            model_ref=cast(str, model_ref),
            llm_client=client,
            context_budget=budget,
        )
        relations, events, _facts = (
            await gather_relations_events_facts(
                text=text,
                entities=entities,
                known_entities=[],
                user_id=cast(str, user_id),
                project_id=None,
                model_source=model_source,
                model_ref=cast(str, model_ref),
                llm_client=client,
                context_budget=budget,
            )
            if entities
            else ([], [], [])
        )

        # Build a DeepEval test case for each of the 3 metrics. They share
        # `input` (chapter text). `actual_output` and `expected_output` are
        # the JSON-stringified extracted/gold collections so G-Eval's natural
        # language criteria can reason over them.
        # We bundle ALL extractor categories into a single test_case;
        # each metric pulls the relevant fields per its criteria.
        actual_payload = {
            "entities": [{"name": e.name, "kind": e.kind} for e in entities],
            "relations": [
                {
                    "subject": r.subject,
                    "predicate": r.predicate,
                    "object": r.object,
                }
                for r in relations
            ],
            "events": [
                {"summary": ev.summary, "participants": list(ev.participants)}
                for ev in events
            ],
        }
        case = LLMTestCase(
            input=text,
            actual_output=json.dumps(actual_payload, ensure_ascii=False),
            expected_output=json.dumps(expected, ensure_ascii=False),
        )
        test_cases.append(case)

    if not test_cases:
        pytest.skip(f"No chapters loaded from {chapters}")

    # Run DeepEval. `evaluate` is the orchestration entry — returns a result
    # object with per-metric per-case scores.
    print(f"\nDeepEval: running {len(metrics)} metrics × {len(test_cases)} cases")
    results = evaluate(test_cases=test_cases, metrics=metrics)

    # Persist results next to the dump
    dump_dir = _env("KNOWLEDGE_EVAL_DUMP_PATH")
    if dump_dir:
        out_path = Path(dump_dir) / "deepeval_results.json"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # `results` is a Pydantic model in DeepEval ≥ 4.0; fall back to str.
            payload = (
                results.model_dump() if hasattr(results, "model_dump")
                else str(results)
            )
            out_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            print(f"DeepEval results written: {out_path}")
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to persist DeepEval results: %s", e)

    # Accept: at least one metric produced ≥ 1 successful score across the
    # test cases. Sanity-floor analogous to anchor_runner (HIGH-1 spirit:
    # not zero-output, but no quality gate).
    summary = getattr(results, "test_results", None) or []
    n_scored = 0
    for tr in summary:
        # tr.metrics_data is a list of MetricData with .score attribute
        for md in getattr(tr, "metrics_data", []) or []:
            score = getattr(md, "score", None)
            if score is not None:
                n_scored += 1
                print(
                    f"  - {getattr(md, 'name', '?')}: score={score:.3f} "
                    f"reason={getattr(md, 'reason', '')[:80]}"
                )
    assert n_scored > 0, (
        "DeepEval produced zero scored metric outcomes — likely judge model "
        "unavailable, prompt rejected, or G-Eval parse failure. Check the "
        "DeepEval logs for the actual failure mode."
    )
