"""Resumable 3-judge ensemble re-judge over a saved extraction dump.

Why this exists (cycle 73e → D-PASS2-WRITER-AUTOCREATE-F1-EVAL):
`test_judge_eval.py::test_llm_judge_ensemble` runs all judges in one process
and calls `persist_verdicts` ONCE at the very end. When knowledge-service got
OOM-killed mid-ensemble in session 73 (LM Studio JIT model load → host memory
pressure → Docker Desktop kills the heaviest container), every judge's verdicts
were lost because nothing was persisted until all three finished.

This runner fixes BOTH failure modes:

1. **Persist-per-judge** — each judge's `judge_verdicts_<label>.json` is written
   to dump_root the instant that judge completes. A crash during judge N only
   loses judge N's in-flight work; judges < N are already on disk.

2. **Resume** — on restart, any judge whose verdict file already exists with
   `judge_status == "complete"` is reloaded from disk and skipped, so you can
   re-invoke until all three are present.

3. **Host orchestration** — run this from host Python (not in-container). The
   orchestrator process lives outside the Docker VM, so the OOM-killer that
   targets knowledge-service can't kill it. Path:
     host python  →  provider-registry (localhost:8208)  →  LM Studio (1234)
   knowledge-service is not in the loop at all.

After all judges are present it assembles + persists `judge_ensemble_report.json`
(Fleiss κ, D11 acceptance, D12 bias). Then run `compute_ensemble_macros.py` for
the per-judge macro P/R/F1 table.

Env (mirrors test_judge_eval.py::test_llm_judge_ensemble):
    KNOWLEDGE_EVAL_ENSEMBLE_JUDGES   comma-sep judge model UUIDs (>=2)
    KNOWLEDGE_EVAL_ENSEMBLE_LABELS   comma-sep labels (default gemma,qwen-30b,claude-4.7-opus)
    KNOWLEDGE_EVAL_USER_ID           BYOK owner user UUID
    KNOWLEDGE_EVAL_JUDGE_MODEL_SOURCE  default "user_model"
    KNOWLEDGE_JUDGE_DUMP_PATH        dump dir with per-chapter actual.json/expected.json

Usage (from services/knowledge-service, host):
    KNOWLEDGE_EVAL_ENSEMBLE_JUDGES=<g>,<q>,<c> KNOWLEDGE_EVAL_USER_ID=<u> \
    KNOWLEDGE_JUDGE_DUMP_PATH=tests/quality/eval_runs/c73e-autocreate-on \
        python -m tests.quality.run_rejudge_resumable
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from app.clients.llm_client import get_llm_client

try:
    from tests.quality.judge_ensemble import (
        JudgeRunResult,
        JudgeVerdict,
        assemble_report,
        persist_ensemble_report,
        persist_verdicts,
    )
    from tests.quality.llm_judge import run_dump_judge
except ModuleNotFoundError:  # pragma: no cover - container path
    from quality.judge_ensemble import (  # type: ignore[no-redef]
        JudgeRunResult,
        JudgeVerdict,
        assemble_report,
        persist_ensemble_report,
        persist_verdicts,
    )
    from quality.llm_judge import run_dump_judge  # type: ignore[no-redef]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("rejudge_resumable")

GOLDEN_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "golden_chapters"

_DEFAULT_LABELS = ["gemma", "qwen-30b", "claude-4.7-opus"]


def _safe_label(label: str) -> str:
    """Match persist_verdicts' filename sanitization exactly."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in label)


def _load_source_text(chapter: str) -> str | None:
    path = GOLDEN_ROOT / chapter / "chapter.txt"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _load_persisted_judge(path: Path) -> JudgeRunResult | None:
    """Reload a previously-persisted judge_verdicts_<label>.json into a
    JudgeRunResult. Returns None if the file is missing, malformed, or the
    judge did not finish (status != complete) — caller re-runs in that case."""
    import json

    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        logger.warning("could not read %s (%s) — will re-run judge", path, e)
        return None
    if data.get("judge_status") != "complete":
        logger.info(
            "%s has status=%s (not complete) — will re-run judge",
            path.name,
            data.get("judge_status"),
        )
        return None
    verdicts = [
        JudgeVerdict(
            chapter=v["chapter"],
            category=v["category"],
            kind=v["kind"],
            idx=v["idx"],
            verdict=v["verdict"],
        )
        for v in data.get("verdicts", [])
    ]
    return JudgeRunResult(
        judge_uuid=data["judge_uuid"],
        judge_label=data["judge_label"],
        judge_status=data["judge_status"],
        failure_reason=data.get("failure_reason", ""),
        chapters_complete=data.get("chapters_complete", []),
        chapters_incomplete=data.get("chapters_incomplete", []),
        verdicts=verdicts,
    )


async def main() -> int:
    ensemble_env = os.environ.get("KNOWLEDGE_EVAL_ENSEMBLE_JUDGES", "").strip()
    if not ensemble_env:
        print("ERROR: KNOWLEDGE_EVAL_ENSEMBLE_JUDGES required", file=sys.stderr)
        return 2
    user_id = os.environ.get("KNOWLEDGE_EVAL_USER_ID", "").strip()
    if not user_id:
        print("ERROR: KNOWLEDGE_EVAL_USER_ID required", file=sys.stderr)
        return 2
    model_source = os.environ.get("KNOWLEDGE_EVAL_JUDGE_MODEL_SOURCE", "user_model")
    dump_env = (
        os.environ.get("KNOWLEDGE_JUDGE_DUMP_PATH")
        or os.environ.get("KNOWLEDGE_EVAL_DUMP_PATH")
        or ""
    ).strip()
    if not dump_env:
        print("ERROR: KNOWLEDGE_JUDGE_DUMP_PATH required", file=sys.stderr)
        return 2
    dump_root = Path(dump_env).resolve()
    if not dump_root.is_dir():
        print(f"ERROR: dump path not found: {dump_root}", file=sys.stderr)
        return 2

    judge_uuids = [s.strip() for s in ensemble_env.split(",") if s.strip()]
    if len(judge_uuids) < 2:
        print(f"ERROR: ensemble needs >=2 judges; got {len(judge_uuids)}", file=sys.stderr)
        return 2

    label_env = os.environ.get("KNOWLEDGE_EVAL_ENSEMBLE_LABELS", "").strip()
    if label_env:
        labels = [s.strip() for s in label_env.split(",")]
        if len(labels) != len(judge_uuids):
            print("ERROR: ENSEMBLE_LABELS count must match JUDGES count", file=sys.stderr)
            return 2
    else:
        labels = _DEFAULT_LABELS[: len(judge_uuids)] + judge_uuids[len(_DEFAULT_LABELS):]

    judges = list(zip(judge_uuids, labels))
    logger.info(
        "resumable re-judge: %d judges over %s", len(judges), dump_root
    )
    for uuid, lbl in judges:
        logger.info("  judge %s (%s)", lbl, uuid[:8])

    client = get_llm_client()
    results: list[JudgeRunResult] = []

    for uuid, label in judges:
        verdict_path = dump_root / f"judge_verdicts_{_safe_label(label)}.json"
        resumed = _load_persisted_judge(verdict_path)
        if resumed is not None:
            logger.info(
                "RESUME: judge %s already complete on disk (%d verdicts) — skipping",
                label,
                len(resumed.verdicts),
            )
            results.append(resumed)
            continue

        logger.info("RUN: judge %s starting (model JIT-load may take minutes)", label)
        try:
            result = await run_dump_judge(
                client,
                judge_model_uuid=uuid,
                judge_label=label,
                user_id=user_id,
                model_source=model_source,
                dump_root=dump_root,
                source_text_loader=_load_source_text,
            )
        except Exception as e:  # noqa: BLE001 — record as failed, persist, continue
            logger.error("judge %s raised before completion: %s", label, e, exc_info=True)
            result = JudgeRunResult(
                judge_uuid=uuid,
                judge_label=label,
                judge_status="failed",
                failure_reason=f"{type(e).__name__}: {e}",
            )

        # Persist this judge IMMEDIATELY — survives a crash on the next judge.
        persist_verdicts([result], dump_root)
        logger.info(
            "PERSISTED judge %s: status=%s verdicts=%d complete=%d incomplete=%d",
            label,
            result.judge_status,
            len(result.verdicts),
            len(result.chapters_complete),
            len(result.chapters_incomplete),
        )
        results.append(result)

    report = assemble_report(results)
    report_path = persist_ensemble_report(report, dump_root)

    print("\n=== Ensemble re-judge complete ===")
    print(f"report: {report_path}")
    print(f"acceptable (>=2 complete): {report.ensemble_acceptable}")
    kappa = report.fleiss_kappa
    print(
        f"fleiss_kappa: {kappa if kappa is None else round(kappa, 3)} "
        f"({report.fleiss_kappa_interpretation}, basis={report.fleiss_kappa_basis})"
    )
    for uuid, status in report.judge_status.items():
        lbl = report.judge_labels.get(uuid, uuid[:8])
        reason = report.judge_failure_reasons.get(uuid, "")
        print(f"  - {lbl}: {status}{(' — ' + reason) if reason else ''}")

    if not report.ensemble_acceptable:
        print("\nWARNING: ensemble NOT acceptable (<2 judges complete).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
