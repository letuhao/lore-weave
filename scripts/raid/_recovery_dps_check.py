#!/usr/bin/env python3
"""
_recovery_dps_check — internal helper for recovery-protocol-runner.sh.

Reads IN_PROGRESS state for cycle <N>, checks each DPS with status=complete
has a commit_sha that exists in git. Prints semicolon-separated errors to
stdout; exits 0 (errors are data, not exit code).

Usage: _recovery_dps_check.py <cycle_padded_string>
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: _recovery_dps_check.py <cycle>", file=sys.stderr)
        return 2
    cycle = argv[0]
    state_path = REPO_ROOT / "docs" / "raid" / "IN_PROGRESS" / f"cycle-{cycle}-state.md"
    if not state_path.exists():
        return 0  # no state → no DPS check
    text = state_path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return 0
    dps_list = []
    for line in m.group(1).splitlines():
        if line.startswith("dps_status:"):
            val = line.split(":", 1)[1].strip()
            try:
                dps_list = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                pass
            break
    errs = []
    for d in dps_list:
        if isinstance(d, dict) and d.get("status") == "complete":
            sha = d.get("commit_sha", "")
            if sha:
                r = subprocess.run(
                    ["git", "cat-file", "-e", sha],
                    cwd=REPO_ROOT,
                    capture_output=True,
                )
                if r.returncode != 0:
                    errs.append(f"DPS {d.get('dps_id')} commit_sha={sha} not in git")
    if errs:
        print("; ".join(errs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
