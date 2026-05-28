#!/usr/bin/env python3
"""
Write/read docs/raid/IN_PROGRESS/cycle-<N>-state.md per RAID_WORKFLOW §12.3 P3.

State file is YAML-frontmatter + markdown body. The frontmatter is the
machine-readable handoff for crash-recovery + P5 protocol.

Usage:
  in-progress-state-writer.py init --cycle 1 --title "L1.E Meta HA"
  in-progress-state-writer.py update --cycle 1 --phase build --note "DPS-3 spawned"
  in-progress-state-writer.py dps-update --cycle 1 --dps-id 1 --status complete --commit-sha abc1234
  in-progress-state-writer.py read --cycle 1                     # prints YAML
  in-progress-state-writer.py archive --cycle 1                  # move to _archive/
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IN_PROGRESS_DIR = REPO_ROOT / "docs" / "raid" / "IN_PROGRESS"
ARCHIVE_DIR = IN_PROGRESS_DIR / "_archive"
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"

PHASES = [
    "CLARIFY", "DESIGN", "REVIEW1", "PLAN", "BUILD", "VERIFY",
    "REVIEW2", "QC", "POST_REVIEW", "SESSION", "COMMIT", "RETRO",
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def audit_append(event: str, **fields) -> None:
    row = {"ts": now_iso(), "event": event, **fields}
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def state_path(cycle: int) -> Path:
    return IN_PROGRESS_DIR / f"cycle-{cycle:03d}-state.md"


def write_state(cycle: int, fm: dict, body: str = "") -> None:
    """Write YAML-frontmatter + body atomically."""
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, (dict, list)):
            lines.append(f"{k}: {json.dumps(v)}")
        elif v is None:
            lines.append(f"{k}: null")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Cycle {cycle} in-progress state")
    lines.append("")
    if body:
        lines.append(body)
    text = "\n".join(lines) + "\n"
    p = state_path(cycle)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def parse_state(cycle: int) -> dict:
    """Return frontmatter dict; raises if file missing or malformed."""
    p = state_path(cycle)
    if not p.exists():
        raise FileNotFoundError(f"no IN_PROGRESS state for cycle {cycle}: {p}")
    text = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        raise ValueError(f"malformed frontmatter in {p}")
    fm: dict = {}
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        # Try JSON
        try:
            fm[k.strip()] = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            fm[k.strip()] = v.strip('"').strip("'")
    return fm


def cmd_init(args) -> int:
    fm = {
        "cycle": args.cycle,
        "title": args.title,
        "current_phase": "CLARIFY",
        "phase_started_at": now_iso(),
        "last_checkpoint_at": now_iso(),
        "retry_count": 0,
        "dps_status": [],
        "adversary_findings": None,
        "scope_guard_result": None,
        "verify_script_exit": None,
        "notes": args.note or "(init)",
    }
    write_state(args.cycle, fm, body=f"Initialized at {now_iso()} for `{args.title}`.")
    audit_append("in_progress_init", cycle=args.cycle, title=args.title)
    print(f"[in-progress] cycle {args.cycle} initialized")
    return 0


def cmd_update(args) -> int:
    fm = parse_state(args.cycle)
    if args.phase:
        if args.phase.upper() not in PHASES:
            print(f"unknown phase: {args.phase}", file=sys.stderr)
            return 2
        fm["current_phase"] = args.phase.upper()
        fm["phase_started_at"] = now_iso()
    fm["last_checkpoint_at"] = now_iso()
    if args.note:
        fm["notes"] = args.note
    if args.retry is not None:
        fm["retry_count"] = args.retry
    write_state(args.cycle, fm)
    audit_append(
        "in_progress_update",
        cycle=args.cycle,
        phase=fm.get("current_phase"),
        retry=fm.get("retry_count"),
    )
    print(f"[in-progress] cycle {args.cycle} updated → phase={fm['current_phase']}")
    return 0


def cmd_dps_update(args) -> int:
    fm = parse_state(args.cycle)
    dps_list = fm.get("dps_status") or []
    if isinstance(dps_list, str):
        dps_list = json.loads(dps_list)
    # find or append
    found = False
    for d in dps_list:
        if d.get("dps_id") == args.dps_id:
            d["status"] = args.status
            if args.commit_sha:
                d["commit_sha"] = args.commit_sha
            if args.branch:
                d["branch"] = args.branch
            d["updated_at"] = now_iso()
            found = True
            break
    if not found:
        dps_list.append({
            "dps_id": args.dps_id,
            "status": args.status,
            "branch": args.branch or "",
            "commit_sha": args.commit_sha or "",
            "updated_at": now_iso(),
        })
    fm["dps_status"] = dps_list
    fm["last_checkpoint_at"] = now_iso()
    write_state(args.cycle, fm)
    audit_append(
        "in_progress_dps_update",
        cycle=args.cycle,
        dps_id=args.dps_id,
        status=args.status,
    )
    print(f"[in-progress] cycle {args.cycle} DPS {args.dps_id} → {args.status}")
    return 0


def cmd_read(args) -> int:
    try:
        fm = parse_state(args.cycle)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(fm, indent=2))
    return 0


def cmd_archive(args) -> int:
    src = state_path(args.cycle)
    if not src.exists():
        print(f"no state to archive: {src}", file=sys.stderr)
        return 1
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dst = ARCHIVE_DIR / f"cycle-{args.cycle:03d}-state.md"
    if dst.exists():
        # add timestamp suffix to avoid clobber
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        dst = ARCHIVE_DIR / f"cycle-{args.cycle:03d}-state-{ts}.md"
    os.replace(src, dst)
    audit_append("in_progress_archived", cycle=args.cycle, archived_to=str(dst.name))
    print(f"[in-progress] cycle {args.cycle} archived → {dst}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init"); pi.add_argument("--cycle", type=int, required=True); pi.add_argument("--title", required=True); pi.add_argument("--note")
    pu = sub.add_parser("update"); pu.add_argument("--cycle", type=int, required=True); pu.add_argument("--phase"); pu.add_argument("--note"); pu.add_argument("--retry", type=int)
    pd = sub.add_parser("dps-update"); pd.add_argument("--cycle", type=int, required=True); pd.add_argument("--dps-id", type=int, required=True); pd.add_argument("--status", required=True); pd.add_argument("--commit-sha"); pd.add_argument("--branch")
    pr = sub.add_parser("read"); pr.add_argument("--cycle", type=int, required=True)
    pa = sub.add_parser("archive"); pa.add_argument("--cycle", type=int, required=True)

    args = p.parse_args(argv)
    if args.cmd == "init":     return cmd_init(args)
    if args.cmd == "update":   return cmd_update(args)
    if args.cmd == "dps-update": return cmd_dps_update(args)
    if args.cmd == "read":     return cmd_read(args)
    if args.cmd == "archive":  return cmd_archive(args)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
