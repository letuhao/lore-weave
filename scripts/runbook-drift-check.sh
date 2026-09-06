#!/usr/bin/env bash
# scripts/runbook-drift-check.sh — L7.B.18 (RAID cycle 35)
#
# Detects drift: runbooks referring to services that no longer exist OR
# missing services that have been renamed. Cross-checks against:
#   - services/<name>/  directories  (source of truth for service names)
#   - a small KNOWN_LOGICAL set for platform names with no services/ dir yet
#
# Exit 0 = no drift; 1 = drift or a dead allowlist row; 2 = misuse / selftest
# failure / the scan reached nothing.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12), and the allowlist audit that
# came with it.
#
# ⚠️ **`KNOWN_LOGICAL` WAS 91% DEAD.** It carried 23 names described as
# *"canonical platform names that aren't yet services/ dirs (will be V1+)"* —
# and measured 2026-08-12, **19 of them ARE services/ dirs** (they shipped; the
# real source of truth covers them) and **2 more are cited by no runbook at
# all**. Exactly **2** were load-bearing: `meta-postgres` and
# `projection-runner`. An allowlist that only grows stops being read, and this
# one had become a place where a genuinely-renamed service could hide: any of
# those 21 dead names would have silently satisfied a stale runbook reference.
# Trimmed to the two, with both shrink arms below so it cannot regrow silently.
#
# The trailing `exit 0` after the python block was CHECKED, not assumed: under
# `set -e` a python exit 1 aborts the script first, so drift is reported. It is
# kept, and the selftest covers the drift path end-to-end.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

# Overridable so `--selftest` can drive the REAL checker over a synthetic tree
# instead of re-implementing its logic — the defect that let twelve production
# rules be deleted with a sibling gate's self-test green.
: "${RB_RUNBOOKS_DIR:=docs/sre/runbooks}"
: "${RB_SERVICES_DIR:=services}"
: "${RB_KNOWN_LOGICAL:=meta-postgres,projection-runner}"
: "${RB_MIN_CHECKED:=1}"
export RB_RUNBOOKS_DIR RB_SERVICES_DIR RB_KNOWN_LOGICAL RB_MIN_CHECKED

run_lint() {
python3 - <<'PY'
import os
import re
import sys
from pathlib import Path

repo = Path.cwd()
runbooks_dir = repo / os.environ["RB_RUNBOOKS_DIR"]
services_dir = repo / os.environ["RB_SERVICES_DIR"]
known_logical = {s.strip() for s in os.environ["RB_KNOWN_LOGICAL"].split(",") if s.strip()}
min_checked = int(os.environ["RB_MIN_CHECKED"])

# Source of truth: directory names under services/
real_services = set()
if services_dir.is_dir():
    for entry in services_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            real_services.add(entry.name)

known_services = real_services | known_logical


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
declared = set()
for path in sorted(runbooks_dir.rglob("*.md")) if runbooks_dir.is_dir() else []:
    if path.name in ("README.md", "TEMPLATE.md", "INDEX.md"):
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
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
        declared.add(svc)
        if svc not in known_services:
            drift.append(f"{path.relative_to(repo).as_posix()}: unknown service '{svc}' (not in {services_dir.name}/ or KNOWN_LOGICAL)")

# REACH FLOOR. A missing/renamed runbooks directory makes `rglob` yield nothing,
# and "no drift over zero runbooks" is byte-identical to a clean tree, exit code
# included. Same for a corpus that has lost its frontmatter: `parse_fm` returns
# None and every file is skipped in silence.
if checked < min_checked:
    print(f"[runbook-drift-check] FAIL — checked {checked} runbook(s) with frontmatter "
          f"under {runbooks_dir}; a scan that reaches nothing reports no drift, which "
          f"is what a clean tree looks like")
    sys.exit(2)

# SHRINK ARMS. Every KNOWN_LOGICAL row is an exemption, and an exemption with no
# expiry is permanent by default. A row dies two ways.
dead = []
for name in sorted(known_logical):
    if name in real_services:
        dead.append(f"'{name}' is now a real {services_dir.name}/ directory — the real source "
                    f"of truth covers it, so the row is dead weight that could also hide a rename")
    elif name not in declared:
        dead.append(f"'{name}' is declared by no runbook — the row exempts nothing")

print(f"[runbook-drift-check] checked={checked} declared={len(declared)} "
      f"known_logical={len(known_logical)} drift={len(drift)} dead_rows={len(dead)}")
for d in drift:
    print(f"[runbook-drift-check] DRIFT: {d}")
for d in dead:
    print(f"[runbook-drift-check] DEAD ROW: {d}")
sys.exit(1 if (drift or dead) else 0)
PY
}

_probe() {  # $1 = runbook frontmatter body ("" = no runbooks), $2 = KNOWN_LOGICAL, $3 = service dirs
  local d rc=0 svc
  d="$(mktemp -d)"
  mkdir -p "$d/rb" "$d/svc"
  [[ -n "$1" ]] && printf '%s' "$1" > "$d/rb/one.md"
  for svc in ${3:-}; do mkdir -p "$d/svc/$svc"; done
  (
    cd "$d"
    RB_RUNBOOKS_DIR=rb RB_SERVICES_DIR=svc RB_KNOWN_LOGICAL="$2" RB_MIN_CHECKED=1 \
      run_lint
  ) >/dev/null 2>&1 || rc=$?
  rm -rf "$d"
  printf '%s' "$rc"
}

selftest() {
  local rc
  local rb_real=$'---\ntitle: x\napplies_to_services: [alpha]\n---\n\nbody\n'

  # A runbook naming a REAL service dir -> clean. KNOWN_LOGICAL is EMPTY here
  # and in every probe where it is not the subject: a logical row nothing cites
  # is itself a finding (shrink arm 2), so leaving one in would make every
  # unrelated probe red for the wrong reason.
  rc=$(_probe "$rb_real" "" "alpha")
  [[ "$rc" == "0" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — a runbook naming a real service did not pass (rc=$rc, cry-wolf)"; exit 2; }

  # A runbook naming a service that exists NOWHERE -> drift.
  rc=$(_probe $'---\ntitle: x\napplies_to_services: [ghost]\n---\n' "" "alpha")
  [[ "$rc" == "1" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — an UNKNOWN service was not reported as drift (rc=$rc, vacuous)"; exit 2; }

  # A runbook naming a KNOWN_LOGICAL name -> clean (that is what the list is for).
  rc=$(_probe $'---\ntitle: x\napplies_to_services: [meta-postgres]\n---\n' "meta-postgres" "alpha")
  [[ "$rc" == "0" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — a KNOWN_LOGICAL name was reported as drift (rc=$rc)"; exit 2; }

  # SHRINK ARM 1 — a logical row that is now a real service dir.
  rc=$(_probe "$rb_real" "alpha" "alpha")
  [[ "$rc" == "1" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — a KNOWN_LOGICAL row that is NOW a real service dir was not reported dead (rc=$rc)"; exit 2; }

  # SHRINK ARM 2 — a logical row no runbook declares.
  rc=$(_probe "$rb_real" "nobody-cites-me" "alpha")
  [[ "$rc" == "1" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — a KNOWN_LOGICAL row cited by NO runbook was not reported dead (rc=$rc)"; exit 2; }

  # THE FLOOR — no runbooks at all, and a runbook with no frontmatter. Both make
  # the scan reach nothing, which reports no drift.
  rc=$(_probe "" "" "alpha")
  [[ "$rc" == "2" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — an EMPTY runbooks dir did not trip the reach floor (rc=$rc)"; exit 2; }

  rc=$(_probe $'no frontmatter here\njust prose\n' "" "alpha")
  [[ "$rc" == "2" ]] || { echo "[runbook-drift-check] SELFTEST FAIL — a corpus with NO frontmatter did not trip the reach floor (rc=$rc)"; exit 2; }

  echo "[runbook-drift-check] SELFTEST PASS — a real service passes, an unknown one is drift,"
  echo "  a KNOWN_LOGICAL name is accepted; both shrink arms report a dead row (now-real, and"
  echo "  cited-by-nobody); and the floor trips on an empty corpus AND on one that has lost its"
  echo "  frontmatter — the two ways this scan reaches nothing while reporting no drift"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
