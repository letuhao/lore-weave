#!/usr/bin/env python3
"""
_quota_helper — internal helper for quota-check.sh (avoids shell-quoting hell).

Two modes:
  --classify <complexity>   → print integer cap from profile
  --decide --cycle <C> --quota-log <P> --profile <P>  → print DECISION:remaining:typical:burn
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path


def read_profile_int(profile_path: Path, key_path: list[str]) -> int:
    """Walk a simple YAML-by-indent for a nested int."""
    text = profile_path.read_text(encoding="utf-8")
    indent = 0
    cursor = 0
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        depth = (len(raw) - len(raw.lstrip())) // 2
        line = raw.strip()
        key = line.split(":", 1)[0].strip()
        if cursor < len(key_path) and depth == cursor and key == key_path[cursor]:
            val = line.split(":", 1)[1].strip() if ":" in line else ""
            if cursor + 1 == len(key_path):
                # final segment — extract int (may have underscores)
                m = re.match(r"^([\d_]+)", val)
                if m:
                    return int(m.group(1).replace("_", ""))
                return 0
            cursor += 1
            indent = depth + 1
    return 0


def classify(profile_path: Path, complexity: str) -> int:
    cap = read_profile_int(profile_path, ["dps_count_cap_per_complexity", complexity])
    return cap


def decide(cycle: str, quota_log: Path, profile: Path) -> tuple[str, int, int, int]:
    window_limit = read_profile_int(profile, ["limits", "five_hour_window_tokens_estimate"]) or 2_000_000
    typical = 0
    text = profile.read_text(encoding="utf-8")
    m = re.search(r"^typical_cycle_tokens:\s*([\d_]+)", text, re.MULTILINE)
    if m:
        typical = int(m.group(1).replace("_", ""))
    if typical == 0:
        typical = 450_000

    # Recent burn in last 5h
    now = time.time()
    burn = 0
    if quota_log.exists():
        for line in quota_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = time.mktime(time.strptime(d.get("ts", ""), "%Y-%m-%dT%H:%M:%SZ"))
            except ValueError:
                continue
            if ts >= now - 5 * 3600:
                burn += int(d.get("estimated_tokens", 0))

    remaining = max(0, window_limit - burn)
    proceed_threshold = typical * 3 // 2
    risky_threshold = typical // 2

    if remaining >= proceed_threshold:
        decision = "PROCEED"
    elif remaining >= risky_threshold:
        decision = "RISKY"
    else:
        decision = "WAIT"
    return decision, remaining, typical, burn


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--classify")
    p.add_argument("--decide", action="store_true")
    p.add_argument("--cycle")
    p.add_argument("--quota-log")
    p.add_argument("--profile")
    args = p.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    default_profile = repo_root / "contracts" / "raid" / "quota-profile.yaml"

    if args.classify:
        profile = Path(args.profile) if args.profile else default_profile
        print(classify(profile, args.classify))
        return 0

    if args.decide:
        profile = Path(args.profile) if args.profile else default_profile
        quota_log = Path(args.quota_log) if args.quota_log else (repo_root / "docs" / "raid" / "QUOTA_LOG.jsonl")
        decision, remaining, typical, burn = decide(args.cycle or "0", quota_log, profile)
        print(f"{decision}:{remaining}:{typical}:{burn}")
        return 0

    print("usage: _quota_helper.py --classify <complexity> | --decide --cycle <C>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
