#!/usr/bin/env python3
"""Phase C stability + braindump smoke for PlanForge eval."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.compare import compare_specs
from plan_forge.ingest import ingest_file
from plan_forge.llm_client import LMStudioClient
from plan_forge.propose import propose_spec
from plan_forge.propose_llm import propose_spec_llm
from plan_forge.validate import run_rules, validate_golden

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
BRAINDUMP = ROOT / "fixtures" / "story-braindump-smoke.md"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"
OUT = ROOT / "out" / "eval"


def _arc2_titles(spec: dict) -> list[str]:
    return [e["title"] for e in spec.get("events", []) if e.get("arc_id") == "arc_2"]


def stability_runs(n: int = 3) -> list[dict]:
    results: list[dict] = []
    doc = ingest_file(FIXTURE)
    rules = propose_spec(doc)
    for i in range(1, n + 1):
        io_dir = OUT / f"stability_{i}" / "llm_io"
        client = LMStudioClient(io_dir=io_dir)
        spec, analyze = propose_spec_llm(FIXTURE, client=client, io_dir=io_dir)
        rules_out = run_rules(spec)
        notes = next(r for r in rules_out if r["rule"] == "notes_linked")
        cmp = compare_specs(rules, spec)
        run_dir = OUT / f"stability_{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "novel_system_spec.llm.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        results.append(
            {
                "run": i,
                "arc2_events": len(_arc2_titles(spec)),
                "arc2_titles": _arc2_titles(spec),
                "notes_linked_ratio": notes.get("detail", ""),
                "notes_linked_pass": notes["pass"],
                "vars_pass": all(r["pass"] for r in rules_out if r["rule"] == "vars_four"),
                "title_overlap": cmp["event_title_overlap_ratio"],
            }
        )
    return results


def braindump_smoke() -> dict:
    client = LMStudioClient(io_dir=OUT / "braindump" / "llm_io")
    _, analyze = propose_spec_llm(BRAINDUMP, client=client, io_dir=OUT / "braindump" / "llm_io")
    codes = {v["code"] for v in analyze.get("variables", [])}
    arc2 = [e for e in analyze.get("events", []) if e.get("arc_id") == "arc_2"]
    out = {
        "vars_four": codes >= {"PA", "HA", "CD", "THR"},
        "variable_codes": sorted(codes),
        "arc2_event_count": len(arc2),
        "arc2_titles": [e.get("title") for e in arc2],
        "open_questions_count": len(analyze.get("open_questions", [])),
    }
    (OUT / "braindump").mkdir(parents=True, exist_ok=True)
    (OUT / "braindump" / "plan_analyze.json").write_text(
        json.dumps(analyze, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Stability runs (3x)...")
    stability = stability_runs(3)
    print("Braindump smoke...")
    braindump = braindump_smoke()
    report = {"stability_runs": stability, "braindump_smoke": braindump}
    path = OUT / "phase_c_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"→ {path}")
    pass_count = sum(1 for r in stability if r["notes_linked_pass"] and r["vars_pass"])
    print(f"Stability pass: {pass_count}/3 (notes_linked + vars_four)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
