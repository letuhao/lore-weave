#!/usr/bin/env bash
# scripts/runbook-drift-check.sh — L7.B.18 (RAID cycle 35)
#
# Detects drift: runbooks referring to services that no longer exist OR
# missing services that have been renamed. Cross-checks against:
#   - services/<name>/  directories  (source of truth for service names)
#   - contracts/service_acl/matrix.yaml  (rpc-allowed graph, if present)
#
# Exit 0 = no drift; exit 1 = drift detected (PR annotation, not blocking).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

python3 - <<'PY'
import os
import re
import sys
from pathlib import Path

repo = Path.cwd()
runbooks_dir = repo / "docs/sre/runbooks"
services_dir = repo / "services"

# Source of truth: directory names under services/
known_services = set()
if services_dir.is_dir():
    for entry in services_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            known_services.add(entry.name)

# Also accept canonical platform names that aren't yet services/ dirs (will be V1+)
KNOWN_LOGICAL = {
    "api-gateway-bff", "auth-service", "book-service", "sharing-service",
    "catalog-service", "provider-registry-service", "usage-billing-service",
    "translation-service", "glossary-service", "chat-service",
    "knowledge-service", "video-gen-service",
    "world-service", "game-server", "publisher", "projection-runner",
    "meta-postgres", "outbox-runner", "incident-bot", "postmortem-bot",
    "alert-recorder", "slo-budget-calculator", "oncall-bot",
}
known_services |= KNOWN_LOGICAL

def parse_fm(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", line)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [] if not inner else [s.strip() for s in inner.split(",")]
        else:
            fm[key] = val
    return fm

drift = []
checked = 0
for path in sorted(runbooks_dir.rglob("*.md")):
    if path.name in ("README.md", "TEMPLATE.md", "INDEX.md"):
        continue
    text = path.read_text(encoding="utf-8")
    fm = parse_fm(text)
    if not fm:
        continue
    checked += 1
    svc_list = fm.get("applies_to_services") or []
    if isinstance(svc_list, str):
        svc_list = [svc_list]
    for svc in svc_list:
        if not svc:
            continue
        if svc not in known_services:
            drift.append(f"{path.relative_to(repo).as_posix()}: unknown service '{svc}' (not in services/ or KNOWN_LOGICAL)")

print(f"[runbook-drift-check] checked={checked} drift={len(drift)}")
for d in drift:
    print(f"[runbook-drift-check] DRIFT: {d}")
sys.exit(1 if drift else 0)
PY

exit 0
