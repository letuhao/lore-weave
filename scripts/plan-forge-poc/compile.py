#!/usr/bin/env python3
"""CLI: compile LW artifacts + PlanningPackage + optional mock pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.compile import compile_artifacts, mock_pipeline_result


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge compile")
    p.add_argument("input", type=Path, help="novel_system_spec.json")
    p.add_argument("-o", "--output-dir", type=Path, required=True)
    p.add_argument("--arc", default="arc_2")
    p.add_argument("--mock-llm", action="store_true")
    args = p.parse_args()
    spec = json.loads(args.input.read_text(encoding="utf-8"))
    compiled = compile_artifacts(spec, arc_id=args.arc)
    out = args.output_dir
    compile_dir = out / "compile"
    compile_dir.mkdir(parents=True, exist_ok=True)
    (compile_dir / "glossary_seeds.json").write_text(
        json.dumps(compiled["glossary_seeds"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (compile_dir / "planner_state.json").write_text(
        json.dumps(compiled["planner_state_init"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (compile_dir / "outline_skeleton.json").write_text(
        json.dumps(compiled["outline_skeleton"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (compile_dir / "planning_package.json").write_text(
        json.dumps(compiled["planning_package"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (compile_dir / "working_memory_charter.json").write_text(
        json.dumps(compiled["working_memory_charter"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.mock_llm:
        pipeline = mock_pipeline_result(compiled["planning_package"])
        (out / f"{args.arc}_pipeline.json").write_text(
            json.dumps(pipeline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"mock pipeline: {pipeline['chapter_count']} chapters, {pipeline['scene_count']} scene groups")
    print(f"compiled → {compile_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
