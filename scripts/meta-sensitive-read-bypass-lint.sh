#!/usr/bin/env bash
# L1.K.15 meta-sensitive-read-bypass-lint.sh — S04 §12T.6
#
# Reads on enumerated sensitive paths (contracts/meta/meta-sensitive-read-paths.yml)
# MUST flow through contracts/meta/read_audit.go — bare SELECTs from outside
# the audit wrapper bypass the meta_read_audit row.
#
# Heuristic: forbid `SELECT * FROM actor_control_binding ... WHERE user_ref_id != ...`
# (non-owner queries) outside contracts/meta. Tighten in future cycles.
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
sensitive="$repo_root/contracts/meta/meta-sensitive-read-paths.yml"

if [[ ! -f "$sensitive" ]]; then
  echo "[meta-sensitive-read] WARN — meta-sensitive-read-paths.yml absent; skipping"
  exit 0
fi

violations=0

# Pull table names from the sensitive-paths YAML.
#
# ⚠ The extractor this replaces was `grep -oE 'table:[[:space:]]*[a-z_]+'`, and
# the YAML has never used a singular `table:` key — every entry is a `tables:`
# LIST. So it matched nothing, in every run since it was written, and the lint's
# real scope was the single hardcoded name below it. `NV-3`: an enumerated list
# is default-uncovered, and here the list was empty and nobody could tell,
# because the hardcoded fallback kept the gate green-and-useful-looking.
#
# Found while renaming the table for SEALED-BINDING (034/035): the rename had to
# touch the hardcoded name, which is what exposed that the hardcoded name was
# doing all the work.
#
# ── WHICH paths this lint is about, and why it is not all of them ───────────
#
# This gate's subject is stated in its own header: a NON-OWNER read
# (`WHERE user_ref_id != ...`). It is not the enforcement mechanism for
# `audit_query`, `admin_bulk_export`, `bulk_meta_query` or the two `pii_*` paths
# — those are tagged by the contracts/pii + contracts/meta SDKs at the call
# site, which is a different mechanism with a different failure mode.
#
# So the scan is the tables of the CROSS-USER paths, derived from the contract
# rather than hardcoded: a path whose `description` names the `user_ref_id !=`
# shape this gate exists to catch. Registering another cross-user path widens
# this scan by itself, which the previous hardcoded single name could never do.
#
# ⚠ NOT A SILENT CAP — both numbers are printed. Widening the scan to every
# table in the file was measured first: it reaches 12 tables and reports 30+
# pre-existing audit-count reads in drill/admin/bench binaries, which are that
# other mechanism's subject, not this one's. Tracked as
# D-AUDIT-READ-BYPASS-UNSCANNED rather than absorbed here.
all_tables=$(awk '
  /^[[:space:]]*tables:[[:space:]]*$/ { in_tables = 1; next }
  in_tables && /^[[:space:]]*-[[:space:]]*[a-z_"*]+/ {
    line = $0
    sub(/^[[:space:]]*-[[:space:]]*/, "", line); sub(/[[:space:]]*#.*$/, "", line)
    sub(/[[:space:]]*$/, "", line); gsub(/"/, "", line)
    if (line != "*") print line
    next
  }
  { in_tables = 0 }
' "$sensitive" 2>/dev/null | sort -u || true)

sensitive_tables=$(awk '
  /^[[:space:]]*-[[:space:]]*id:/ { cross = 0; in_tables = 0 }
  /^[[:space:]]*description:.*user_ref_id[[:space:]]*!=/ { cross = 1 }
  /^[[:space:]]*tables:[[:space:]]*$/ { in_tables = 1; next }
  in_tables && cross && /^[[:space:]]*-[[:space:]]*[a-z_]+/ {
    line = $0
    sub(/^[[:space:]]*-[[:space:]]*/, "", line); sub(/[[:space:]]*#.*$/, "", line)
    sub(/[[:space:]]*$/, "", line)
    print line
    next
  }
  /^[[:space:]]*[a-z_]+:/ && !/^[[:space:]]*-/ { in_tables = 0 }
' "$sensitive" 2>/dev/null | sort -u || true)

count_of() { echo "$1" | grep -c '[a-z]' || true; }
sensitive_table_count=$(count_of "$sensitive_tables")
all_table_count=$(count_of "$all_tables")

# An extraction that silently yields nothing is worse than no gate: the scan
# would pass trivially and report success. This is the `NV-3` failure the
# extractor above was rewritten to remove, so it is checked rather than trusted.
if [[ "$sensitive_table_count" -eq 0 ]]; then
  echo "[meta-sensitive-read] FAIL — extracted ZERO cross-user tables from $sensitive." >&2
  echo "  A scan over no tables passes trivially. Either the contract lost its" >&2
  echo "  cross-user path, or the extractor stopped matching it." >&2
  exit 1
fi
echo "[meta-sensitive-read] scanning $sensitive_table_count cross-user table(s): $(echo $sensitive_tables | tr '\n' ' ')"
echo "[meta-sensitive-read] NOT scanned here: $((all_table_count - sensitive_table_count)) table(s) on non-cross-user paths (SDK-tagged; D-AUDIT-READ-BYPASS-UNSCANNED)"

for table in $sensitive_tables; do
  hits=$(grep -rniE "SELECT.*FROM[[:space:]]+${table}" \
    --include='*.go' --include='*.rs' --include='*.ts' \
    "$repo_root/services" "$repo_root/contracts" "$repo_root/crates" 2>/dev/null \
    | grep -vE '/contracts/meta/' \
    | grep -vE '_test\.go|_test\.rs' \
    | grep -vE 'services/meta-worker/pkg/user_erased_writer/' || true)
  # ^ The GDPR erasure cascade (P2/071) reads actor_control_binding OWNER-scoped
  #   (WHERE user_ref_id = $1) to find which realities to scrub for the subject
  #   being erased — NOT a cross-user read (the != case the discipline targets).
  #   The erasure is audited end-to-end (each per-reality scrub writes a
  #   meta_write_audit row); a separate read-audit would be redundant. Tracked.
  if [[ -n "$hits" ]]; then
    echo "[meta-sensitive-read] FAIL — bare SELECT on sensitive table $table outside contracts/meta:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[meta-sensitive-read] FAIL — $violations bypass(es) (S04 §12T.6)"
  exit 1
fi
echo "[meta-sensitive-read] PASS"
exit 0
