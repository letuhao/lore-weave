#!/usr/bin/env python3
"""
cost-summary — B3 dual-use dashboard
Delegates to cost-tracker.py for both modes.

Usage:
  cost-summary.py             # both modes for full foundation
  cost-summary.py --cycle 17  # cycle-specific
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKER = REPO_ROOT / "scripts" / "raid" / "cost-tracker.py"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cycle", type=int, default=None)
    args = p.parse_args(argv)
    scope = ["--cycle", str(args.cycle)] if args.cycle else ["--foundation"]

    print("=" * 64)
    print("Cost summary (dual-use: subscription quota + API $ estimate)")
    print("=" * 64)
    print()
    print("--- Quota mode (subscription users) ---")
    subprocess.run([sys.executable, str(TRACKER), "--mode", "quota", *scope], check=False)
    print()
    print("--- Dollar mode (API users; subscription returns 0) ---")
    subprocess.run([sys.executable, str(TRACKER), "--mode", "dollar", *scope], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
