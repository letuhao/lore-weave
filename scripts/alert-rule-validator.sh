#!/usr/bin/env bash
# scripts/alert-rule-validator.sh — L7.J.7 (RAID cycle 34)
#
# CI lint: every alert rule in infra/prometheus/alerts/*.yaml MUST:
#   (1) appear in contracts/alerts/rules.yaml (alert-name match)
#   (2) reference a runbook that exists on disk
#   (3) carry severity + action labels (cycle-19 envelope shape)
#   (4) reference an sli_ref label OR be in the explicit pre-SLI grandfather list
#
# Exit codes:
#   0 — all rules valid
#   1 — at least one rule fails (per-rule reason emitted)
#   2 — usage error / dependency missing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALERTS_DIR="${LW_ALERTS_DIR:-${REPO_ROOT}/infra/prometheus/alerts}"
RULES_REGISTRY="${LW_ALERT_RULES_REGISTRY:-${REPO_ROOT}/contracts/alerts/rules.yaml}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[alert-rule-validator] python3 required" >&2
    exit 2
fi

if [[ ! -f "$RULES_REGISTRY" ]]; then
    echo "[alert-rule-validator] missing registry: $RULES_REGISTRY" >&2
    exit 2
fi

run_lint() {
python3 - "$ALERTS_DIR" "$RULES_REGISTRY" "$REPO_ROOT" <<'PYEOF'
import os
import re
import sys

alerts_dir, registry_path, repo_root = sys.argv[1], sys.argv[2], sys.argv[3]

# Pre-SLI alerts that pre-date SR1 §12AD; allowed without sli_ref AND
# allowed to be ABSENT from rules.yaml (the rules.yaml is treated as the
# cycle-34 EXTENSION registry per L7.J.6 — pre-cycle-34 alerts live only
# in infra/prometheus/alerts/*.yaml. Future work tracked as
# D-PRE-SLI-ALERTS-BACKFILL: build a full registry covering cycles 1-33).
PRE_SLI_GRANDFATHER = {
    "LWMetaPostgresPrimaryDown",
    "LWMetaPostgresSyncReplicaLag",
    "LWMetaPostgresAsyncReplicaLag",
    "LWMetaWriteAuditInsertStopped",
    "LWMetaWALArchiveStalled",
    "lw_migration_persistent_failure",
    "lw_migration_canary_aborted",
    "LWRealityDBSizeWarning",
    "LWRealityDBSizeCritical",
    "LWRealityDBConnectionsWarning",
    "LWRealityDBUnreachable",
    "LWRealityDBHighRollbackRate",
    "LWProjectionDriftWarning",
    "LWProjectionDriftCritical",
    "LWProjectionLagWarning",
    "LWProjectionLagCritical",
    "LWProjectionStaleVerification",
    "LWProjectionMonthlyDriftDetected",
    "LWWsConnectionSaturation",
    "LWWsHandshakeFailureSpike",
    "LWWsTicketReplayAttack",
    "LWWsOriginMismatchSpike",
    "LWWsFingerprintMismatchSpike",
    "LWWsAuthzRejectionSpike",
}


# Overridable so `--selftest` can drive the shrink arm with a set it controls.
# Without this, every synthetic probe trips the arm on all 24 real names — an
# arm reding for the right reason in the wrong case, which certifies nothing.
_gf = os.environ.get("LW_GF_OVERRIDE")
if _gf is not None:
    PRE_SLI_GRANDFATHER = {s for s in _gf.split(",") if s}


def parse_registry(path):
    """Return dict {alert_name: rule_dict}. Tiny YAML parser — handles the
    flat list-of-mappings shape used by rules.yaml. Avoids the gopkg yaml
    dep so this lint stays Go-free."""
    out = {}
    cur = None
    cur_name = None
    in_rules = False
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if line.startswith("rules:"):
                in_rules = True
                continue
            if not in_rules:
                continue
            # New rule entry begins with '  - alert: <name>'
            m = re.match(r"^\s*-\s*alert:\s*(\S+)", line)
            if m:
                if cur_name:
                    out[cur_name] = cur
                cur_name = m.group(1)
                cur = {"_lines": []}
                continue
            if cur is not None:
                cur["_lines"].append(line)
                m2 = re.match(r"^\s*(\w[\w_-]*):\s*(.*)$", line)
                if m2:
                    key, val = m2.group(1), m2.group(2)
                    if key not in cur:
                        cur[key] = val.strip()
        if cur_name:
            out[cur_name] = cur
    return out


def parse_prom_alerts(dirpath):
    """Scan infra/prometheus/alerts/*.yaml and return list of
    (alertname, file, labels, annotations) tuples."""
    out = []
    for root, _, files in os.walk(dirpath):
        for fname in files:
            if not (fname.endswith(".yaml") or fname.endswith(".yml")):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding="utf-8") as fh:
                lines = fh.readlines()
            cur_alert = None
            cur_labels = []
            cur_annots = []
            in_labels = False
            in_annots = False
            for line in lines:
                m = re.match(r"^\s*-\s*alert:\s*(\S+)", line)
                if m:
                    if cur_alert:
                        out.append((cur_alert, fpath, cur_labels, cur_annots))
                    cur_alert = m.group(1)
                    cur_labels = []
                    cur_annots = []
                    in_labels = False
                    in_annots = False
                    continue
                if re.match(r"^\s*labels:\s*$", line):
                    in_labels = True
                    in_annots = False
                    continue
                if re.match(r"^\s*annotations:\s*$", line):
                    in_labels = False
                    in_annots = True
                    continue
                if in_labels:
                    m2 = re.match(r"^\s+([\w_-]+):\s*(\S+.*)?$", line)
                    if m2:
                        cur_labels.append(m2.group(1))
                if in_annots:
                    m2 = re.match(r"^\s+([\w_-]+):\s*(\S+.*)?$", line)
                    if m2:
                        cur_annots.append((m2.group(1), m2.group(2) or ""))
            if cur_alert:
                out.append((cur_alert, fpath, cur_labels, cur_annots))
    return out


registry = parse_registry(registry_path)
prom_alerts = parse_prom_alerts(alerts_dir)

problems = []
checked = 0
for alertname, fpath, labels, annots in prom_alerts:
    checked += 1

    # (1) Must appear in registry (skip pre-SLI grandfathered alerts that
    # may not be re-declared in cycle-34's rules.yaml; only SLO + ws +
    # meta-postgres-primary are required there).
    if alertname not in registry and alertname not in PRE_SLI_GRANDFATHER:
        problems.append(f"{alertname} ({fpath}): NOT in contracts/alerts/rules.yaml")
        continue

    # (2) severity + action labels (cycle-19 envelope shape)
    if "severity" not in labels:
        problems.append(f"{alertname} ({fpath}): missing 'severity' label")
    if "action" not in labels and "route" not in labels:
        problems.append(f"{alertname} ({fpath}): missing 'action' or 'route' label (cycle-19 envelope)")

    # (3) runbook annotation — REQUIRED for cycle-34+ alerts; advisory
    # for grandfathered (pre-cycle-34) entries until D-PRE-SLI-ALERTS-BACKFILL
    runbook_val = None
    for k, v in annots:
        if k == "runbook":
            runbook_val = v.strip()
            break
    if not runbook_val:
        if alertname in PRE_SLI_GRANDFATHER:
            # advisory only — print but don't fail
            print(f"  [advisory] {alertname} ({fpath}): missing runbook annotation (grandfathered)")
        else:
            problems.append(f"{alertname} ({fpath}): missing runbook annotation")
    elif runbook_val.startswith("runbooks/"):
        rpath = os.path.join(repo_root, runbook_val)
        if not os.path.exists(rpath):
            if alertname in PRE_SLI_GRANDFATHER:
                print(f"  [advisory] {alertname} ({fpath}): runbook {runbook_val} not on disk (grandfathered)")
            else:
                problems.append(f"{alertname} ({fpath}): runbook {runbook_val} does not exist on disk")

    # (4) sli_ref (SR1 §12AD.7) — required unless grandfathered
    if "sli_ref" not in labels and alertname not in PRE_SLI_GRANDFATHER:
        problems.append(f"{alertname} ({fpath}): missing 'sli_ref' label (SR1 §12AD.7); not in PRE_SLI_GRANDFATHER")

# SHRINK ARM (`GT-F5`). Every grandfather row is an EXEMPTION, and an
# exemption with no expiry is permanent by default. Measured 2026-08-12:
# 14 of 38 rows named alerts that no longer exist anywhere on disk — 36% of
# the list exempting nothing, while looking like deliberate coverage. Worse,
# a dead row silently re-grandfathers the alert if the name ever comes back.
live_names = {a for a, _f, _l, _an in prom_alerts}
for name in sorted(PRE_SLI_GRANDFATHER - live_names):
    problems.append(
        f"PRE_SLI_GRANDFATHER names {name!r}, which is not an alert in "
        f"{alerts_dir} — the exemption applies to nothing; delete the row")

# REACH FLOOR. `os.walk` on a missing or renamed alerts directory yields
# nothing: `checked` stays 0, `problems` stays empty, and this prints
# "0 alerts validated" and exits 0 — a clean run over no subject.
if checked < 1 and not problems:
    print(f"[alert-rule-validator] FAIL — walked ZERO alert rules under {alerts_dir}. "
          "A scan that reaches nothing validates nothing, and reports it as success.",
          file=sys.stderr)
    sys.exit(2)

if problems:
    print(f"[alert-rule-validator] {len(problems)} problems in {checked} alerts:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    sys.exit(1)

print(f"[alert-rule-validator] {checked} alerts validated; {len(registry)} registry rows; "
      f"{len(PRE_SLI_GRANDFATHER)} grandfathered, all live")
PYEOF
}

_probe() {  # $1 = alert yaml text ("" = no alerts dir), $2 = registry text
  local d rc=0
  d="$(mktemp -d)"; mkdir -p "$d/alerts"
  [[ -n "$1" ]] && printf '%s' "$1" > "$d/alerts/a.yaml"
  printf '%s' "$2" > "$d/rules.yaml"
  ( ALERTS_DIR="$d/alerts" RULES_REGISTRY="$d/rules.yaml" REPO_ROOT="$d" LW_GF_OVERRIDE="${3-}" run_lint ) >/dev/null 2>&1 || rc=$?
  rm -rf "$d"
  printf '%s' "$rc"
}

selftest() {
  local rc
  local reg=$'rules:
  - alert: LWProbeAlert
    severity: page
'
  local ok=$'groups:
- name: g
  rules:
  - alert: LWProbeAlert
    labels:
      severity: page
      action: page
      sli_ref: sli.probe
    annotations:
      runbook: docs/x.md
'

  rc=$(_probe "$ok" "$reg")
  [[ "$rc" == "0" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - a fully-conformant alert did not pass (rc=$rc, cry-wolf)"; exit 2; }

  rc=$(_probe "${ok/LWProbeAlert/LWGhostAlert}" "$reg")
  [[ "$rc" == "1" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - an alert absent from the registry did not fail (rc=$rc, vacuous)"; exit 2; }

  rc=$(_probe "${ok/      severity: page
/}" "$reg")
  [[ "$rc" == "1" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - a missing severity label did not fail (rc=$rc)"; exit 2; }

  rc=$(_probe "${ok/      sli_ref: sli.probe
/}" "$reg")
  [[ "$rc" == "1" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - a missing sli_ref did not fail (rc=$rc)"; exit 2; }

  # THE REACH FLOOR: no alerts dir at all validated nothing and exited 0.
  rc=$(_probe "" "$reg")
  [[ "$rc" == "2" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - ZERO alerts walked did not trip the reach floor (rc=$rc)"; exit 2; }

  # THE SHRINK ARM: a grandfather row naming an alert that does not exist.
  rc=$(_probe "$ok" "$reg" "LWLongGoneAlert")
  [[ "$rc" == "1" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - a DEAD grandfather row was not reported (rc=$rc)"; exit 2; }

  rc=$(_probe "$ok" "$reg" "LWProbeAlert")
  [[ "$rc" == "0" ]] || { echo "[alert-rule-validator] SELFTEST FAIL - a LIVE grandfather row was reported dead (rc=$rc, cry-wolf)"; exit 2; }

  echo "[alert-rule-validator] SELFTEST PASS - a conformant alert passes; an unregistered one,"
  echo "  a missing severity label and a missing sli_ref each fail; and a walk that reaches zero"
  echo "  alert rules is refused rather than reported as 0-validated success"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
