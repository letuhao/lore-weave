#!/usr/bin/env python3
"""CLI: propose NovelSystemSpec from PlanDocument (rules) or raw markdown (LLM)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.ingest import ingest_file
from plan_forge.propose import propose_spec
from plan_forge.propose_llm import propose_spec_llm


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge propose")
    p.add_argument("input", type=Path, nargs="?", help="plan_document.json (rules mode)")
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--mode", choices=["rules", "llm"], default="rules")
    p.add_argument("--source", type=Path, help="raw .md for llm mode (defaults to fixture path)")
    p.add_argument("--analyze-out", type=Path, help="write PlanAnalyze JSON (llm mode)")
    p.add_argument("--io-dir", type=Path, help="LLM IO log directory")
    p.add_argument("--interactive", action="store_true", help="Prompt before write")
    args = p.parse_args()

    if args.mode == "llm":
        raw = args.source or args.input
        if raw is None:
            print("llm mode requires --source <file.md> or input path", file=sys.stderr)
            return 2
        io_dir = args.io_dir or args.output.parent / "llm_io"
        spec, analyze = propose_spec_llm(raw, io_dir=io_dir)
        if args.analyze_out:
            args.analyze_out.parent.mkdir(parents=True, exist_ok=True)
            args.analyze_out.write_text(json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        if args.input is None:
            print("rules mode requires plan_document.json input", file=sys.stderr)
            return 2
        doc = json.loads(args.input.read_text(encoding="utf-8"))
        spec = propose_spec(doc)

    if args.interactive:
        print(json.dumps(spec, ensure_ascii=False, indent=2)[:2000], "...")
        ans = input("Approve spec? [y/N]: ").strip().lower()
        if ans != "y":
            print("Aborted at propose checkpoint.")
            return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"proposed ({args.mode}): {len(spec.get('arcs', []))} arcs, "
        f"{len(spec.get('events', []))} events, "
        f"{len(spec.get('layers', {}).get('variables', []))} variables → {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
