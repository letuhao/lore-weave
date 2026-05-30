#!/usr/bin/env python3
"""
Append rows to docs/raid/ESCALATIONS.md per RAID_WORKFLOW §5 + §14.5 schema.

Row types supported (RAID_WORKFLOW v1.4):
  - error                       (true escalation; 3-retry exhausted, design gap, etc.)
  - quota_block                 (§14.5; recoverable; user resumes after reset)
  - p5_recovery_inconsistent    (R3-Adversary-R2-BLOCK-1; P5 8-step recovery halted)
  - spec_drift                  (R3-WARN-2 D-CYCLE-0-DRIFT-ENFORCER; header mismatch)
  - secret_leak                 (B6; gitleaks fired on DPS branch)

Usage:
  escalation-writer.py --type error --cycle 17 --phase build --reason "DPS-3 OOM after 3 retries"
  escalation-writer.py --type quota_block --cycle 17 --phase verify --reset-eta "2026-05-29T18:30Z"
  escalation-writer.py --type p5_recovery_inconsistent --cycle 17 --mismatch "IN_PROGRESS phase=commit but git HEAD does not match dps_status[0].commit_sha"
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ESCALATIONS = REPO_ROOT / "docs" / "raid" / "ESCALATIONS.md"
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def audit_append(event: str, **fields) -> None:
    row = {"ts": now_iso(), "event": event, **fields}
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


TEMPLATE = """\
## Cycle {cycle} — {title_for_type} — {date}

### Type
`{type}`

### Phase
{phase}

### Reason / details
{reason}

{extra}

### Suggested human action
{suggested_action}

---
"""


def title_for_type(t: str) -> str:
    return {
        "error": "ERROR (3-retry exhausted)",
        "quota_block": "QUOTA BLOCK (recoverable)",
        "p5_recovery_inconsistent": "P5 RECOVERY INCONSISTENT (halted)",
        "spec_drift": "SPEC DRIFT",
        "secret_leak": "SECRET LEAK (quarantined)",
    }.get(t, t.upper())


def suggested_for_type(t: str) -> str:
    return {
        "error": "Inspect AUDIT_LOG.jsonl + IN_PROGRESS state; fix root cause; re-invoke /raid <N>",
        "quota_block": "Wait for reset window; re-invoke /raid <N>; orchestrator resumes from IN_PROGRESS",
        "p5_recovery_inconsistent": "Manually investigate worktree state; run scripts/raid/recover-from-crash.sh --inspect; restore consistency before re-invoking",
        "spec_drift": "Re-run scripts/raid/regenerate-briefs.sh; sync CYCLE_DECOMPOSITION header version with RAID_WORKFLOW.md frontmatter; re-attempt cycle",
        "secret_leak": "Rotate the leaked credential immediately; review .gitleaks.toml allowlist; quarantined branch in ../foundation-worktrees/_quarantine/",
    }.get(t, "Investigate + decide manual or automated recovery path")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--type", required=True,
                   choices=["error", "quota_block", "p5_recovery_inconsistent",
                            "spec_drift", "secret_leak"])
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--phase", default="unknown")
    p.add_argument("--reason", default="(no reason provided)")
    p.add_argument("--mismatch", help="P5 inconsistency description")
    p.add_argument("--reset-eta", help="quota_block reset ETA (ISO)")
    p.add_argument("--retry-log", help="3-retry detail JSON path")
    args = p.parse_args(argv)

    extra_lines = []
    if args.type == "p5_recovery_inconsistent" and args.mismatch:
        extra_lines.append(f"### Mismatch\n{args.mismatch}")
    if args.type == "quota_block" and args.reset_eta:
        extra_lines.append(f"### Estimated reset\n{args.reset_eta}")
    if args.retry_log and Path(args.retry_log).exists():
        retry_text = Path(args.retry_log).read_text(encoding="utf-8")
        extra_lines.append(f"### 3-retry log\n```\n{retry_text}\n```")

    row = TEMPLATE.format(
        cycle=args.cycle,
        title_for_type=title_for_type(args.type),
        date=now_iso(),
        type=args.type,
        phase=args.phase,
        reason=args.reason,
        extra="\n\n".join(extra_lines),
        suggested_action=suggested_for_type(args.type),
    )

    ESCALATIONS.parent.mkdir(parents=True, exist_ok=True)
    with ESCALATIONS.open("a", encoding="utf-8") as f:
        f.write("\n" + row)

    audit_append(
        "escalation_written",
        cycle=args.cycle,
        type=args.type,
        phase=args.phase,
    )
    print(f"[escalation-writer] appended {args.type} row for cycle {args.cycle}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
