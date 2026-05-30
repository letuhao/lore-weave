#!/usr/bin/env python3
"""
coordinator-helper — RAID v1.5 Coordinator's next-pending-cycle query.

Reads docs/raid/CYCLE_LOG.md status board; returns the next cycle whose
dependencies are all DONE and whose status is PENDING. Used by /raid
Coordinator at each loop iteration.

Usage:
  coordinator-helper.py next-cycle              # emit JSON {cycle, brief_path, deps_satisfied, locked_qids} or {idle: true}
  coordinator-helper.py done-cycle <N> <sha>    # mark cycle <N> DONE in CYCLE_LOG.md
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CYCLE_LOG = REPO_ROOT / "docs" / "raid" / "CYCLE_LOG.md"
BRIEFS_DIR = REPO_ROOT / "docs" / "raid" / "cycle_briefs"
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def audit(event: str, **fields) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_iso(), "event": event, **fields}) + "\n")


def parse_cycle_log() -> list[dict]:
    """Parse CYCLE_LOG.md status table; return list of {num, status, brief_hint}."""
    if not CYCLE_LOG.exists():
        return []
    text = CYCLE_LOG.read_text(encoding="utf-8")
    rows = []
    # Look for table rows: | N | Title | STATUS | ...
    # The exact format depends on the CYCLE_LOG schema; try a permissive parse
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\w+)\s*\|", line)
        if m:
            num, title, status = m.groups()
            try:
                rows.append({
                    "num": int(num),
                    "title": title.strip(),
                    "status": status.strip().upper(),
                })
            except ValueError:
                continue
    return rows


def find_brief(cycle_num: int) -> Path | None:
    """Find the brief file for cycle_num via filename glob NN_*.md."""
    if cycle_num < 10:
        pat = f"0{cycle_num}_*.md"
    else:
        pat = f"{cycle_num}_*.md"
    matches = list(BRIEFS_DIR.glob(pat))
    return matches[0] if matches else None


def extract_deps_from_brief(brief_path: Path) -> list[int]:
    """Parse the brief 'Dependencies' section for cycle numbers."""
    if not brief_path.exists():
        return []
    text = brief_path.read_text(encoding="utf-8")
    # Look for "- Cycles: <list>" or "**Dependencies:** <list>"
    deps = []
    in_deps = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("## Dependencies"):
            in_deps = True
            continue
        if in_deps and line.startswith("##"):
            break
        if in_deps:
            # Find any "C<N>" or "Cycle <N>" or just numbers in context
            for m in re.finditer(r"\bC?(\d+)\b", line):
                try:
                    n = int(m.group(1))
                    if 1 <= n <= 50:  # plausible cycle range
                        deps.append(n)
                except ValueError:
                    continue
    return sorted(set(deps))


def extract_top_locked(brief_path: Path) -> list[str]:
    """Extract Q-IDs from TL;DR 'Top 3 LOCKED' line."""
    if not brief_path.exists():
        return []
    text = brief_path.read_text(encoding="utf-8")
    m = re.search(r"Top 3 LOCKED[^:]*:\*?\*?\s*([^\n]+)", text)
    if not m:
        return []
    line = m.group(1)
    qids = re.findall(r"Q-[A-Z0-9\-]+", line)
    return qids[:3]


def cmd_next_cycle() -> int:
    rows = parse_cycle_log()
    if not rows:
        # No CYCLE_LOG table parseable — fall back to brief filenames (cycles 1..38 PENDING by default)
        rows = [{"num": n, "status": "PENDING", "title": f"cycle {n}"} for n in range(1, 39)]

    done_set = {r["num"] for r in rows if r["status"] == "DONE"}
    pending = [r for r in rows if r["status"] == "PENDING"]

    for r in sorted(pending, key=lambda x: x["num"]):
        n = r["num"]
        if n == 0:
            continue  # C0 already shipped via default workflow
        brief = find_brief(n)
        if not brief:
            continue
        deps = extract_deps_from_brief(brief)
        unmet = [d for d in deps if d not in done_set and d != 0]
        if not unmet:
            result = {
                "cycle": n,
                "title": r["title"],
                "brief_path": str(brief.relative_to(REPO_ROOT)),
                "deps_satisfied": True,
                "locked_qids": extract_top_locked(brief),
            }
            print(json.dumps(result, indent=2))
            audit("coordinator_next_cycle_emitted", cycle=n)
            return 0

    # No pending cycle with deps satisfied
    print(json.dumps({"idle": True, "reason": "no pending cycle with satisfied deps"}, indent=2))
    audit("coordinator_idle")
    return 0


def cmd_done_cycle(cycle_num: int, sha: str) -> int:
    """Update CYCLE_LOG.md status board row for cycle_num to DONE."""
    if not CYCLE_LOG.exists():
        print(f"[coordinator-helper] CYCLE_LOG.md missing", file=sys.stderr)
        return 2
    text = CYCLE_LOG.read_text(encoding="utf-8")
    # Replace the status cell for this cycle (best-effort regex)
    pattern = rf"(\|\s*{cycle_num}\s*\|[^|]+\|\s*)PENDING(\s*\|)"
    replaced = re.sub(pattern, rf"\1DONE\2", text, count=1)
    if replaced == text:
        print(f"[coordinator-helper] WARN: no PENDING row for cycle {cycle_num} found", file=sys.stderr)
        # Still continue — board may already be DONE
    else:
        CYCLE_LOG.write_text(replaced, encoding="utf-8")
    audit("coordinator_done_cycle", cycle=cycle_num, sha=sha)
    print(f"[coordinator-helper] cycle {cycle_num} marked DONE (sha={sha[:8]})")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("next-cycle")
    pd = sub.add_parser("done-cycle")
    pd.add_argument("cycle", type=int)
    pd.add_argument("sha")
    args = p.parse_args(argv)
    if args.cmd == "next-cycle":
        return cmd_next_cycle()
    if args.cmd == "done-cycle":
        return cmd_done_cycle(args.cycle, args.sha)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
