"""Chat HIL evaluation metrics (I1–I4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def measure_turn(
    *,
    turn_id: str,
    interpretation: dict[str, Any],
    apply_result: dict[str, Any],
    oracle: dict[str, Any] | None = None,
    token_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    oracle = oracle or {}
    focus = interpretation.get("focus_paths") or []
    expected_focus = oracle.get("expect_focus_contains") or []
    i1 = True
    if expected_focus:
        blob = " ".join(focus).lower()
        i1 = any(exp.lower() in blob for exp in expected_focus)

    gap_ids = [d.get("gap_id", "") for d in interpretation.get("diagnosis") or []]
    expected_gaps = oracle.get("expect_gap_prefix") or []
    i2 = True
    if expected_gaps:
        i2 = any(any(g.startswith(p) for p in expected_gaps) for g in gap_ids if g)

    i3 = bool(apply_result.get("accepted")) or oracle.get("expect_no_apply", False)
    if oracle.get("expect_clarify"):
        i3 = interpretation.get("apply_mode") == "needs_clarification"

    prompt_chars = (token_stats or {}).get("interpret_prompt_chars", 0) + (token_stats or {}).get(
        "refine_prompt_chars", 0
    )
    max_chars = oracle.get("max_prompt_chars", 8000)
    interpret_only = (token_stats or {}).get("interpret_prompt_chars", 0)
    if interpret_only == 0 and prompt_chars > 0:
        # rules-only path: budget gate uses per-turn refine total vs oracle
        i4 = prompt_chars <= max_chars
    elif interpret_only > 0:
        i4 = interpret_only <= 4000 and prompt_chars <= max_chars
    else:
        i4 = True

    return {
        "turn_id": turn_id,
        "I1_scope": i1,
        "I2_diagnosis": i2,
        "I3_apply": i3,
        "I4_context_budget": i4,
        "prompt_chars": prompt_chars,
        "interpretation": {
            "intent": interpretation.get("intent"),
            "apply_mode": interpretation.get("apply_mode"),
            "focus_paths": focus,
        },
        "apply": {
            "accepted": apply_result.get("accepted"),
            "fidelity_delta": apply_result.get("fidelity_after", 0) - apply_result.get("fidelity_before", 0),
        },
    }


def aggregate_metrics(turns: list[dict[str, Any]]) -> dict[str, Any]:
    if not turns:
        return {"pass": False, "turns": 0}
    keys = ("I1_scope", "I2_diagnosis", "I3_apply", "I4_context_budget")
    rates = {k: sum(1 for t in turns if t.get(k)) / len(turns) for k in keys}
    return {
        "turns": len(turns),
        "rates": rates,
        "pass": all(rates[k] >= 0.75 for k in keys),
    }


def format_chat_hil_report(turns: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = ["# PlanForge Chat HIL Evaluation", ""]
    lines.append(f"**Overall:** {'PASS' if summary.get('pass') else 'FAIL'}")
    lines.append("")
    for k, v in (summary.get("rates") or {}).items():
        lines.append(f"- {k}: {v:.0%}")
    lines.append("")
    for t in turns:
        lines.append(f"## Turn {t['turn_id']}")
        lines.append(f"- I1 scope: {'PASS' if t['I1_scope'] else 'FAIL'}")
        lines.append(f"- I2 diagnosis: {'PASS' if t['I2_diagnosis'] else 'FAIL'}")
        lines.append(f"- I3 apply: {'PASS' if t['I3_apply'] else 'FAIL'}")
        lines.append(f"- I4 budget: {'PASS' if t['I4_context_budget'] else 'FAIL'} ({t.get('prompt_chars', 0)} chars)")
        lines.append("")
    return "\n".join(lines)


def load_io_token_stats(io_dir: Path, *, after_seq: int = 0) -> dict[str, int]:
    interpret_chars = 0
    refine_chars = 0
    if not io_dir.exists():
        return {}
    for p in sorted(io_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("seq", 0) <= after_seq:
            continue
        step = data.get("step", "")
        chars = data.get("prompt_chars", 0)
        if "interpret" in step:
            interpret_chars += chars
        if "refine" in step:
            refine_chars += chars
    return {"interpret_prompt_chars": interpret_chars, "refine_prompt_chars": refine_chars}
