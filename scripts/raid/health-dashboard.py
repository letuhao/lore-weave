#!/usr/bin/env python3
"""
health-dashboard — P10 per-cycle health gauge
Per RAID_WORKFLOW.md §12.10.

Reads AUDIT_LOG.jsonl + QUOTA_LOG.jsonl; emits per-cycle health summary.

Usage:
  health-dashboard.py <cycle>          # one cycle
  health-dashboard.py --all            # all cycles
"""
from __future__ import annotations
import argparse
import collections
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"
QUOTA_LOG = REPO_ROOT / "docs" / "raid" / "QUOTA_LOG.jsonl"


def parse_iso(s: str) -> float:
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return 0.0


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def cycle_summary(cycle: int, audit_rows: list[dict], quota_rows: list[dict]) -> dict:
    cycle_audit = [r for r in audit_rows if r.get("cycle") == cycle]
    cycle_quota = [r for r in quota_rows if r.get("cycle") == cycle]

    if not cycle_audit:
        return {"cycle": cycle, "status": "no events"}

    start_ts = parse_iso(cycle_audit[0].get("ts", ""))
    end_ts = parse_iso(cycle_audit[-1].get("ts", ""))
    wall_time = max(0, int(end_ts - start_ts))

    sub_agent_invocations = sum(
        1 for r in cycle_audit
        if r.get("event") in ("sub_agent_spawn_resolved", "dps_complete",
                              "adversary_findings", "scope_guard")
    )
    compaction_events = sum(1 for r in cycle_audit if r.get("event") == "compaction_detected")
    drift_events = sum(1 for r in cycle_audit if r.get("event") in ("recovery_halted", "startup_drift_detected"))
    total_tokens = sum(int(r.get("estimated_tokens", 0)) for r in cycle_quota)

    # Memory pressure heuristic: peak tokens / 150K ceiling
    pressure_pct = (total_tokens / 150_000) * 100 if total_tokens else 0
    pressure = "low" if pressure_pct < 50 else "medium" if pressure_pct < 80 else "high"

    return {
        "cycle": cycle,
        "wall_time_seconds": wall_time,
        "wall_time_human": f"{wall_time // 3600}h {(wall_time % 3600) // 60}min",
        "sub_agent_invocations": sub_agent_invocations,
        "raid_leader_tokens_est": total_tokens,
        "ceiling_pct": round(pressure_pct, 1),
        "memory_pressure": pressure,
        "compaction_events": compaction_events,
        "drift_events": drift_events,
    }


def print_summary(s: dict) -> None:
    cyc = s.get("cycle", "?")
    if s.get("status") == "no events":
        print(f"Cycle {cyc}: no audit events")
        return
    print(f"Cycle {cyc}")
    print(f"├─ Wall time: {s.get('wall_time_human','?')}")
    print(f"├─ Sub-agent invocations: {s.get('sub_agent_invocations',0)}")
    print(f"├─ Raid Leader peak tokens (est): {s.get('raid_leader_tokens_est',0):,} / 150K ({s.get('ceiling_pct',0)}%)")
    print(f"├─ Compaction events detected: {s.get('compaction_events',0)}")
    print(f"├─ Memory pressure: {s.get('memory_pressure','?')}")
    print(f"└─ Drift events: {s.get('drift_events',0)}")
    print()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cycle", nargs="?", type=int, default=None)
    p.add_argument("--all", action="store_true")
    args = p.parse_args(argv)

    audit = load_jsonl(AUDIT_LOG)
    quota = load_jsonl(QUOTA_LOG)

    if args.all or args.cycle is None:
        cycles = sorted({r.get("cycle") for r in audit if isinstance(r.get("cycle"), int)})
        for c in cycles:
            print_summary(cycle_summary(c, audit, quota))
    else:
        print_summary(cycle_summary(args.cycle, audit, quota))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
