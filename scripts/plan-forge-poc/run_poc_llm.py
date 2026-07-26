#!/usr/bin/env python3
"""Run PlanForge LLM live POC — analyze → materialize → validate + optional rules compare."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.compare import compare_specs, format_compare_report
from plan_forge.ingest import ingest_file
from plan_forge.llm_client import LMStudioClient
from plan_forge.propose import propose_spec
from plan_forge.propose_llm import propose_spec_llm

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge LLM live POC")
    p.add_argument("-o", "--output-dir", type=Path, default=ROOT / "out")
    p.add_argument("--fixture", type=Path, default=FIXTURE)
    p.add_argument("--golden", type=Path, default=GOLDEN)
    p.add_argument("--compare-rules", action="store_true", default=True)
    p.add_argument("--no-compare-rules", action="store_false", dest="compare_rules")
    p.add_argument("--skip-validate", action="store_true")
    args = p.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    io_dir = out / "llm_io"
    py = sys.executable

    client = LMStudioClient(io_dir=io_dir)
    print("LM Studio health check...")
    models = client.health_check()
    model_ids = [m.get("id", m) if isinstance(m, dict) else m for m in models.get("data", [])]
    print(f"  models available: {len(model_ids)}")
    if client.model not in str(model_ids):
        print(f"  warning: configured model {client.model!r} not in list (may still work)")

    print("Step 1-2: LLM analyze + materialize...")
    spec_llm, analyze = propose_spec_llm(args.fixture, client=client, io_dir=io_dir)
    (out / "plan_analyze.json").write_text(json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "novel_system_spec.llm.json").write_text(json.dumps(spec_llm, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.compare_rules:
        print("Rules baseline for comparison...")
        doc = ingest_file(args.fixture)
        (out / "plan_document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        spec_rules = propose_spec(doc)
        (out / "novel_system_spec.rules.json").write_text(
            json.dumps(spec_rules, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        metrics = compare_specs(spec_rules, spec_llm)
        (out / "llm_vs_rules_report.md").write_text(format_compare_report(metrics), encoding="utf-8")
        print(f"  event overlap: {metrics['event_id_overlap_ratio']:.0%}")

    run([py, str(ROOT / "decompose.py"), str(out / "novel_system_spec.llm.json"), "-o", str(out / "plan_graph.llm.json")])
    run(
        [
            py,
            str(ROOT / "compile.py"),
            str(out / "novel_system_spec.llm.json"),
            "-o",
            str(out),
            "--arc",
            "arc_2",
            "--mock-llm",
        ]
    )
  # compile writes to out/compile/ — copy planning package name for llm validate
    compile_pkg = out / "compile" / "planning_package.json"
    if compile_pkg.exists():
        (out / "compile" / "planning_package.llm.json").write_text(
            compile_pkg.read_text(encoding="utf-8"), encoding="utf-8"
        )

    if not args.skip_validate:
        # validate.py expects standard paths — symlink-like copy for LLM spec
        (out / "novel_system_spec.json").write_text(
            (out / "novel_system_spec.llm.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (out / "plan_graph.json").write_text(
            (out / "plan_graph.llm.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        if not (out / "plan_document.json").exists():
            doc = ingest_file(args.fixture)
            (out / "plan_document.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        rc = subprocess.run(
            [
                py,
                str(ROOT / "validate.py"),
                str(out),
                "-o",
                str(out / "validation_report.llm.md"),
                "--golden",
                str(args.golden),
            ]
        ).returncode
        if rc != 0:
            print("LLM validation: FAIL (see validation_report.llm.md)")
            return rc

    print(f"\nLLM POC complete → {out}")
    print(f"  plan_analyze.json")
    print(f"  novel_system_spec.llm.json")
    print(f"  llm_io/ ({len(list(io_dir.glob('*.json')))} calls)")
    if args.compare_rules:
        print(f"  llm_vs_rules_report.md")
    if not args.skip_validate:
        print(f"  validation_report.llm.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
