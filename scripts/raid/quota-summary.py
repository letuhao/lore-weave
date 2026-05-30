#!/usr/bin/env python3
"""
quota-summary — Q7 quota dashboard
Per RAID_WORKFLOW.md §14.7.

Reads docs/raid/QUOTA_LOG.jsonl and emits human-readable dashboard.

Usage:
  quota-summary.py                  # full dashboard
  quota-summary.py --cycle 17       # filter to one cycle
"""
from __future__ import annotations
import argparse
import collections
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUOTA_LOG = REPO_ROOT / "docs" / "raid" / "QUOTA_LOG.jsonl"


def parse_iso(s: str) -> float:
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return 0.0


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


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cycle", type=int, default=None)
    args = p.parse_args(argv)

    rows = load_rows()
    if args.cycle is not None:
        rows = [r for r in rows if r.get("cycle") == args.cycle]
    if not rows:
        print("[quota-summary] no rows found")
        return 0

    by_cycle = collections.defaultdict(int)
    by_model = collections.defaultdict(int)
    total = 0
    for r in rows:
        t = int(r.get("estimated_tokens", 0))
        total += t
        cyc = r.get("cycle", "?")
        by_cycle[cyc] += t
        m = r.get("model", "unknown")
        by_model[m] += t

    # 5h window estimate
    now = time.time()
    recent = sum(
        int(r.get("estimated_tokens", 0))
        for r in rows
        if parse_iso(r.get("ts", "")) >= now - 5 * 3600
    )

    print("=" * 64)
    print("RAID quota summary (foundation mega-task)")
    print("=" * 64)
    print(f"Total estimated tokens (all-time): {total:,}")
    print(f"5h window recent burn:             {recent:,}")
    print()
    print("By cycle (top 10):")
    for cyc, t in sorted(by_cycle.items(), key=lambda x: -x[1])[:10]:
        print(f"  Cycle {cyc:<4}: {t:>10,} tokens")
    print()
    print("By model:")
    for m, t in sorted(by_model.items(), key=lambda x: -x[1]):
        print(f"  {m:<30}: {t:>10,} tokens")
    print()
    print(f"Recommendation: {'PROCEED' if recent < 1_000_000 else 'RISKY' if recent < 1_500_000 else 'WAIT-FOR-RESET'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
