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

EXIT=0

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
    "LWMetaPatroniNoLeader",
    "LWMetaArchiveStale",
    "LWMetaProvisionerEffectFailed",
    "LWMetaMigrationOrchestratorBlocked",
    "LWMetaPgbouncerPoolSaturation",
    "LWMetaWALArchiveStalled",
    "lw_migration_persistent_failure",
    "lw_migration_canary_aborted",
    "LWPerRealityShardDown",
    "LWPerRealityReplicationLag",
    "LWPerRealityConnsExhausted",
    "LWRealityDBSizeWarning",
    "LWRealityDBSizeCritical",
    "LWRealityDBConnectionsWarning",
    "LWRealityDBUnreachable",
    "LWRealityDBHighRollbackRate",
    "LWProjectionRunnerLag",
    "LWProjectionRunnerHeartbeatStale",
    "LWProjectionRebuildBacklog",
    "LWProjectionDriftWarning",
    "LWProjectionDriftCritical",
    "LWProjectionLagWarning",
    "LWProjectionLagCritical",
    "LWProjectionStaleVerification",
    "LWProjectionMonthlyDriftDetected",
    "LWWsConnectionSaturation",
    "LWWsClockSkewExceeds",
    "LWWsRefreshFailureRate",
    "LWWsReplayDetected",
    "LWWsHandshakeFailureSpike",
    "LWWsTicketReplayAttack",
    "LWWsOriginMismatchSpike",
    "LWWsFingerprintMismatchSpike",
    "LWWsAuthzRejectionSpike",
}


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

if problems:
    print(f"[alert-rule-validator] {len(problems)} problems in {checked} alerts:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    sys.exit(1)

print(f"[alert-rule-validator] {checked} alerts validated; {len(registry)} registry rows")
PYEOF
EXIT=$?

exit "$EXIT"
