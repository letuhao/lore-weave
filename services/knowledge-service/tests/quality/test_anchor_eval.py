"""Anchor benchmark eval against published-baseline datasets (cycle 2026-05-27).

Per spec D2 + Acceptance gate: runs the extractor against CoNLL-2003 + DocRED
samples and verifies the **sanity floor** (HIGH-1 fix) — extractor must not
return ~empty. F1 numbers themselves are informational, not quality gates.

ENV (matches existing eval test conventions):
    KNOWLEDGE_EVAL_MODEL=<extractor_user_model_uuid>
    KNOWLEDGE_EVAL_USER_ID=<user_uuid>
    KNOWLEDGE_EVAL_MODEL_SOURCE=user_model         (default)
    KNOWLEDGE_EVAL_MODEL_CONTEXT=<int>             (default 40000)
    KNOWLEDGE_EVAL_DUMP_PATH=<dir>                 (anchor reports written here)
    KNOWLEDGE_EVAL_ANCHOR_N_CONLL=<int>            (default 100; spec Q1)
    KNOWLEDGE_EVAL_ANCHOR_N_DOCRED=<int>           (default 100)
    HF_DATASETS_CACHE=<path>                       (optional)

Marker: @pytest.mark.quality + requires --run-quality flag.
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
from app.clients.llm_client import get_llm_client
from app.extraction.pass2_orchestrator import gather_relations_events_facts
from tests.quality.anchor_runner import (
    ExtractedEntity,
    ExtractedTriple,
    run_conll2003_anchor,
    run_docred_anchor,
    write_anchor_report,
)

logger = logging.getLogger(__name__)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value else default


def _resolve_eval_params() -> dict[str, object] | None:
    """Read env config; return None to signal `pytest.skip` if anything missing."""

    model_ref = _env("KNOWLEDGE_EVAL_MODEL")
    if not model_ref:
        return None
    user_id = _env("KNOWLEDGE_EVAL_USER_ID")
    if not user_id:
        return None
    model_source = cast(
        Literal["user_model", "platform_model"],
        _env("KNOWLEDGE_EVAL_MODEL_SOURCE", "user_model"),
    )
    model_context = int(_env("KNOWLEDGE_EVAL_MODEL_CONTEXT", "40000") or 40000)
    return {
        "model_ref": model_ref,
        "user_id": user_id,
        "model_source": model_source,
        "budget": ContextBudget(model_context=model_context),
    }


@pytest.mark.quality
@pytest.mark.asyncio
async def test_conll2003_anchor_passes_sanity_floor() -> None:
    """Run CoNLL-2003 anchor + assert sanity floor (spec HIGH-1)."""

    params = _resolve_eval_params()
    if params is None:
        pytest.skip("KNOWLEDGE_EVAL_MODEL + KNOWLEDGE_EVAL_USER_ID required")
    n_samples = int(_env("KNOWLEDGE_EVAL_ANCHOR_N_CONLL", "100") or 100)
    hf_cache = _env("HF_DATASETS_CACHE")

    llm_client = get_llm_client()

    async def _extractor(text: str) -> list[ExtractedEntity]:
        candidates = await extract_entities(
            text=text,
            known_entities=[],
            user_id=cast(str, params["user_id"]),
            project_id=None,
            model_source=cast(
                Literal["user_model", "platform_model"], params["model_source"]
            ),
            model_ref=cast(str, params["model_ref"]),
            llm_client=llm_client,
            context_budget=cast(ContextBudget, params["budget"]),
        )
        return [ExtractedEntity(name=c.name, kind=c.kind) for c in candidates]

    report = await run_conll2003_anchor(
        _extractor, n_samples=n_samples, hf_cache_dir=hf_cache
    )

    logger.info(
        "CoNLL-2003 anchor: n=%d avg_extracted=%.1f avg_gold=%.1f P=%.3f R=%.3f F1=%.3f sanity=%s",
        report.n_samples,
        report.avg_n_extracted,
        report.avg_n_gold,
        report.precision,
        report.recall,
        report.f1,
        report.passes_sanity_floor,
    )
    print(
        f"\nCoNLL-2003 anchor: P={report.precision:.3f} R={report.recall:.3f} F1={report.f1:.3f}"
        f" (n={report.n_samples}, extracted avg {report.avg_n_extracted:.1f} vs gold {report.avg_n_gold:.1f})"
    )
    print(f"  per_class_f1: {json.dumps(report.per_class_f1, indent=2)}")

    dump_dir = _env("KNOWLEDGE_EVAL_DUMP_PATH")
    if dump_dir:
        out = write_anchor_report(report, Path(dump_dir))
        print(f"  report written: {out}")

    assert report.passes_sanity_floor, (
        f"Sanity floor failed (spec HIGH-1): {report.sanity_floor_reason}. "
        f"Extractor likely regressed to empty output. F1={report.f1:.3f}, "
        f"avg_n_extracted={report.avg_n_extracted:.1f}, avg_n_gold={report.avg_n_gold:.1f}."
    )


@pytest.mark.quality
@pytest.mark.asyncio
async def test_docred_anchor_passes_sanity_floor() -> None:
    """Run DocRED unlabeled-triple anchor + assert sanity floor (spec HIGH-1).

    Uses our gather_relations_events_facts pipeline + maps the resulting
    LLMRelationCandidate triples down to (subject, object) name pairs.
    """

    params = _resolve_eval_params()
    if params is None:
        pytest.skip("KNOWLEDGE_EVAL_MODEL + KNOWLEDGE_EVAL_USER_ID required")
    n_samples = int(_env("KNOWLEDGE_EVAL_ANCHOR_N_DOCRED", "100") or 100)
    hf_cache = _env("HF_DATASETS_CACHE")

    llm_client = get_llm_client()

    async def _triple_extractor(text: str) -> list[ExtractedTriple]:
        # DocRED scoring is relation-only; we still need entities from
        # extract_entities first because gather_relations_events_facts requires
        # them. This is fine — DocRED's input is article text with no pre-
        # provided entity hints, matching production flow.
        entities = await extract_entities(
            text=text,
            known_entities=[],
            user_id=cast(str, params["user_id"]),
            project_id=None,
            model_source=cast(
                Literal["user_model", "platform_model"], params["model_source"]
            ),
            model_ref=cast(str, params["model_ref"]),
            llm_client=llm_client,
            context_budget=cast(ContextBudget, params["budget"]),
        )
        if not entities:
            return []
        relations, _events, _facts = await gather_relations_events_facts(
            text=text,
            entities=entities,
            known_entities=[],
            user_id=cast(str, params["user_id"]),
            project_id=None,
            model_source=cast(
                Literal["user_model", "platform_model"], params["model_source"]
            ),
            model_ref=cast(str, params["model_ref"]),
            llm_client=llm_client,
            context_budget=cast(ContextBudget, params["budget"]),
        )
        return [ExtractedTriple(subject=r.subject, object_=r.object) for r in relations]

    report = await run_docred_anchor(
        _triple_extractor, n_samples=n_samples, hf_cache_dir=hf_cache
    )

    logger.info(
        "DocRED anchor: n=%d avg_extracted=%.1f avg_gold=%.1f P=%.3f R=%.3f F1=%.3f sanity=%s",
        report.n_samples,
        report.avg_n_extracted,
        report.avg_n_gold,
        report.precision,
        report.recall,
        report.f1,
        report.passes_sanity_floor,
    )
    print(
        f"\nDocRED anchor (unlabeled): P={report.precision:.3f} R={report.recall:.3f} F1={report.f1:.3f}"
        f" (n={report.n_samples}, extracted avg {report.avg_n_extracted:.1f} vs gold {report.avg_n_gold:.1f})"
    )

    dump_dir = _env("KNOWLEDGE_EVAL_DUMP_PATH")
    if dump_dir:
        out = write_anchor_report(report, Path(dump_dir))
        print(f"  report written: {out}")

    assert report.passes_sanity_floor, (
        f"Sanity floor failed (spec HIGH-1): {report.sanity_floor_reason}. "
        f"Relation extractor likely regressed to empty. F1={report.f1:.3f}, "
        f"avg_n_extracted={report.avg_n_extracted:.1f}, avg_n_gold={report.avg_n_gold:.1f}."
    )
