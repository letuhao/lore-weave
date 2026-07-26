#!/usr/bin/env python3
"""CLI: validate against golden expectations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.validate import format_report, validate_golden


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge validate")
    p.add_argument("output_dir", type=Path, help="POC out/ directory")
    p.add_argument("-o", "--report", type=Path, required=True)
    p.add_argument("--golden", type=Path, required=True)
    args = p.parse_args()
    out = args.output_dir
    doc = json.loads((out / "plan_document.json").read_text(encoding="utf-8"))
    spec = json.loads((out / "novel_system_spec.json").read_text(encoding="utf-8"))
    graph = json.loads((out / "plan_graph.json").read_text(encoding="utf-8"))
    package = json.loads((out / "compile" / "planning_package.json").read_text(encoding="utf-8"))
    validation = validate_golden(spec, package, graph, doc, args.golden)
    report = format_report(validation)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    (out / "validation_result.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(report)
    return 0 if validation["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
