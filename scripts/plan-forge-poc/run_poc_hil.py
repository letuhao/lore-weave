#!/usr/bin/env python3
"""PlanForge HIL POC — checkpoint + surgical refine loop."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.compile import compile_artifacts
from plan_forge.eval_hil import format_hil_report, measure_round, validate_spec_artifacts
from plan_forge.llm_client import LMStudioClient
from plan_forge.propose_llm import analyze_document, materialize_from_analyze
from plan_forge.refine import accept_refine, refine_analyze, refine_spec

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"
DEFAULT_SCRIPT = ROOT / "fixtures" / "hil_eval_script.yaml"
MAX_REFINES_PER_CHECKPOINT = 2


def _load_script(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _revisions_for_checkpoint(script: dict[str, Any], checkpoint: str) -> list[dict[str, Any]]:
    ledger = list(script.get("constraint_ledger") or [])
    out: list[dict[str, Any]] = []
    for rev in script.get("revisions") or []:
        if rev.get("checkpoint") != checkpoint:
            continue
        merged = {**rev, "version": 1, "constraint_ledger": list(ledger)}
        out.append(merged)
    return out


def _append_ledger(ledger: list[str], instruction: str) -> None:
    entry = instruction.strip()[:200]
    if entry and entry not in ledger:
        ledger.append(entry)


def _run_validate_compile(out: Path, spec: dict[str, Any], fixture: Path) -> int:
    py = sys.executable
    spec_path = out / "novel_system_spec.hil.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(
        [py, str(ROOT / "decompose.py"), str(spec_path), "-o", str(out / "plan_graph.hil.json")],
        check=True,
    )
    subprocess.run(
        [
            py,
            str(ROOT / "compile.py"),
            str(spec_path),
            "-o",
            str(out),
            "--arc",
            "arc_2",
            "--mock-llm",
        ],
        check=True,
    )
    validation = validate_spec_artifacts(spec, fixture, GOLDEN)
    report = format_hil_report([], baseline=spec, final=spec, final_validation=validation)
    # write validation slice only
    val_path = out / "validation_report.hil.md"
    lines = ["# PlanForge HIL Validation", "", f"**Overall:** {'PASS' if validation['all_pass'] else 'FAIL'}", ""]
    for k, v in validation.get("criteria", {}).items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    val_path.write_text("\n".join(lines), encoding="utf-8")
    (out / "validation_result.hil.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if validation["all_pass"] else 1


def run_hil(
    fixture: Path,
    script_path: Path,
    output_dir: Path,
    *,
    interactive: bool = False,
) -> int:
    out = output_dir
    out.mkdir(parents=True, exist_ok=True)
    io_dir = out / "hil_io"
    script = _load_script(script_path)
    ledger: list[str] = list(script.get("constraint_ledger") or [])

    client = LMStudioClient(io_dir=io_dir)
    print("LM Studio health check...")
    client.health_check()

    print("Step 1: analyze...")
    analyze, checksum = analyze_document(fixture, client=client, io_dir=io_dir)
    (out / "plan_analyze.json").write_text(json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8")

    rounds: list[dict[str, Any]] = []
    package: dict[str, Any] | None = None

    # Checkpoint 1 — analyze
    for i, rev in enumerate(_revisions_for_checkpoint(script, "analyze")[:MAX_REFINES_PER_CHECKPOINT]):
        if interactive:
            ans = input(f"Apply analyze revision {i + 1}? [y/N/a=approve] ").strip().lower()
            if ans in ("a", "approve", ""):
                break
            if ans not in ("y", "yes"):
                continue
        before = analyze
        rev = {**rev, "constraint_ledger": list(ledger)}
        candidate = refine_analyze(before, rev, client=client)
        accept = accept_refine(before, candidate, rev, package=package)
        analyze = candidate if accept.accepted else before
        if accept.accepted:
            _append_ledger(ledger, rev.get("instruction", ""))
        rounds.append(measure_round(label=f"analyze_{i + 1}", before=before, after=analyze, revision=rev, accept=accept, package=package))
        (out / "plan_analyze.json").write_text(json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  analyze refine {i + 1}: {'accepted' if accept.accepted else 'rejected'} {accept.reasons}")

    print("Step 2: materialize...")
    spec = materialize_from_analyze(analyze, checksum, client=client, io_dir=io_dir)
    baseline_spec = json.loads(json.dumps(spec))
    package = compile_artifacts(spec, arc_id="arc_2")["planning_package"]
    val_before = validate_spec_artifacts(spec, fixture, GOLDEN)
    criteria_before = val_before.get("criteria", {})

    # Checkpoint 2 — spec
    for i, rev in enumerate(_revisions_for_checkpoint(script, "spec")[:MAX_REFINES_PER_CHECKPOINT]):
        if interactive:
            ans = input(f"Apply spec revision {i + 1}? [y/N/a=approve] ").strip().lower()
            if ans in ("a", "approve", ""):
                break
            if ans not in ("y", "yes"):
                continue
        before = spec
        rev = {**rev, "constraint_ledger": list(ledger)}
        candidate = refine_spec(before, rev, client=client, source_checksum=checksum)
        val_after_cand = validate_spec_artifacts(candidate, fixture, GOLDEN)
        accept = accept_refine(
            before,
            candidate,
            rev,
            package=package,
            criteria_before=criteria_before,
            criteria_after=val_after_cand.get("criteria", {}),
        )
        spec = candidate if accept.accepted else before
        if accept.accepted:
            _append_ledger(ledger, rev.get("instruction", ""))
            package = compile_artifacts(spec, arc_id="arc_2")["planning_package"]
            criteria_before = val_after_cand.get("criteria", criteria_before)
        rounds.append(
            measure_round(
                label=f"spec_{i + 1}",
                before=before,
                after=spec,
                revision=rev,
                accept=accept,
                package=package,
                criteria_before=val_before.get("criteria") if i == 0 else criteria_before,
                criteria_after=val_after_cand.get("criteria", {}),
            )
        )
        print(f"  spec refine {i + 1}: {'accepted' if accept.accepted else 'rejected'} {accept.reasons}")

    (out / "novel_system_spec.hil.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    final_validation = validate_spec_artifacts(spec, fixture, GOLDEN)

    report = format_hil_report(
        rounds,
        baseline=baseline_spec,
        final=spec,
        final_validation=final_validation,
    )
    (out / "hil_eval_report.md").write_text(report, encoding="utf-8")
    print(report)

    rc = _run_validate_compile(out, spec, fixture)
    print(f"\nHIL POC complete → {out}")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge HIL POC")
    p.add_argument("-o", "--output-dir", type=Path, default=ROOT / "out")
    p.add_argument("--fixture", type=Path, default=FIXTURE)
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    p.add_argument("--interactive", action="store_true")
    args = p.parse_args()
    return run_hil(args.fixture, args.script, args.output_dir, interactive=args.interactive)


if __name__ == "__main__":
    raise SystemExit(main())
