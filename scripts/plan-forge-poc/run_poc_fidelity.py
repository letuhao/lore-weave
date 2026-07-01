#!/usr/bin/env python3
"""PlanForge Fidelity POC — coverage reports + HIL completeness + optional elaboration."""

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
from plan_forge.coverage import (
    build_section_map,
    coverage_report_analyze,
    coverage_report_spec,
    load_coverage_context,
    write_fidelity_artifacts,
)
from plan_forge.elaborate import consistency_audit, elaborate_spec, section_excerpts_for_elaboration
from plan_forge.eval_fidelity import evaluate_elaboration_fidelity, load_fidelity_config
from plan_forge.eval_hil import format_hil_report, measure_round, validate_spec_artifacts
from plan_forge.llm_client import LMStudioClient
from plan_forge.propose_llm import analyze_document, materialize_from_analyze
from plan_forge.refine import accept_refine, refine_analyze, refine_spec

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"
FIDELITY = ROOT / "fixtures" / "story-plan-v1.fidelity.yaml"
DEFAULT_SCRIPT = ROOT / "fixtures" / "hil_fidelity_script.yaml"
ELAB_SCRIPT = ROOT / "fixtures" / "hil_elaboration_script.yaml"
MAX_REFINES_PER_CHECKPOINT = 5


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


def _print_gaps(report: dict[str, Any], label: str) -> None:
    print(f"\n--- {label} fidelity: {report.get('score')} gate={report.get('gate_pass', 'n/a')} ---")
    for g in report.get("gaps") or []:
        print(f"  GAP: {g['id']} — {g['detail']}")
    for s in report.get("suggestions") or []:
        print(f"  SUGGEST: {s}")


def _run_validate_compile(out: Path, spec: dict[str, Any], fixture: Path) -> tuple[int, dict[str, Any]]:
    py = sys.executable
    spec_path = out / "novel_system_spec.fidelity.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(
        [py, str(ROOT / "decompose.py"), str(spec_path), "-o", str(out / "plan_graph.fidelity.json")],
        check=True,
    )
    subprocess.run(
        [py, str(ROOT / "compile.py"), str(spec_path), "-o", str(out), "--arc", "arc_2", "--mock-llm"],
        check=True,
    )
    validation = validate_spec_artifacts(spec, fixture, GOLDEN)
    val_path = out / "validation_report.fidelity.md"
    lines = ["# PlanForge Fidelity Validation", "", f"**Overall:** {'PASS' if validation['all_pass'] else 'FAIL'}", ""]
    for k, v in validation.get("criteria", {}).items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    val_path.write_text("\n".join(lines), encoding="utf-8")
    (out / "validation_result.fidelity.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rc = 0 if validation["all_pass"] else 1
    return rc, validation


def run_fidelity(
    fixture: Path,
    script_path: Path,
    output_dir: Path,
    *,
    interactive: bool = False,
    phase: str = "fidelity",
) -> int:
    out = output_dir
    out.mkdir(parents=True, exist_ok=True)
    io_dir = out / "fidelity_io"
    section_map, fidelity_cfg = load_coverage_context(fixture, FIDELITY)
    script = _load_script(script_path)
    ledger: list[str] = list(script.get("constraint_ledger") or [])

    gate_path = out / "fidelity_gate.json"
    if phase == "elaboration":
        if not gate_path.exists():
            print("ERROR: Phase B requires Phase A gate — run --phase fidelity first")
            return 2
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        if not gate.get("phase_a_pass"):
            print("ERROR: Phase A gate not PASS — cannot run elaboration")
            return 2
        spec_path = out / "novel_system_spec.fidelity.json"
        if not spec_path.exists():
            print("ERROR: missing novel_system_spec.fidelity.json")
            return 2
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        checksum = spec.get("meta", {}).get("source_checksum", "")
        return _run_elaboration(spec, checksum, section_map, fidelity_cfg, script, out, io_dir, interactive)

    client = LMStudioClient(io_dir=io_dir)
    print("LM Studio health check...")
    client.health_check()

    print("Step 1: analyze...")
    analyze, checksum = analyze_document(fixture, client=client, io_dir=io_dir)
    (out / "plan_analyze.json").write_text(json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8")

    analyze_report = coverage_report_analyze(analyze, section_map, fidelity_cfg)
    _print_gaps(analyze_report, "Analyze")
    write_fidelity_artifacts(out, analyze_report=analyze_report)

    rounds: list[dict[str, Any]] = []
    package: dict[str, Any] | None = None
    fidelity_before = analyze_report.get("score", 0.0)

    for i, rev in enumerate(_revisions_for_checkpoint(script, "analyze")[:MAX_REFINES_PER_CHECKPOINT]):
        if interactive:
            ans = input(f"Apply analyze revision {i + 1}? [Y/n/s=skip] ").strip().lower()
            if ans in ("n", "no", "s", "skip"):
                continue
        before = analyze
        rev = {**rev, "constraint_ledger": list(ledger)}
        candidate = refine_analyze(before, rev, client=client)
        cand_report = coverage_report_analyze(candidate, section_map, fidelity_cfg)
        accept = accept_refine(
            before,
            candidate,
            rev,
            package=package,
            fidelity_before=fidelity_before,
            fidelity_after=cand_report.get("score"),
        )
        analyze = candidate if accept.accepted else before
        if accept.accepted:
            _append_ledger(ledger, rev.get("instruction", ""))
            fidelity_before = cand_report.get("score", fidelity_before)
            analyze_report = cand_report
        rounds.append(
            measure_round(
                label=f"analyze_{i + 1}",
                before=before,
                after=analyze,
                revision=rev,
                accept=accept,
                package=package,
            )
        )
        (out / "plan_analyze.json").write_text(json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  analyze refine {i + 1}: {'accepted' if accept.accepted else 'rejected'} {accept.reasons}")

    write_fidelity_artifacts(out, analyze_report=analyze_report)

    print("Step 2: materialize...")
    spec = materialize_from_analyze(analyze, checksum, client=client, io_dir=io_dir)
    baseline_spec = json.loads(json.dumps(spec))
    package = compile_artifacts(spec, arc_id="arc_2")["planning_package"]
    val_before = validate_spec_artifacts(spec, fixture, GOLDEN)
    criteria_before = val_before.get("criteria", {})

    spec_report = coverage_report_spec(spec, section_map, fidelity_cfg)
    _print_gaps(spec_report, "Spec")
    write_fidelity_artifacts(out, analyze_report=analyze_report, spec_report=spec_report)
    fidelity_before = spec_report.get("score", 0.0)

    for i, rev in enumerate(_revisions_for_checkpoint(script, "spec")[:MAX_REFINES_PER_CHECKPOINT]):
        if interactive:
            ans = input(f"Apply spec revision {i + 1}? [Y/n/s=skip] ").strip().lower()
            if ans in ("n", "no", "s", "skip"):
                continue
        before = spec
        rev = {**rev, "constraint_ledger": list(ledger)}
        candidate = refine_spec(before, rev, client=client, source_checksum=checksum, analyze=analyze)
        cand_report = coverage_report_spec(candidate, section_map, fidelity_cfg)
        val_after_cand = validate_spec_artifacts(candidate, fixture, GOLDEN)
        accept = accept_refine(
            before,
            candidate,
            rev,
            package=package,
            criteria_before=criteria_before,
            criteria_after=val_after_cand.get("criteria", {}),
            fidelity_before=fidelity_before,
            fidelity_after=cand_report.get("score"),
        )
        spec = candidate if accept.accepted else before
        if accept.accepted:
            _append_ledger(ledger, rev.get("instruction", ""))
            fidelity_before = cand_report.get("score", fidelity_before)
            spec_report = cand_report
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
                criteria_before=criteria_before,
                criteria_after=val_after_cand.get("criteria", {}),
            )
        )
        print(f"  spec refine {i + 1}: {'accepted' if accept.accepted else 'rejected'} {accept.reasons}")

    (out / "novel_system_spec.fidelity.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    spec_report = coverage_report_spec(spec, section_map, fidelity_cfg)
    final_validation = validate_spec_artifacts(spec, fixture, GOLDEN)
    gate_pass = bool(spec_report.get("gate_pass")) and bool(final_validation.get("all_pass"))

    write_fidelity_artifacts(out, analyze_report=analyze_report, spec_report=spec_report)
    (out / "fidelity_gate.json").write_text(
        json.dumps(
            {
                "phase_a_pass": gate_pass,
                "fidelity_score": spec_report.get("score"),
                "golden_pass": final_validation.get("all_pass"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = format_hil_report(
        rounds,
        baseline=baseline_spec,
        final=spec,
        final_validation=final_validation,
    )
    (out / "fidelity_hil_report.md").write_text(report, encoding="utf-8")
    _print_gaps(spec_report, "Final Spec")
    print(report)

    rc, _ = _run_validate_compile(out, spec, fixture)
    if not gate_pass:
        print(f"\nPhase A gate FAIL — fidelity={spec_report.get('score')} (need >=0.85)")
        rc = max(rc, 1)
    else:
        print("\nPhase A gate PASS")
    print(f"\nFidelity POC complete → {out}")
    return rc


def _run_elaboration(
    spec: dict[str, Any],
    checksum: str,
    section_map: list[dict[str, Any]],
    fidelity_cfg: dict[str, Any],
    script: dict[str, Any],
    out: Path,
    io_dir: Path,
    interactive: bool,
) -> int:
    client = LMStudioClient(io_dir=io_dir)
    excerpts = section_excerpts_for_elaboration(section_map)
    print("Phase B: elaboration...")
    elaborated = elaborate_spec(spec, excerpts, client=client, source_checksum=checksum)
    audit = consistency_audit(elaborated)
    print(f"  consistency audit: {len(audit.get('critical', []))} critical, {len(audit.get('warnings', []))} warnings")

    for i, rev in enumerate(_revisions_for_checkpoint(script, "elaborate")[:MAX_REFINES_PER_CHECKPOINT]):
        if interactive:
            ans = input(f"Apply elaboration revision {i + 1}? [Y/n] ").strip().lower()
            if ans in ("n", "no"):
                continue
        before = elaborated
        rev = {**rev, "constraint_ledger": list(script.get("constraint_ledger") or [])}
        candidate = elaborate_spec(before, excerpts, client=client, source_checksum=checksum)
        elab_report = evaluate_elaboration_fidelity(candidate, fidelity_cfg)
        blob = json.dumps(candidate, ensure_ascii=False).lower()
        missing = [t for t in rev.get("expect_contains") or [] if t.lower() not in blob]
        if missing:
            print(f"  elaboration refine {i + 1}: skipped — missing {missing}")
            continue
        elaborated = candidate
        print(f"  elaboration refine {i + 1}: applied score={elab_report.get('score')}")

    elab_report = evaluate_elaboration_fidelity(elaborated, fidelity_cfg)
    write_fidelity_artifacts(
        out,
        spec_report=coverage_report_spec(elaborated, section_map, fidelity_cfg),
        elaboration_report=elab_report,
    )
    (out / "novel_system_spec.elaborated.json").write_text(
        json.dumps(elaborated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    gate = json.loads((out / "fidelity_gate.json").read_text(encoding="utf-8"))
    gate["phase_b_pass"] = bool(elab_report.get("gate_pass"))
    gate["elaboration_score"] = elab_report.get("score")
    gate.setdefault("phase_a_pass", True)
    gate.setdefault("fidelity_score", coverage_report_spec(elaborated, section_map, fidelity_cfg).get("score"))
    (out / "fidelity_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")

    rc = 0 if elab_report.get("gate_pass") else 1
    print(f"Phase B gate: {'PASS' if elab_report.get('gate_pass') else 'FAIL'}")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge Fidelity POC")
    p.add_argument("-o", "--output-dir", type=Path, default=ROOT / "out")
    p.add_argument("--fixture", type=Path, default=FIXTURE)
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    p.add_argument("--phase", choices=("fidelity", "elaboration"), default="fidelity")
    p.add_argument("--interactive", action="store_true")
    args = p.parse_args()
    script = ELAB_SCRIPT if args.phase == "elaboration" else args.script
    return run_fidelity(
        args.fixture,
        script,
        args.output_dir,
        interactive=args.interactive,
        phase=args.phase,
    )


if __name__ == "__main__":
    raise SystemExit(main())
