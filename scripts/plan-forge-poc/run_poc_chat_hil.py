#!/usr/bin/env python3
"""PlanForge Chat HIL POC — vague feedback + chat orchestration simulation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plan_forge.apply_policy import format_diagnosis_card, process_user_turn
from plan_forge.compile import compile_artifacts
from plan_forge.coverage import build_section_map, load_coverage_context
from plan_forge.eval_chat_hil import aggregate_metrics, format_chat_hil_report, load_io_token_stats, measure_turn
from plan_forge.eval_fidelity import evaluate_spec_fidelity, load_fidelity_config
from plan_forge.eval_hil import validate_spec_artifacts
from plan_forge.llm_client import LMStudioClient

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "story-plan-v1.md"
FIDELITY = ROOT / "fixtures" / "story-plan-v1.fidelity.yaml"
GOLDEN = ROOT / "fixtures" / "story-plan-v1.expectations.yaml"
DEFAULT_SCRIPT = ROOT / "fixtures" / "chat_hil_vague_script.yaml"
DEFAULT_SPEC = ROOT / "out" / "novel_system_spec.fidelity.json"


def _load_script(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _confirm_default(_interp: dict[str, Any]) -> bool:
    return True


def run_chat_hil(
    spec_path: Path,
    script_path: Path,
    output_dir: Path,
    *,
    interactive: bool = False,
    use_llm_interpret: bool = True,
) -> int:
    out = output_dir
    out.mkdir(parents=True, exist_ok=True)
    io_dir = out / "chat_hil_io"

    if not spec_path.exists():
        print(f"ERROR: spec not found: {spec_path}")
        print("Run run_poc_fidelity.py first to produce novel_system_spec.fidelity.json")
        return 2

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    checksum = spec.get("meta", {}).get("source_checksum", "")
    section_map, _ = load_coverage_context(FIXTURE, FIDELITY)
    fidelity_cfg = load_fidelity_config(FIDELITY)
    package = compile_artifacts(spec, arc_id="arc_2")["planning_package"]
    script = _load_script(script_path)
    ledger: list[str] = list(script.get("constraint_ledger") or [])
    chat_context = ""

    client = LMStudioClient(io_dir=io_dir)
    print("LM Studio health check...")
    client.health_check()

    turn_metrics: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []

    for turn in script.get("turns") or []:
        user_msg = turn.get("user_message", "")
        seq_before = client._seq
        print(f"\n=== User: {user_msg[:80]}...")

        def confirm_fn(interp: dict[str, Any]) -> bool:
            print(format_diagnosis_card(interp))
            if interactive:
                ans = input("Apply revision? [Y/n] ").strip().lower()
                return ans not in ("n", "no")
            return True

        result = process_user_turn(
            user_msg,
            spec,
            section_map,
            client=client,
            source_checksum=checksum,
            fixture_path=FIXTURE,
            fidelity_path=FIDELITY,
            fidelity_cfg=fidelity_cfg,
            package=package,
            constraint_ledger=ledger,
            chat_context=chat_context[-200:] if chat_context else None,
            confirm_fn=confirm_fn if turn.get("expect_confirm") else None,
            use_llm_interpret=use_llm_interpret,
        )

        spec = result.spec
        if result.accepted and result.interpretation.get("draft_revision"):
            instr = (result.interpretation["draft_revision"].get("instruction") or "")[:200]
            if instr and instr not in ledger:
                ledger.append(instr)

        print(f"Assistant: {result.chat_response[:500]}")
        chat_context = result.chat_response[:200]

        token_stats = load_io_token_stats(io_dir, after_seq=seq_before)
        tm = measure_turn(
            turn_id=turn.get("id", "turn"),
            interpretation=result.interpretation,
            apply_result={
                "accepted": result.accepted,
                "fidelity_before": result.fidelity_before,
                "fidelity_after": result.fidelity_after,
            },
            oracle=turn.get("oracle"),
            token_stats=token_stats,
        )
        turn_metrics.append(tm)
        transcript.append(
            {
                "turn_id": turn.get("id"),
                "user": user_msg,
                "assistant": result.chat_response,
                "interpretation": result.interpretation,
                "accepted": result.accepted,
                "metrics": tm,
            }
        )

    (out / "novel_system_spec.chat_hil.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    final_fidelity = evaluate_spec_fidelity(spec, fidelity_cfg)
    validation = validate_spec_artifacts(spec, FIXTURE, GOLDEN)

    summary = aggregate_metrics(turn_metrics)
    summary["final_fidelity"] = final_fidelity.get("score")
    summary["final_gate"] = final_fidelity.get("gate_pass")
    summary["golden_pass"] = validation.get("all_pass")

    (out / "chat_hil_transcript.json").write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "chat_hil_metrics.json").write_text(
        json.dumps({"summary": summary, "turns": turn_metrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = format_chat_hil_report(turn_metrics, summary)
    (out / "chat_hil_report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nFinal fidelity: {final_fidelity.get('score')} gate={final_fidelity.get('gate_pass')}")

    rc = 0 if summary.get("pass") and final_fidelity.get("gate_pass") else 1
    print(f"\nChat HIL POC complete → {out}")
    return rc


def main() -> int:
    p = argparse.ArgumentParser(description="PlanForge Chat HIL POC")
    p.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    p.add_argument("-o", "--output-dir", type=Path, default=ROOT / "out")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--rules-only", action="store_true", help="Skip LLM interpret; rules path only")
    args = p.parse_args()
    return run_chat_hil(
        args.spec,
        args.script,
        args.output_dir,
        interactive=args.interactive,
        use_llm_interpret=not args.rules_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
