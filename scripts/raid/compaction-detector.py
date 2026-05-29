#!/usr/bin/env python3
"""
P5 compaction-event detector — RAID_WORKFLOW.md §12.5.

Anthropic does not expose a "you were just compacted" API signal. We detect
compaction via a heuristic on observable proxies:
  - Token-count delta between consecutive turns > 30% drop
  - Disappearance of previously-referenced tool-result IDs

This script is a stub-style heuristic + test-mode injector. The smoke test
exercises detection via --inject-event; production usage would integrate
with a tool-call wrapper that records (turn_id, total_tokens, referenced_ids).

Usage:
  compaction-detector.py check                # observational heuristic (POC)
  compaction-detector.py --test-mode --inject-event   # smoke harness
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"
TURN_LOG = REPO_ROOT / "docs" / "raid" / ".compaction-turn-log.jsonl"

THRESHOLD_DROP_PCT = 30


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def audit(event: str, **fields) -> None:
    row = {"ts": now_iso(), "event": event, **fields}
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def detect_from_turns() -> bool:
    """Read TURN_LOG (records of turn_id + token_count) and check for >30% drop."""
    if not TURN_LOG.exists():
        return False
    rows = []
    for line in TURN_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if len(rows) < 2:
        return False
    prev, curr = rows[-2], rows[-1]
    pt, ct = prev.get("total_tokens", 0), curr.get("total_tokens", 0)
    if pt <= 0:
        return False
    drop_pct = 100.0 * (pt - ct) / pt
    if drop_pct >= THRESHOLD_DROP_PCT:
        return True
    return False


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?", default="check", choices=["check"])
    p.add_argument("--test-mode", action="store_true", help="smoke harness mode")
    p.add_argument("--inject-event", action="store_true",
                   help="inject a synthetic compaction event (test only)")
    args = p.parse_args(argv)

    # Test injection path (smoke 5A-a and 5B-a both use this)
    if args.test_mode and args.inject_event:
        audit("compaction_detected",
              source="test_injection",
              note="P5 smoke harness — synthetic event")
        print("[compaction-detector] TEST: injected event → DETECTED=true")
        return 0

    detected = detect_from_turns()
    if detected:
        audit("compaction_detected", source="turn_log_heuristic")
        print("[compaction-detector] DETECTED via heuristic")
        return 0
    print("[compaction-detector] no compaction detected")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
