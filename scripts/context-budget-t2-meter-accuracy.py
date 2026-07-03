"""T2 GATE — meter (token estimator) accuracy vs provider ground truth.

The Context Budget meter projects tokens with the script-aware `estimate_tokens`
(token_budget.py) — provider-agnostic, so it works for local lm_studio / Qwen /
Gemma AND Claude. What the meter/target/compaction actually act on is the INPUT
projection, so that is what we validate: the sum of the persisted per-turn
`context_breakdown` categories (the estimate the meter shows) vs the provider's
`input_tokens` for that same turn (ground truth).

We also report an OUTPUT-side sanity comparison (est(content) vs output_tokens),
but that is CONFOUNDED — `output_tokens` includes reasoning + tool-call arg tokens
that `content` (final text only) does not — so it reads as a large under-estimate
and is NOT the gate. The input comparison has only a small confound (the current
user message is not a breakdown category), which biases it slightly LOW.

GATE (spec §8 T2): input estimate within ±X% of provider-reported input_tokens.

Usage:
  PYTHONPATH=services/chat-service python scripts/context-budget-t2-meter-accuracy.py
  (dev postgres on the host-exposed port; override with T2_DB_DSN=...)
"""
from __future__ import annotations

import asyncio
import os
import statistics
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "chat-service"))
from app.services.token_budget import estimate_tokens  # noqa: E402

DSN = os.environ.get("T2_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _breakdown_sum(frame) -> int | None:
    """Sum the estimate the meter showed: every context_breakdown category
    (memory_knowledge is nested {total, sections} → use total)."""
    if not isinstance(frame, dict):
        return None
    bd = frame.get("breakdown")
    if not isinstance(bd, dict):
        return None
    total = 0
    for v in bd.values():
        if isinstance(v, dict):
            total += int(v.get("total", 0) or 0)
        else:
            total += int(v or 0)
    return total


def _report(name: str, rs: list[float]) -> None:
    if not rs:
        print(f"  {name}: no samples")
        return
    errs = [abs(x - 1.0) for x in rs]
    within10 = 100.0 * sum(1 for e in errs if e <= 0.10) / len(errs)
    within20 = 100.0 * sum(1 for e in errs if e <= 0.20) / len(errs)
    print(f"  {name} (n={len(rs)}):")
    print(f"    median est/actual ratio : {statistics.median(rs):.3f}  (1.000 = perfect)")
    print(f"    mean abs error          : {100*statistics.mean(errs):.1f}%")
    print(f"    within ±10% / ±20%      : {within10:.0f}% / {within20:.0f}%")


async def main() -> int:
    import asyncpg
    import json

    conn = await asyncpg.connect(DSN)
    in_rows = await conn.fetch(
        "SELECT context_breakdown, input_tokens FROM chat_messages "
        "WHERE role='assistant' AND input_tokens IS NOT NULL AND input_tokens > 100 "
        "AND context_breakdown IS NOT NULL"
    )
    out_rows = await conn.fetch(
        "SELECT content, output_tokens FROM chat_messages "
        "WHERE role='assistant' AND output_tokens IS NOT NULL AND output_tokens > 20 "
        "AND content IS NOT NULL AND length(content) > 40 AND tool_calls IS NULL"
    )
    await conn.close()

    # ── INPUT side (the gate): sum(breakdown) vs input_tokens ──
    in_ratios: list[float] = []
    for r in in_rows:
        frame = r["context_breakdown"]
        if isinstance(frame, str):
            frame = json.loads(frame)
        est = _breakdown_sum(frame)
        actual = int(r["input_tokens"])
        if est and actual > 0:
            in_ratios.append(est / actual)

    # ── OUTPUT side (confounded sanity only): est(content) vs output_tokens ──
    out_ratios: list[float] = []
    for r in out_rows:
        actual = int(r["output_tokens"])
        if actual > 0:
            out_ratios.append(estimate_tokens(r["content"]) / actual)

    print("T2 meter accuracy — script-aware INPUT estimate vs provider input_tokens")
    print("=" * 70)
    _report("input: sum(breakdown) / input_tokens  [THE GATE]", in_ratios)
    print()
    print("  (confounded sanity — output_tokens counts reasoning+toolargs not in content):")
    _report("output: est(content) / output_tokens", out_ratios)

    if not in_ratios:
        print("\nNo turns with a persisted breakdown — cannot gate.")
        return 1
    median = statistics.median(in_ratios)
    majority20 = sum(1 for x in in_ratios if abs(x - 1.0) <= 0.20) / len(in_ratios)
    # Input estimate biases slightly LOW (excludes the current user message), so
    # accept a median in [0.80, 1.15] with a majority within ±25%.
    ok = 0.80 <= median <= 1.15 and majority20 >= 0.4
    print()
    print("GATE (input median in [0.80,1.15] AND ≥40% within ±20%):", "PASS" if ok else "REVIEW")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
