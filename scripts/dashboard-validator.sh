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

run_lint() {
EXIT=0
# READ INSIDE the function, not at script load. It was a top-level assignment,
# so `--selftest`'s probes — which set `LW_DASHBOARD_ROOT` per invocation — all
# ran against the REAL `dashboards/` tree and every case passed by accident. A
# self-test that never reaches its own fixture is worse than none: it reports
# coverage of synthetic inputs it never read.
local DASH_ROOT="${LW_DASHBOARD_ROOT:-dashboards}"

# Grandfathered dashboards (pre-STANDARDS.md). RAID cycle 33 introduced
# STANDARDS.md + grandfathered 6 pre-existing dashboards.
# RAID cycle 34 BACKFILLED all 6 to STANDARDS.md conformance
# (D-DASHBOARD-STANDARDS-BACKFILL row 062 ADDRESSED).
# The list now empty — any new pre-STANDARDS.md dashboard MUST be brought
# up to standard in the cycle that introduces it.
declare -A GRANDFATHERED
# (intentionally empty post-cycle-34 backfill)

# The _library/TEMPLATE.json is the template itself — the uid "_template"
# is intentionally non-kebab-case (the underscore marks it as not for prod
# use). Validator soft-skips template files.
# Overridable so the cases can drive BOTH the narrowed exemption and the shrink
# arm. Without this the template branch and the shrink arm had no case at all —
# their bite arms stayed GREEN when disabled, which is how a rule added today
# becomes deletable tomorrow with the suite still passing.
declare -A TEMPLATE_FILES
# `+x` tests whether the variable is SET, not whether it is non-empty. A probe
# that wants NO template exemptions passes an empty string, and `-n "${VAR-}"`
# would have silently handed it the production default instead — which then
# trips the shrink arm on a path that does not exist in the probe's tree.
local _tf
if [ -n "${LW_TEMPLATE_FILES+x}" ]; then
    for _tf in ${LW_TEMPLATE_FILES//,/ }; do TEMPLATE_FILES[$_tf]=1; done
else
    TEMPLATE_FILES[dashboards/_library/TEMPLATE.json]=1
fi

# Find all dashboard JSONs under dashboards/ EXCEPT the validator's own
# fixtures (any *.fixture.json).
# SHRINK ARMS (`GT-F5`). Both maps above are exemption lists keyed by PATH, and
# a path that no longer exists exempts nothing while looking like a decision.
# Three other lists in this repo measured 36–91% dead; these are armed while
# they are still clean.
for _rel in "${!GRANDFATHERED[@]}" "${!TEMPLATE_FILES[@]}"; do
    if [ ! -f "$_rel" ]; then
        echo "[dashboard-validator] FAIL — exemption row '$_rel' names a file that does not" >&2
        echo "                      exist; the exemption applies to nothing. Delete the row." >&2
        exit 1
    fi
done

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
        # EXEMPT THE UID RULE, NOT THE FILE.
        #
        # This was `check_dashboard "$f" 2>/dev/null` — which swallowed EVERY
        # problem in the file and then reported the uid as the reason. The
        # stated exemption ("uid '_template' is intentionally non-kebab-case")
        # is ONE rule; the implemented exemption was all nine. A template that
        # lost its `timezone`, or stopped being valid JSON, would have been
        # waved through under a justification that does not cover it.
        #
        # Measured 2026-08-12 before narrowing: TEMPLATE.json fails the uid rule
        # and nothing else, so this reds nothing today — the right moment to
        # narrow an exemption rather than the urgent one.
        tmpl_out="$(check_dashboard "$f" 2>&1 || true)"
        tmpl_others="$(printf '%s\n' "$tmpl_out" | grep '^  - ' | grep -v 'not kebab-case' || true)"
        if [ -n "$tmpl_others" ]; then
            echo "[FAIL] $rel — exempted for its uid ONLY, but it also fails:"
            printf '%s\n' "$tmpl_others"
            EXIT=1
        else
            echo "[INFO template] $rel — uid rule exempted ('_template' intentional); all other rules pass"
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
}

_probe() {  # $1 = dashboard json ("" = empty root), $2 = LW_TEMPLATE_FILES override
  local d rc=0
  d="$(mktemp -d)"; mkdir -p "$d/dash"
  [[ -n "$1" ]] && printf '%s' "$1" > "$d/dash/x.json"
  ( cd "$d" && LW_DASHBOARD_ROOT="dash" LW_TEMPLATE_FILES="${2-}" run_lint ) >/dev/null 2>&1 || rc=$?
  rm -rf "$d"
  printf '%s' "$rc"
}

selftest() {
  local rc
  local ok='{"title":"T","uid":"my-dash","tags":["cycle-34"],"panels":[{"title":"P","datasource":{"uid":"prom-primary"}}],"refresh":"30s","time":{"from":"now-6h","to":"now"},"timezone":"utc"}'

  rc=$(_probe "$ok")
  [[ "$rc" == "0" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a conformant dashboard did not pass (rc=$rc, cry-wolf)"; exit 2; }

  rc=$(_probe "${ok/\"uid\":\"my-dash\"/\"uid\":\"NotKebab\"}")
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a non-kebab uid did not fail (rc=$rc, vacuous)"; exit 2; }

  rc=$(_probe "${ok/prom-primary/rogue-datasource}")
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a datasource outside the LOCKED set did not fail (rc=$rc)"; exit 2; }

  rc=$(_probe "${ok/,\"timezone\":\"utc\"/}")
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a missing timezone did not fail (rc=$rc)"; exit 2; }

  rc=$(_probe "${ok/\"cycle-34\"/\"misc\"}")
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a missing cycle-<N> tag did not fail (rc=$rc)"; exit 2; }

  rc=$(_probe '{not json')
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - invalid JSON did not fail (rc=$rc)"; exit 2; }

  # THE REACH FLOOR (this gate already had it - the case proves it stays).
  rc=$(_probe "")
  [[ "$rc" == "2" ]] || { echo "[dashboard-validator] SELFTEST FAIL - an EMPTY dashboard root did not trip the reach floor (rc=$rc)"; exit 2; }

  # THE NARROWED TEMPLATE EXEMPTION. A template may be excused its uid and
  # NOTHING ELSE. Both directions, because the old code excused all nine rules
  # under a justification that named one.
  rc=$(_probe "${ok/\"uid\":\"my-dash\"/\"uid\":\"_template\"}" "dash/x.json")
  [[ "$rc" == "0" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a template failing ONLY the uid rule was not exempted (rc=$rc, cry-wolf)"; exit 2; }

  rc=$(_probe "${ok/,\"timezone\":\"utc\"/}" "dash/x.json")
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - a template with a missing timezone was exempted anyway (rc=$rc);"; echo "  the exemption is wider than the uid rule it claims to be"; exit 2; }

  # THE EXEMPTION-PATH SHRINK ARM: a row naming a file that is not there.
  rc=$(_probe "$ok" "dash/does-not-exist.json")
  [[ "$rc" == "1" ]] || { echo "[dashboard-validator] SELFTEST FAIL - an exemption row naming a MISSING file was not reported (rc=$rc)"; exit 2; }

  echo "[dashboard-validator] SELFTEST PASS - a conformant dashboard passes; a non-kebab uid, an"
  echo "  unlocked datasource, a missing timezone, a missing cycle tag and invalid JSON each fail;"
  echo "  and an empty dashboard root is refused rather than reported as 0 conforming"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
