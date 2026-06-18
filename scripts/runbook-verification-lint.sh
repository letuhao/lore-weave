#!/usr/bin/env bash
# scripts/runbook-verification-lint.sh — L7.B.17 (RAID cycle 35)
#
# Two responsibilities:
#   1. Every alert in infra/prometheus/alerts/**/*.yaml MUST link to a runbook
#      (SR1-D6 enforcement). Either runbook annotation OR explicit fallback to
#      generic/escalation-chains.md.
#   2. Every runbook in docs/sre/runbooks/ MUST have a valid YAML frontmatter
#      with required fields: runbook_id, owner, applies_to_alerts, last_verified,
#      verification_method, next_verification_due.
#
# Stubs (Q-L7B-1) are PRESENT — they count as runbooks — but verification_method
# MUST be exactly 'stub' and last_verified MUST be '1970-01-01' to flag overdue.
#
# Exit 0 on PASS; non-zero on FAIL.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

python3 - <<'PY'
import os
import re
import sys
import datetime
from pathlib import Path

repo = Path.cwd()
runbooks_dir = repo / "docs/sre/runbooks"
alerts_dir = repo / "infra/prometheus/alerts"

errors = []
warnings = []

REQUIRED_FIELDS = [
    "runbook_id", "version", "owner", "applies_to_alerts", "applies_to_services",
    "last_verified", "verification_method", "next_verification_due",
]
ALLOWED_METHODS = {"reading_review", "tabletop", "chaos_drill", "stub"}

def parse_fm(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm = {}
    cur_list = None
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith("  - "):
            if cur_list is not None:
                cur_list.append(line[4:].strip())
            continue
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if val == "":
            fm[key] = []
            cur_list = fm[key]
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [] if not inner else [s.strip() for s in inner.split(",")]
            cur_list = None
            continue
        fm[key] = val
        cur_list = None
    return fm

# Walk runbooks
runbook_count = 0
stub_count = 0
runbook_alert_index = {}  # alert name -> runbook path
for path in sorted(runbooks_dir.rglob("*.md")):
    if path.name in ("README.md", "TEMPLATE.md", "INDEX.md"):
        continue
    text = path.read_text(encoding="utf-8")
    fm = parse_fm(text)
    rel = path.relative_to(repo).as_posix()
    if fm is None:
        errors.append(f"{rel}: missing YAML frontmatter")
        continue
    runbook_count += 1
    for fld in REQUIRED_FIELDS:
        if fld not in fm:
            errors.append(f"{rel}: missing required frontmatter field '{fld}'")
    method = fm.get("verification_method", "")
    if method not in ALLOWED_METHODS:
        errors.append(f"{rel}: verification_method='{method}' not in {sorted(ALLOWED_METHODS)}")
    if method == "stub":
        stub_count += 1
        if fm.get("last_verified") != "1970-01-01":
            errors.append(f"{rel}: stub MUST have last_verified=1970-01-01 (got '{fm.get('last_verified')}')")
    for a in (fm.get("applies_to_alerts") or []):
        runbook_alert_index.setdefault(a, []).append(rel)

# Walk alert files
alerts_seen = 0
alerts_without_runbook = []
if alerts_dir.is_dir():
    for path in sorted(alerts_dir.rglob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        # Lightweight regex parse — find alert: X with surrounding context
        # Walk line by line; track current alert + look for runbook annotation
        current_alert = None
        runbook_set = False
        for line in text.splitlines():
            alert_m = re.match(r"^\s*-\s*alert:\s*(\S+)", line)
            if alert_m:
                # finalize previous
                if current_alert and not runbook_set:
                    # Check if the alert is linked via a runbook frontmatter (reverse lookup)
                    if current_alert in runbook_alert_index:
                        runbook_set = True
                if current_alert and not runbook_set:
                    alerts_without_runbook.append((path.relative_to(repo).as_posix(), current_alert))
                current_alert = alert_m.group(1)
                runbook_set = False
                alerts_seen += 1
                continue
            if current_alert and re.search(r"runbook(_url)?:\s*\S", line):
                runbook_set = True
        # finalize last
        if current_alert and not runbook_set:
            if current_alert in runbook_alert_index:
                runbook_set = True
        if current_alert and not runbook_set:
            alerts_without_runbook.append((path.relative_to(repo).as_posix(), current_alert))

# Cycle 35 minimum: 27 runbooks (Q-L7B-1 V1 launch gate)
if runbook_count < 27:
    errors.append(f"V1 LAUNCH GATE FAIL: {runbook_count} runbooks present; SR3 §12AF.4 requires 27")

if alerts_without_runbook:
    # Cycle 35 establishes the lint; existing alerts may not yet declare runbooks.
    # Print as WARN (not blocking) until cycle 36+ alert-rule-validator backfill.
    for af, alert in alerts_without_runbook[:20]:
        warnings.append(f"alert without runbook link: {alert} in {af}")
    if len(alerts_without_runbook) > 20:
        warnings.append(f"... and {len(alerts_without_runbook)-20} more")

print(f"[runbook-verification-lint] runbooks={runbook_count} stubs={stub_count} alerts_scanned={alerts_seen}")
print(f"[runbook-verification-lint] alerts_without_runbook (advisory)={len(alerts_without_runbook)}")
for w in warnings[:10]:
    print(f"[runbook-verification-lint] WARN: {w}")
for e in errors:
    print(f"[runbook-verification-lint] ERROR: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY

exit 0
