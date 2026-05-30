#!/usr/bin/env python3
"""
cost-tracker — B3 dual-use (Q9 §14.9):
  - --mode quota  → estimated tokens from QUOTA_LOG.jsonl (subscription users)
  - --mode dollar → estimated $ from token counts × Opus pricing (API users)

For Max 20x subscription users, dollar mode returns 0 (no $-billing).

Usage:
  cost-tracker.py --mode quota --cycle 17
  cost-tracker.py --mode dollar --cycle 17
  cost-tracker.py --mode quota --foundation     # full foundation total
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUOTA_LOG = REPO_ROOT / "docs" / "raid" / "QUOTA_LOG.jsonl"
PROFILE = REPO_ROOT / "contracts" / "raid" / "quota-profile.yaml"

# Anthropic Opus 4.7 pricing (May 2026 estimate — for API users only)
OPUS_INPUT_PER_M = 15.0
OPUS_OUTPUT_PER_M = 75.0


def is_subscription_user() -> bool:
    """Check quota-profile.yaml plan; if max-20x → subscription."""
    if not PROFILE.exists():
        return False
    text = PROFILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("plan:"):
            return "max-" in line or "pro" in line
    return False


def load_rows() -> list[dict]:
    rows = []
    if not QUOTA_LOG.exists():
        return rows
    for line in QUOTA_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def filter_rows(rows: list[dict], cycle: int | None, foundation: bool) -> list[dict]:
    if foundation:
        return rows
    if cycle is None:
        return rows
    return [r for r in rows if r.get("cycle") == cycle]


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["quota", "dollar"], required=True)
    p.add_argument("--cycle", type=int, default=None)
    p.add_argument("--foundation", action="store_true",
                   help="all rows (full foundation total)")
    args = p.parse_args(argv)

    rows = filter_rows(load_rows(), args.cycle, args.foundation)
    total_tokens = sum(int(r.get("estimated_tokens", 0)) for r in rows)

    if args.mode == "quota":
        print(f"mode: quota")
        print(f"scope: {'foundation' if args.foundation else f'cycle {args.cycle}' if args.cycle else 'all'}")
        print(f"estimated_tokens: {total_tokens:,}")
        return 0

    # mode == dollar
    if is_subscription_user():
        print("mode: dollar")
        print("subscription_user: true")
        print("dollar_cost: 0 (subscription plan — no per-token billing)")
        print(f"reference_tokens: {total_tokens:,}")
        return 0
    # API-user estimate: assume 50/50 input/output split
    in_tok = total_tokens // 2
    out_tok = total_tokens - in_tok
    dollars = (in_tok / 1_000_000) * OPUS_INPUT_PER_M + (out_tok / 1_000_000) * OPUS_OUTPUT_PER_M
    print(f"mode: dollar")
    print(f"estimated_tokens: {total_tokens:,}")
    print(f"estimated_input: {in_tok:,}")
    print(f"estimated_output: {out_tok:,}")
    print(f"estimated_dollars: ${dollars:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
