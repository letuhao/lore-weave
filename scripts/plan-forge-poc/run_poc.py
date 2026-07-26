#!/usr/bin/env python3
"""Run full PlanForge POC pipeline (rules or LLM)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge full POC")
    p.add_argument("-o", "--output-dir", type=Path, default=ROOT / "out")
    p.add_argument("--fixture", type=Path, default=FIXTURE)
    p.add_argument("--golden", type=Path, default=GOLDEN)
    p.add_argument("--llm", action="store_true", help="Use LLM propose (LM Studio)")
    p.add_argument("--compare-rules", action="store_true", help="With --llm, also run rules baseline")
    p.add_argument("--mock-llm", action="store_true", default=True)
    args = p.parse_args()

    if args.llm:
        cmd = [sys.executable, str(ROOT / "run_poc_llm.py"), "-o", str(args.output_dir), "--fixture", str(args.fixture), "--golden", str(args.golden)]
        if args.compare_rules:
            cmd.append("--compare-rules")
        else:
            cmd.append("--no-compare-rules")
        run(cmd)
        return 0

    out = args.output_dir
    py = sys.executable

    run([py, str(ROOT / "ingest.py"), str(args.fixture), "-o", str(out / "plan_document.json")])
    run([py, str(ROOT / "propose.py"), str(out / "plan_document.json"), "-o", str(out / "novel_system_spec.json"), "--mode", "rules"])
    run([py, str(ROOT / "decompose.py"), str(out / "novel_system_spec.json"), "-o", str(out / "plan_graph.json")])
    compile_cmd = [
        py,
        str(ROOT / "compile.py"),
        str(out / "novel_system_spec.json"),
        "-o",
        str(out),
        "--arc",
        "arc_2",
    ]
    if args.mock_llm:
        compile_cmd.append("--mock-llm")
    run(compile_cmd)
    run(
        [
            py,
            str(ROOT / "validate.py"),
            str(out),
            "-o",
            str(out / "validation_report.md"),
            "--golden",
            str(args.golden),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
