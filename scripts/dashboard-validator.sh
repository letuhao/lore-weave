#!/usr/bin/env bash
# scripts/dashboard-validator.sh — L7.H.11 (RAID cycle 33)
#
# CI lint: every dashboard JSON in dashboards/ must conform to
# dashboards/_library/STANDARDS.md.
#
# Checks (cycle 33 v1):
#   1. Valid JSON
#   2. `title` non-empty
#   3. `uid` non-empty + kebab-case
#   4. `tags` array exists and includes at least one cycle-<N> tag
#   5. `panels` array exists; every panel has a non-empty `title`
#   6. Every panel `datasource.uid` is one of the LOCKED set:
#      prom-primary / prom-secondary / loki-primary / thanos-query
#   7. `refresh` present (any value)
#   8. `time.from` and `time.to` present
#   9. `timezone` field present
#
# Exit codes:
#   0 — all dashboards pass
#   1 — at least one dashboard fails (lint emits per-dashboard reason)
#   2 — usage error / missing dependency

set -euo pipefail

DASH_ROOT="${LW_DASHBOARD_ROOT:-dashboards}"

# Default LOCKED datasource UIDs (cycle 33 — see STANDARDS.md).
ALLOWED_UIDS=(
    prom-primary
    prom-secondary
    loki-primary
    thanos-query
)

if ! command -v python3 >/dev/null 2>&1; then
    echo "[dashboard-validator] python3 required for JSON parsing" >&2
    exit 2
fi

EXIT=0

check_dashboard() {
    local f="$1"

    # Run all checks inside python for speed + portability.
    python3 - "$f" "${ALLOWED_UIDS[@]}" <<'PYEOF'
import json
import re
import sys

f = sys.argv[1]
allowed_uids = set(sys.argv[2:])

try:
    with open(f, encoding='utf-8') as fh:
        d = json.load(fh)
except Exception as e:
    print(f"[FAIL] {f}: invalid JSON: {e}", file=sys.stderr)
    sys.exit(1)

problems = []

# 1+2: title
title = d.get("title", "")
if not title:
    problems.append("title missing or empty")

# 3: uid kebab-case
uid = d.get("uid", "")
if not uid:
    problems.append("uid missing")
elif not re.match(r'^[a-z0-9][a-z0-9_-]*$', uid):
    problems.append(f"uid '{uid}' not kebab-case")

# 4: tags include cycle-<N>
tags = d.get("tags", [])
if not isinstance(tags, list):
    problems.append("tags not a list")
else:
    has_cycle = any(re.match(r'^cycle-\d+$', t) for t in tags if isinstance(t, str))
    if not has_cycle:
        problems.append("tags missing cycle-<N> entry")

# 5+6: panels + their titles + datasource UIDs
panels = d.get("panels", [])
if not isinstance(panels, list):
    problems.append("panels not a list")
else:
    for i, p in enumerate(panels):
        if not isinstance(p, dict):
            continue
        if not p.get("title"):
            problems.append(f"panel #{i+1} title missing")
        ds = p.get("datasource")
        if isinstance(ds, dict):
            ds_uid = ds.get("uid", "")
            if ds_uid and ds_uid not in allowed_uids:
                problems.append(f"panel #{i+1} datasource.uid '{ds_uid}' not in LOCKED set {sorted(allowed_uids)}")
        # nested panels (row collapsed)
        for j, sp in enumerate(p.get("panels", []) or []):
            if isinstance(sp, dict):
                ds = sp.get("datasource")
                if isinstance(ds, dict):
                    ds_uid = ds.get("uid", "")
                    if ds_uid and ds_uid not in allowed_uids:
                        problems.append(f"panel #{i+1}.subpanel #{j+1} datasource.uid '{ds_uid}' not in LOCKED set")

# 7: refresh
if not d.get("refresh"):
    problems.append("refresh missing")

# 8: time.from / time.to
t = d.get("time", {})
if not (isinstance(t, dict) and t.get("from") and t.get("to")):
    problems.append("time.from/to missing")

# 9: timezone
if not d.get("timezone"):
    problems.append("timezone missing")

if problems:
    print(f"[FAIL] {f}:")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
else:
    print(f"[OK]   {f}")
PYEOF
}

# Grandfathered dashboards (pre-STANDARDS.md, cycle 6) — these will be
# backfilled in a dedicated cycle (D-DASHBOARD-STANDARDS-BACKFILL). The
# validator reports their violations as INFO but does not exit-1 on them.
# A future cycle that does the backfill removes them from this list.
declare -A GRANDFATHERED
GRANDFATHERED[dashboards/backup-verification.json]=1
GRANDFATHERED[dashboards/capacity-planner.json]=1
GRANDFATHERED[dashboards/per-reality-health.json]=1
GRANDFATHERED[dashboards/projection-health.json]=1
GRANDFATHERED[dashboards/shard-health.json]=1
GRANDFATHERED[dashboards/ws-health.json]=1

# The _library/TEMPLATE.json is the template itself — the uid "_template"
# is intentionally non-kebab-case (the underscore marks it as not for prod
# use). Validator soft-skips template files.
declare -A TEMPLATE_FILES
TEMPLATE_FILES[dashboards/_library/TEMPLATE.json]=1

# Find all dashboard JSONs under dashboards/ EXCEPT the validator's own
# fixtures (any *.fixture.json).
shopt -s nullglob
mapfile -d '' files < <(find "$DASH_ROOT" -type f -name '*.json' \
    ! -name '*.fixture.json' -print0)

if [ "${#files[@]}" -eq 0 ]; then
    echo "[dashboard-validator] no dashboards found under $DASH_ROOT" >&2
    exit 2
fi

for f in "${files[@]}"; do
    rel="${f#./}"
    if [ "${GRANDFATHERED[$rel]:-0}" = "1" ]; then
        if ! check_dashboard "$f"; then
            echo "[INFO grandfathered] $rel — pre-STANDARDS.md; backfill tracked as D-DASHBOARD-STANDARDS-BACKFILL"
        fi
        continue
    fi
    if [ "${TEMPLATE_FILES[$rel]:-0}" = "1" ]; then
        # Template files get a softer check (uid is intentionally _template)
        if ! check_dashboard "$f" 2>/dev/null; then
            echo "[INFO template] $rel — exempted (uid '_template' intentional)"
        fi
        continue
    fi
    if ! check_dashboard "$f"; then
        EXIT=1
    fi
done

if [ "$EXIT" -eq 0 ]; then
    echo "[dashboard-validator] all ${#files[@]} dashboards conform"
else
    echo "[dashboard-validator] one or more dashboards failed validation" >&2
fi

exit "$EXIT"
