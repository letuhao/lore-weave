#!/usr/bin/env python3
"""
session-counter — Q8 50-session/month soft-cap tracker
Per RAID_WORKFLOW.md §14.8.

Counts new-session-spawn events from CYCLE_LOG.md (one session ≈ one cycle
invocation per P1 fresh-session-per-cycle). Warns at 40 sessions used in
current month; halts at 48 (2-session safety buffer).

Usage:
  session-counter.py                  # current month count + recommendation
  session-counter.py increment        # record a new session start
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUOTA_LOG = REPO_ROOT / "docs" / "raid" / "QUOTA_LOG.jsonl"
SESSIONS_FILE = REPO_ROOT / "docs" / "raid" / "_session-count.json"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def current_month() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_sessions(data: dict) -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SESSIONS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(SESSIONS_FILE)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?", default="status", choices=["status", "increment"])
    args = p.parse_args(argv)

    sessions = load_sessions()
    month = current_month()
    count = sessions.get(month, 0)

    if args.cmd == "increment":
        count += 1
        sessions[month] = count
        save_sessions(sessions)
        # Also log to QUOTA_LOG
        QUOTA_LOG.parent.mkdir(parents=True, exist_ok=True)
        with QUOTA_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": now_iso(),
                "event": "session_increment",
                "month": month,
                "count": count,
            }) + "\n")

    # Status report
    if count < 40:
        status, exit_code = "OK", 0
    elif count < 48:
        status, exit_code = "WARN", 1
    else:
        status, exit_code = "HALT", 2

    print(f"month: {month}")
    print(f"sessions_used: {count} / 50 (Max 20x soft cap)")
    print(f"status: {status}")
    if status == "WARN":
        print("note: approaching cap; consider deferring non-foundation usage")
    elif status == "HALT":
        print("note: 2-session safety buffer reached; foundation paused")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
