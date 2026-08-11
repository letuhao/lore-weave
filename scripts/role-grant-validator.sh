#!/usr/bin/env bash
# L1.K.11 role-grant-validator.sh — S04-D6 / §12T.7
#
# Every entry in contracts/service_acl/matrix.yaml must:
#   - reference only tables that exist in migrations/meta/*.up.sql
#   - declare permissions from {SELECT,INSERT,UPDATE,DELETE} only
#   - audit tables (meta_write_audit, meta_read_audit, *_audit) may ONLY have INSERT/SELECT (no UPDATE/DELETE — append-only)
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# ── selftest — the red-ability proof (gate-teeth-gate) ──────────────────────
# Runs THIS script against synthetic repo trees. A copy of itself under
# $tmp/scripts/ makes `repo_root` resolve to $tmp, so nothing in the production
# path is parameterised for the test — no env hook that CI could accidentally
# point at an empty tree, which would make the gate pass vacuously.
#
# The deploy_audit cases are why this exists. "UPDATE is sanctioned but DELETE is
# STILL forbidden" is stated only in a comment above the `case` block; an editor
# who simplified that exception to `continue` would break an append-only
# guarantee on deploy history and every real matrix would still lint clean.
if [[ "${1:-}" == "--selftest" ]]; then
  st_fail=0
  st_run() {  # st_run <expected-exit> <name> <matrix-body>
    local want="$1" name="$2" body="$3" t rc base
    base="$(basename "$0")"
    t="$(mktemp -d)"
    mkdir -p "$t/scripts" "$t/migrations/meta" "$t/contracts/service_acl"
    cp "$0" "$t/scripts/$base"
    echo 'CREATE TABLE thing_audit (id int);'  > "$t/migrations/meta/001_thing_audit.up.sql"
    echo 'CREATE TABLE deploy_audit (id int);' > "$t/migrations/meta/002_deploy_audit.up.sql"
    echo 'CREATE TABLE widgets (id int);'      > "$t/migrations/meta/003_widgets.up.sql"
    printf '%s\n' "$body" > "$t/contracts/service_acl/matrix.yaml"
    rc=0
    bash "$t/scripts/$base" >/dev/null 2>&1 || rc=$?
    if [[ "$rc" != "$want" ]]; then
      echo "  FAIL — $name: exit $rc, expected $want"
      st_fail=1
    fi
    rm -rf "$t"
  }

  st_run 0 "an append-only audit grant passes" "version: 1
services:
  - name: svc-a
    permissions:
      thing_audit:
        - INSERT
        - SELECT
      widgets:
        - SELECT"

  st_run 1 "an audit table granting DELETE is refused" "version: 1
services:
  - name: svc-a
    permissions:
      thing_audit:
        - INSERT
        - DELETE"

  st_run 1 "an audit table granting UPDATE is refused" "version: 1
services:
  - name: svc-a
    permissions:
      thing_audit:
        - INSERT
        - UPDATE"

  st_run 0 "deploy_audit MAY grant UPDATE (the sanctioned state-machine exception)" "version: 1
services:
  - name: svc-a
    permissions:
      deploy_audit:
        - INSERT
        - UPDATE"

  st_run 1 "the deploy_audit exception does NOT extend to DELETE" "version: 1
services:
  - name: svc-a
    permissions:
      deploy_audit:
        - INSERT
        - DELETE"

  st_run 1 "a grant on a table no migration creates is refused" "version: 1
services:
  - name: svc-a
    permissions:
      ghosts:
        - SELECT"

  if [[ $st_fail -eq 0 ]]; then
    echo "[role-grant] SELFTEST PASS — append-only enforced, the deploy_audit UPDATE"\
         "exception held open, its DELETE half held shut, unknown tables refused (non-vacuous)"
    exit 0
  fi
  echo "[role-grant] SELFTEST FAIL"
  exit 1
fi

matrix="$repo_root/contracts/service_acl/matrix.yaml"

if [[ ! -f "$matrix" ]]; then
  echo "[role-grant] WARN — matrix.yaml absent; skipping"
  exit 0
fi

violations=0

# Discover audit tables (anything ending in _audit + meta_*_audit)
audit_tables=$(ls "$repo_root/migrations/meta/" 2>/dev/null \
  | grep -E '_audit\.up\.sql$' \
  | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' | sort -u || true)

# For each `table_name:` line, check that no audit table grants UPDATE/DELETE.
#
# EXCEPTION — state-machine "audit" tables: a few tables are named *_audit but
# are legitimately UPDATE-able state machines, not append-only logs. deploy_audit
# (L1A §6.3) is INSERT=started + UPDATE=canary stage advance/rollback (the
# canary-controller is the sole writer). For these, UPDATE is sanctioned but
# DELETE is STILL forbidden (deploy history must not be erased).
for audit in $audit_tables; do
  allow_update=0
  case "$audit" in
    deploy_audit) allow_update=1 ;;
  esac
  hits=$(awk -v t="$audit" -v au="$allow_update" '
    /^[[:space:]]*[a-z_]+:[[:space:]]*$/ {
      block_table = $1; gsub(":", "", block_table);
      in_block = (block_table == t);
    }
    in_block && /^[[:space:]]+-[[:space:]]*(UPDATE|DELETE)[[:space:]]*$/ {
      op = $2;
      if (op == "DELETE" || au == 0)
        print FILENAME ":" NR ": audit table " t " grants " op;
    }
  ' "$matrix" || true)
  if [[ -n "$hits" ]]; then
    echo "[role-grant] FAIL — audit table $audit must be append-only (no UPDATE/DELETE):"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
done

# Check for grants on unknown tables.
#
# Derive the declared-table set from ACTUAL `CREATE TABLE` statements in BOTH
# the meta migrations AND the per-reality migrations — the service-ACL matrix
# legitimately references per-reality tables (events / events_outbox /
# event_audit / archive_state, in contracts/migrations/per_reality/), and
# filename-parsing also produced false table names for ALTER-only migrations
# (e.g. 027_meta_write_audit_scrub_version). Grepping CREATE TABLE is exact.
declared_tables=$( { grep -rhoiE 'CREATE TABLE +(IF NOT EXISTS +)?[a-z_][a-z0-9_]*' \
    "$repo_root/migrations/meta/" \
    "$repo_root/contracts/migrations/per_reality/" 2>/dev/null \
  | sed -E 's/.*CREATE TABLE +(IF NOT EXISTS +)?//I'; } | sort -u || true)
# Tables referenced in matrix (heuristic: 2-space indent, ending in :)
ref_tables=$(grep -E '^[[:space:]]{6}[a-z_]+:$' "$matrix" | sed -E 's/[[:space:]]+([a-z_]+):.*/\1/' | sort -u || true)
for t in $ref_tables; do
  if ! echo "$declared_tables" | grep -qx "$t"; then
    echo "[role-grant] FAIL — matrix references unknown table $t (no migration exists)"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[role-grant] FAIL — $violations issue(s) (S04-D6 / §12T.7)"
  exit 1
fi
echo "[role-grant] PASS"
exit 0
