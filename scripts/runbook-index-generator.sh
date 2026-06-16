#!/usr/bin/env bash
# scripts/runbook-index-generator.sh — L7.B.16 (RAID cycle 35)
#
# Scans docs/sre/runbooks/**/*.md frontmatter and regenerates INDEX.md with:
#   - Alert → runbook map (3am fast lookup)
#   - Service → runbooks map
#   - Alphabetical index
#   - Overdue verification list (next_verification_due < today)
#   - Stub list (verification_method: stub)
#
# Usage: bash scripts/runbook-index-generator.sh
#
# Exit 0 on success. Always rewrites INDEX.md (CI hook ensures it stays current).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
runbooks_dir="${repo_root}/docs/sre/runbooks"
index_file="${runbooks_dir}/INDEX.md"

if [[ ! -d "${runbooks_dir}" ]]; then
    echo "[runbook-index-generator] FATAL: ${runbooks_dir} does not exist" >&2
    exit 1
fi

python3 - <<'PY'
import os
import re
import sys
import datetime
from pathlib import Path

repo_root = Path(os.environ.get("PWD", "."))
# Re-resolve via __file__ location semantics through subprocess CWD
script_root = Path(__file__).resolve().parent if "__file__" in dir() else repo_root
# Walk up to find docs/sre/runbooks
runbooks_dir = None
for candidate in (Path.cwd(), Path.cwd().parent):
    if (candidate / "docs/sre/runbooks").is_dir():
        runbooks_dir = candidate / "docs/sre/runbooks"
        break
if runbooks_dir is None:
    print("FATAL: cannot locate docs/sre/runbooks", file=sys.stderr)
    sys.exit(1)

today = datetime.date.today()

def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm_raw = text[4:end]
    fm = {}
    cur_key = None
    cur_list = None
    for line in fm_raw.splitlines():
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
            # list start on next lines
            fm[key] = []
            cur_list = fm[key]
            cur_key = key
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                fm[key] = [s.strip() for s in inner.split(",")]
            cur_list = None
            cur_key = None
            continue
        fm[key] = val
        cur_list = None
        cur_key = None
    return fm

runbooks = []
for path in sorted(runbooks_dir.rglob("*.md")):
    if path.name in ("README.md", "TEMPLATE.md", "INDEX.md"):
        continue
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if fm is None:
        continue
    rel = path.relative_to(runbooks_dir).as_posix()
    runbooks.append({"path": rel, "fm": fm})

# Build maps
alert_map = {}
service_map = {}
overdue = []
stubs = []
for rb in runbooks:
    fm = rb["fm"]
    alerts = fm.get("applies_to_alerts") or []
    if isinstance(alerts, str):
        alerts = [alerts]
    for a in alerts:
        alert_map.setdefault(a, []).append(rb["path"])
    services = fm.get("applies_to_services") or []
    if isinstance(services, str):
        services = [services]
    for s in services:
        service_map.setdefault(s, []).append(rb["path"])
    nvd_raw = fm.get("next_verification_due") or "1970-01-01"
    try:
        nvd = datetime.date.fromisoformat(nvd_raw)
    except Exception:
        nvd = datetime.date(1970, 1, 1)
    if nvd < today:
        overdue.append({"path": rb["path"], "due": nvd.isoformat()})
    if fm.get("verification_method") == "stub":
        stubs.append(rb["path"])

# Write INDEX.md
out = []
out.append("# SRE Runbook Index — auto-generated")
out.append("")
out.append(f"> **Generated:** {today.isoformat()}  ")
out.append(f"> **Generator:** `scripts/runbook-index-generator.sh`  ")
out.append(f"> **Total runbooks:** {len(runbooks)}  ")
out.append(f"> **Stubs (Q-L7B-1):** {len(stubs)}  ")
out.append(f"> **Overdue verification:** {len(overdue)}")
out.append("")
out.append("## Alert → Runbook (3am fast lookup)")
out.append("")
if not alert_map:
    out.append("_No alerts linked yet._")
else:
    out.append("| Alert | Runbook(s) |")
    out.append("|---|---|")
    for alert in sorted(alert_map.keys()):
        paths = alert_map[alert]
        links = ", ".join(f"[`{p}`]({p})" for p in paths)
        out.append(f"| `{alert}` | {links} |")
out.append("")
out.append("## Service → Runbooks")
out.append("")
if not service_map:
    out.append("_No services linked yet._")
else:
    out.append("| Service | Runbook(s) |")
    out.append("|---|---|")
    for svc in sorted(service_map.keys()):
        paths = service_map[svc]
        links = ", ".join(f"[`{p}`]({p})" for p in paths)
        out.append(f"| `{svc}` | {links} |")
out.append("")
out.append("## Alphabetical")
out.append("")
out.append("| Runbook | Owner | Last verified | Method |")
out.append("|---|---|---|---|")
for rb in sorted(runbooks, key=lambda r: r["path"]):
    fm = rb["fm"]
    out.append(f"| [`{rb['path']}`]({rb['path']}) | {fm.get('owner','?')} | {fm.get('last_verified','?')} | {fm.get('verification_method','?')} |")
out.append("")
out.append("## Overdue verification")
out.append("")
if not overdue:
    out.append("_None._")
else:
    out.append("| Runbook | Due |")
    out.append("|---|---|")
    for o in sorted(overdue, key=lambda r: r["due"]):
        out.append(f"| [`{o['path']}`]({o['path']}) | {o['due']} |")
out.append("")
out.append("## Stubs (Q-L7B-1 placeholders)")
out.append("")
if not stubs:
    out.append("_No stubs._")
else:
    for s in sorted(stubs):
        out.append(f"- [`{s}`]({s})")
out.append("")
out.append("---")
out.append("")
out.append("_This file is regenerated by `scripts/runbook-index-generator.sh`._")
out.append("_Do not edit by hand — your changes will be overwritten._")

(runbooks_dir / "INDEX.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"[runbook-index-generator] wrote {runbooks_dir / 'INDEX.md'} ({len(runbooks)} runbooks; {len(stubs)} stubs; {len(overdue)} overdue)")
PY

exit 0
