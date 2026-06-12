"""Cycle 73d Phase 3 — apply entity recovery (+ optional filter) to the
c70a saved fixture and emit a c73d variant dump for ensemble re-judge.

Pipeline (mirrors `extract_pass2` chain order):
  1. Load c70a chapter dump as Pass A
  2. Recover missing entities (3-tier glossary→hints→LLM)
  3. (Optional) apply precision filter
  4. Dump c73d variant `actual.json`

Per cycle 73d ship gate: also exercises the writer cascade-simulator
in a downstream step so realized F1 can be re-judged with the
ensemble.

Usage:
    KNOWLEDGE_EVAL_USER_ID=<uuid> \\
    KNOWLEDGE_C73D_RECOVERY_MODEL_UUID=<claude-4.7-opus-uuid> \\
    KNOWLEDGE_C73D_VARIANT=c73d-recov-only \\
        python -m tests.quality.run_c73d_recovery

Variants supported:
  - c73d-recov-only      : recovery only (no precision filter)
  - c73d-recov-plus-rel  : recovery + relation-only filter (matches c73b-drop)
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

from loreweave_extraction import (
    EntityRecoveryConfig,
    PrecisionFilterConfig,
    RecoveryDecision,
    apply_precision_filter,
    load_candidates_from_dump,
    recover_missing_entities,
)

from app.clients.llm_client import get_llm_client

logger = logging.getLogger("c73d_recovery")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_TESTS_ROOT = Path(__file__).resolve().parent.parent
_C70A_ROOT_DEFAULT = _TESTS_ROOT / "quality" / "eval_runs" / "c70a"
_OUT_ROOT_DEFAULT = _TESTS_ROOT / "quality" / "eval_runs"
_FIXTURES_ROOT_DEFAULT = _TESTS_ROOT / "fixtures" / "golden_chapters"


def _resolve_paths() -> tuple[Path, Path, Path]:
    return (
        Path(os.environ.get("KNOWLEDGE_C70A_PATH", str(_C70A_ROOT_DEFAULT))),
        Path(os.environ.get("KNOWLEDGE_C72_OUT_ROOT", str(_OUT_ROOT_DEFAULT))),
        Path(os.environ.get("KNOWLEDGE_FIXTURES_ROOT", str(_FIXTURES_ROOT_DEFAULT))),
    )


def _load_chapter_text(fixtures_root: Path, chapter: str) -> str | None:
    p = fixtures_root / chapter / "chapter.txt"
    return p.read_text(encoding="utf-8") if p.is_file() else None


async def _process_chapter(
    chapter: str,
    *,
    c70a_chapter_dir: Path,
    fixtures_root: Path,
    out_dir: Path,
    user_id: str,
    recovery_config: EntityRecoveryConfig,
    filter_config: PrecisionFilterConfig | None,
    llm_client,
) -> dict:
    started = time.perf_counter()
    text = _load_chapter_text(fixtures_root, chapter)
    if text is None:
        return {"chapter": chapter, "status": "skipped_no_text"}

    candidates = load_candidates_from_dump(c70a_chapter_dir)
    pre = {
        "entities": len(candidates.entities),
        "relations": len(candidates.relations),
        "events": len(candidates.events),
        "facts": len(candidates.facts),
    }

    recovery_decisions: list[dict] = []

    def _on_recovery(d: RecoveryDecision) -> None:
        recovery_decisions.append({
            "name": d.name, "verdict": d.verdict, "source": d.source,
            "kind": d.kind,
        })

    # Step 1 — recovery
    enriched = await recover_missing_entities(
        candidates,
        text=text,
        config=recovery_config,
        user_id=user_id,
        llm_client=llm_client,
        on_decision=_on_recovery,
    )

    # Step 2 — optional filter
    if filter_config is not None:
        enriched = await apply_precision_filter(
            enriched,
            text=text,
            config=filter_config,
            user_id=user_id,
            llm_client=llm_client,
        )

    post = {
        "entities": len(enriched.entities),
        "relations": len(enriched.relations),
        "events": len(enriched.events),
        "facts": len(enriched.facts),
    }

    # Dump
    out_chapter_dir = out_dir / chapter
    out_chapter_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "entities": [e.model_dump(mode="json") for e in enriched.entities],
        "relations": [r.model_dump(mode="json") for r in enriched.relations],
        "events": [ev.model_dump(mode="json") for ev in enriched.events],
        "facts": [f.model_dump(mode="json") for f in enriched.facts],
    }
    (out_chapter_dir / "actual.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    for sidecar in ("expected.json", "attribution.json"):
        sp = c70a_chapter_dir / sidecar
        if sp.is_file():
            shutil.copyfile(sp, out_chapter_dir / sidecar)

    elapsed = time.perf_counter() - started
    n_recovered = sum(1 for d in recovery_decisions if d["verdict"] == "entity")
    n_dropped = sum(1 for d in recovery_decisions if d["verdict"] == "abstract")
    logger.info(
        "%s: recovery+filter in %.1fs  ent %d->%d (+%d recovered)  "
        "rel %d->%d (%d abstract-dropped, %d filter-effect)",
        chapter, elapsed,
        pre["entities"], post["entities"], n_recovered,
        pre["relations"], post["relations"], n_dropped,
        (pre["relations"] - n_dropped) - post["relations"],
    )

    return {
        "chapter": chapter,
        "pre": pre, "post": post,
        "recovery_decisions": recovery_decisions,
        "duration_sec": round(elapsed, 1),
    }


async def main() -> int:
    variant = os.environ.get("KNOWLEDGE_C73D_VARIANT", "c73d-recov-only").strip()
    if variant not in ("c73d-recov-only", "c73d-recov-plus-rel"):
        print(
            f"ERROR: KNOWLEDGE_C73D_VARIANT must be 'c73d-recov-only' or "
            f"'c73d-recov-plus-rel'; got {variant!r}",
            file=sys.stderr,
        )
        return 1

    user_id = os.environ.get("KNOWLEDGE_EVAL_USER_ID", "").strip()
    if not user_id:
        print("ERROR: KNOWLEDGE_EVAL_USER_ID required", file=sys.stderr)
        return 1

    model_ref = os.environ.get(
        "KNOWLEDGE_C73D_RECOVERY_MODEL_UUID",
        "019e5650-eca7-78c2-985d-465aa3bce1ce",
    ).strip()

    recovery_config = EntityRecoveryConfig(
        model_ref=model_ref,
        model_source="user_model",
        max_items_per_batch=5,
    )

    filter_config: PrecisionFilterConfig | None = None
    if variant == "c73d-recov-plus-rel":
        filter_config = PrecisionFilterConfig(
            model_ref=model_ref,
            model_source="user_model",
            partial_policy="drop",
            categories=("relation",),
        )

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
        "c73d run starting: variant=%s recovery_model=%s filter=%s chapters=%d",
        variant, model_ref,
        "relation-only-drop" if filter_config else "none",
        len(chapter_dirs),
    )

    client = get_llm_client()
    overall_started = time.perf_counter()
    summary: list[dict] = []
    for cd in chapter_dirs:
        summary.append(await _process_chapter(
            cd.name,
            c70a_chapter_dir=cd,
            fixtures_root=fixtures_root,
            out_dir=out_root,
            user_id=user_id,
            recovery_config=recovery_config,
            filter_config=filter_config,
            llm_client=client,
        ))

    overall_elapsed = time.perf_counter() - overall_started
    summary_path = out_root / "c73d_run_summary.json"
    summary_path.write_text(
        json.dumps({
            "variant": variant,
            "recovery_model_ref": model_ref,
            "has_filter": filter_config is not None,
            "elapsed_sec": round(overall_elapsed, 1),
            "chapters": summary,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "c73d run complete: variant=%s elapsed=%.1fs summary=%s",
        variant, overall_elapsed, summary_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
