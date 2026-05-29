"""Cycle 72 Phase 3 — apply precision filter to the c70a saved fixture.

Loads each chapter's Pass A `actual.json` from the c70a fixture
(`tests/quality/eval_runs/c70a/<chapter>/`), runs
`apply_precision_filter` against the chapter source text using
claude-4.7-opus as the filter model, and writes the filtered
`actual.json` to a new variant dump dir
(`tests/quality/eval_runs/c72b/` for keep policy, `c72c/` for drop).

Per spec HIGH-1 round-1 fold: the Pass A source is the SAVED c70a
extraction dump, NOT a fresh extraction — eliminates LLM
nondeterminism from the A/B comparison.

Usage (from inside infra-knowledge-service-1):

    KNOWLEDGE_EVAL_USER_ID=<uuid> \
    KNOWLEDGE_C72_FILTER_MODEL_UUID=<claude-4.7-opus-uuid> \
    KNOWLEDGE_C72_VARIANT=c72b \
        python -m tests.quality.run_c72_filter

Output structure (per variant):

    tests/quality/eval_runs/<variant>/
        <chapter>/
            actual.json        (filtered candidates)
            expected.json      (copy from c70a)
            attribution.json   (copy from c70a)
        c72_filter_run_summary.json   (per-chapter stats)

Then point `KNOWLEDGE_JUDGE_DUMP_PATH` at the new dump dir and re-run
the ensemble judge via `pytest tests/quality/test_judge_eval.py
-k ensemble --run-quality`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Literal

from loreweave_extraction import (
    FilterDecision,
    PrecisionFilterConfig,
    apply_precision_filter,
    load_candidates_from_dump,
)

from app.clients.llm_client import get_llm_client

logger = logging.getLogger("c72_filter")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Paths assume the script runs from the knowledge-service container
# where /app/tests is mounted. Adjust if running outside.
_TESTS_ROOT = Path(__file__).resolve().parent.parent
_C70A_ROOT_DEFAULT = _TESTS_ROOT / "quality" / "eval_runs" / "c70a"
_OUT_ROOT_DEFAULT = _TESTS_ROOT / "quality" / "eval_runs"
_FIXTURES_ROOT_DEFAULT = _TESTS_ROOT / "fixtures" / "golden_chapters"


def _resolve_paths() -> tuple[Path, Path, Path]:
    """Resolve c70a source dir + output root + chapter-fixtures dir.

    Env overrides (useful when running inside a container without the
    repo fixture mounted — point at /tmp/eval_dump_cycle70 directly):
        KNOWLEDGE_C70A_PATH:     override c70a Pass A dump dir
        KNOWLEDGE_C72_OUT_ROOT:  override variant output root
        KNOWLEDGE_FIXTURES_ROOT: override golden_chapters dir
    """
    c70a = Path(
        os.environ.get("KNOWLEDGE_C70A_PATH", str(_C70A_ROOT_DEFAULT))
    )
    out_root = Path(
        os.environ.get("KNOWLEDGE_C72_OUT_ROOT", str(_OUT_ROOT_DEFAULT))
    )
    fixtures = Path(
        os.environ.get("KNOWLEDGE_FIXTURES_ROOT", str(_FIXTURES_ROOT_DEFAULT))
    )
    return c70a, out_root, fixtures


def _load_chapter_text(fixtures_root: Path, chapter: str) -> str | None:
    """Load chapter.txt from the golden_chapters fixture set."""
    path = fixtures_root / chapter / "chapter.txt"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _build_config(
    *,
    model_ref: str,
    partial_policy: Literal["keep", "drop"],
) -> PrecisionFilterConfig:
    return PrecisionFilterConfig(
        model_ref=model_ref,
        model_source="user_model",
        partial_policy=partial_policy,
        categories=("entity", "relation", "event"),
        # max_items_per_batch + transient_retry_budget use defaults
        # (3 + 1) — calibrated for reasoning-token bursts; tune in
        # follow-up if filter_coverage shows truncation.
    )


async def _filter_one_chapter(
    chapter: str,
    *,
    c70a_chapter_dir: Path,
    fixtures_root: Path,
    out_dir: Path,
    user_id: str,
    config: PrecisionFilterConfig,
    llm_client,
) -> dict:
    """Filter a single chapter's Pass A dump.

    Returns per-chapter stats for the run summary.
    """
    started = time.perf_counter()
    text = _load_chapter_text(fixtures_root, chapter)
    if text is None:
        logger.warning("%s: no chapter.txt found, skipping", chapter)
        return {"chapter": chapter, "status": "skipped_no_text"}

    candidates = load_candidates_from_dump(c70a_chapter_dir)
    pre = {
        "entities": len(candidates.entities),
        "relations": len(candidates.relations),
        "events": len(candidates.events),
        "facts": len(candidates.facts),
    }

    decisions_counter: dict[tuple[str, str], int] = {}

    def _on_decision(d: FilterDecision) -> None:
        key = (d.category, d.verdict)
        decisions_counter[key] = decisions_counter.get(key, 0) + 1

    try:
        filtered = await apply_precision_filter(
            candidates,
            text=text,
            config=config,
            user_id=user_id,
            llm_client=llm_client,
            on_decision=_on_decision,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s: filter raised unexpectedly", chapter)
        return {"chapter": chapter, "status": "filter_error", "error": str(exc)}

    post = {
        "entities": len(filtered.entities),
        "relations": len(filtered.relations),
        "events": len(filtered.events),
        "facts": len(filtered.facts),
    }

    # Write the filtered actual.json
    out_chapter_dir = out_dir / chapter
    out_chapter_dir.mkdir(parents=True, exist_ok=True)
    actual_payload = {
        "entities": [e.model_dump(mode="json") for e in filtered.entities],
        "relations": [r.model_dump(mode="json") for r in filtered.relations],
        "events": [ev.model_dump(mode="json") for ev in filtered.events],
        "facts": [f.model_dump(mode="json") for f in filtered.facts],
    }
    (out_chapter_dir / "actual.json").write_text(
        json.dumps(actual_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Copy expected.json + attribution.json from c70a unchanged
    for sidecar in ("expected.json", "attribution.json"):
        src = c70a_chapter_dir / sidecar
        if src.is_file():
            shutil.copyfile(src, out_chapter_dir / sidecar)

    elapsed = time.perf_counter() - started
    decisions_serializable = {
        f"{cat}|{verdict}": n for (cat, verdict), n in decisions_counter.items()
    }
    logger.info(
        "%s: filter %s in %.1fs  ent %d->%d  rel %d->%d  evt %d->%d  "
        "coverage ent=%.0f%% rel=%.0f%% evt=%.0f%%",
        chapter, filtered.filter_status, elapsed,
        pre["entities"], post["entities"],
        pre["relations"], post["relations"],
        pre["events"], post["events"],
        filtered.filter_coverage.get("entity", 1.0) * 100,
        filtered.filter_coverage.get("relation", 1.0) * 100,
        filtered.filter_coverage.get("event", 1.0) * 100,
    )

    return {
        "chapter": chapter,
        "status": filtered.filter_status,
        "pre_counts": pre,
        "post_counts": post,
        "filter_coverage": filtered.filter_coverage,
        "decisions": decisions_serializable,
        "duration_sec": round(elapsed, 1),
    }


async def main() -> int:
    variant = os.environ.get("KNOWLEDGE_C72_VARIANT", "c72b").strip()
    if variant not in ("c72b", "c72c"):
        print(
            f"ERROR: KNOWLEDGE_C72_VARIANT must be 'c72b' or 'c72c'; "
            f"got {variant!r}",
            file=sys.stderr,
        )
        return 1

    user_id = os.environ.get("KNOWLEDGE_EVAL_USER_ID", "").strip()
    if not user_id:
        print(
            "ERROR: KNOWLEDGE_EVAL_USER_ID required (gateway user UUID).",
            file=sys.stderr,
        )
        return 1

    model_ref = os.environ.get(
        "KNOWLEDGE_C72_FILTER_MODEL_UUID",
        "019e5650-eca7-78c2-985d-465aa3bce1ce",  # default: huihui-claude-4.7-opus
    ).strip()

    partial_policy: Literal["keep", "drop"] = "keep" if variant == "c72b" else "drop"
    config = _build_config(model_ref=model_ref, partial_policy=partial_policy)

    c70a_root, out_root_base, fixtures_root = _resolve_paths()
    out_root = out_root_base / variant
    out_root.mkdir(parents=True, exist_ok=True)

    chapter_dirs = sorted(
        p for p in c70a_root.iterdir()
        if p.is_dir() and (p / "actual.json").is_file()
    )
    if not chapter_dirs:
        print(f"ERROR: no chapter dumps under {c70a_root}", file=sys.stderr)
        return 1

    logger.info(
        "c72 filter run starting: variant=%s policy=%s model=%s chapters=%d",
        variant, partial_policy, model_ref, len(chapter_dirs),
    )

    client = get_llm_client()
    overall_started = time.perf_counter()
    summary: list[dict] = []
    for c70a_chapter_dir in chapter_dirs:
        chapter = c70a_chapter_dir.name
        result = await _filter_one_chapter(
            chapter,
            c70a_chapter_dir=c70a_chapter_dir,
            fixtures_root=fixtures_root,
            out_dir=out_root,
            user_id=user_id,
            config=config,
            llm_client=client,
        )
        summary.append(result)

    overall_elapsed = time.perf_counter() - overall_started

    summary_path = out_root / "c72_filter_run_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "variant": variant,
                "partial_policy": partial_policy,
                "filter_model_ref": model_ref,
                "elapsed_sec": round(overall_elapsed, 1),
                "chapters": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logger.info(
        "c72 filter run complete: variant=%s elapsed=%.1fs summary=%s",
        variant, overall_elapsed, summary_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
