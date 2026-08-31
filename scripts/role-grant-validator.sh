#!/usr/bin/env bash
# L1.K.11 role-grant-validator.sh — S04-D6 / §12T.7
#
# Every entry in contracts/service_acl/matrix.yaml must:
#   - reference only tables that exist in the migrations
#   - declare permissions from {SELECT,INSERT,UPDATE,DELETE} only
#   - audit tables (meta_write_audit, meta_read_audit, *_audit) may ONLY have
#     INSERT/SELECT (no UPDATE/DELETE — append-only)
#
# Exit 0 = clean · 1 = violations · 2 = misuse / nothing to check / self-test failure.
#
# ── GT8 · what this gate lacked ──────────────────────────────────────────────
# **The permission closed-set rule — the second of its three advertised rules —
# was not implemented.** The header has said "declare permissions from
# {SELECT,INSERT,UPDATE,DELETE} only" since it was written; the file contained
# the audit-table check and the unknown-table check and nothing else, so a typo'd
# `- SELCT` or an invented `- TRUNCATE` sailed through. That is the THIRD gate in
# this batch whose header advertises a rule it does not have, after
# `outbox-event-emit` and `template-fixture-validator`. Built; measured clean
# (the matrix uses only INSERT/SELECT/UPDATE — no DELETE anywhere).
#
# **A missing matrix was a silent PASS** (`WARN … exit 0`) — the fourth gate on
# this board with that line, after `transitions-validation` (`GTD-10`),
# `observability-inventory` (`GTD-14`) and `prompt-assembly` (`GTD-22`). Now 2.
#
# **No reach floor**, and this gate has three independent walks that can each go
# quiet alone: the audit-table discovery (`ls migrations/meta | grep _audit`),
# the declared-table set (`grep CREATE TABLE`) and the matrix's own referenced
# tables (an indentation-sensitive grep). Measured 2026-08-12: 9 · 55 · 45. Any
# of them hitting zero used to mean "nothing to complain about".
#
# **The `deploy_audit` UPDATE exception had no shrink arm.** It is sanctioned
# because deploy_audit is a state machine (INSERT=started, UPDATE=canary stage
# advance), not an append-only log — and if it ever stops granting UPDATE, the
# exception is excusing nothing while still standing ready to.

set -euo pipefail

SELF="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"

VALID_PERMS="SELECT INSERT UPDATE DELETE"

# Audit tables that are legitimately UPDATE-able state machines rather than
# append-only logs. DELETE stays forbidden for them regardless — deploy history
# must not be erased. Each row must be a real audit table that actually grants
# UPDATE; the shrink arm below says so.
UPDATE_OK_AUDIT=("deploy_audit")

# run_lint <tree_root>
run_lint() {
    local root="$1"
    local matrix="$root/contracts/service_acl/matrix.yaml"
    local violations=0

    if [[ ! -f "$matrix" ]]; then
        echo "[role-grant] ERROR — matrix.yaml is missing at $matrix." >&2
        echo "  A missing ACL matrix is not an empty one; it is a rule with no subject." >&2
        return 2
    fi

    # ── the three walks, each counted (GT-F3).
    local audit_tables declared_tables ref_tables
    audit_tables=$(ls "$root/migrations/meta/" 2>/dev/null \
        | grep -E '_audit\.up\.sql$' \
        | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' | sort -u || true)
    declared_tables=$( { grep -rhoiE 'CREATE TABLE +(IF NOT EXISTS +)?[a-z_][a-z0-9_]*' \
            "$root/migrations/meta/" \
            "$root/contracts/migrations/per_reality/" 2>/dev/null \
        | sed -E 's/.*CREATE TABLE +(IF NOT EXISTS +)?//I'; } | sort -u || true)
    ref_tables=$(grep -E '^[[:space:]]{6}[a-z_]+:$' "$matrix" \
        | sed -E 's/[[:space:]]+([a-z_]+):.*/\1/' | sort -u || true)

    local n_audit n_declared n_ref
    n_audit=$(printf '%s' "$audit_tables" | grep -c . || true)
    n_declared=$(printf '%s' "$declared_tables" | grep -c . || true)
    n_ref=$(printf '%s' "$ref_tables" | grep -c . || true)

    if [[ "$n_audit" -eq 0 || "$n_declared" -eq 0 || "$n_ref" -eq 0 ]]; then
        echo "[role-grant] ERROR — a walk reached NOTHING, so its silence means nothing:" >&2
        echo "    audit tables=$n_audit · declared tables=$n_declared · matrix refs=$n_ref" >&2
        echo "  Comparing an empty set against anything is agreement about nothing (BDR-82)." >&2
        return 2
    fi

    # ── RULE: audit tables are append-only.
    local audit allow_update hits u
    for audit in $audit_tables; do
        allow_update=0
        for u in "${UPDATE_OK_AUDIT[@]}"; do
            [[ "$audit" == "$u" ]] && allow_update=1
        done
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

    # ── SHRINK ARM (GT-F5) on the UPDATE exception. Two deaths: the row names a
    # table that is not an audit table at all, or one that no longer grants
    # UPDATE — in which case it excuses nothing and waits to excuse the next
    # thing that appears under that name.
    for u in "${UPDATE_OK_AUDIT[@]}"; do
        if ! printf '%s\n' "$audit_tables" | grep -qx "$u"; then
            echo "[role-grant] FAIL — UPDATE_OK_AUDIT names '$u', which is not an audit table here."
            violations=$((violations + 1))
            continue
        fi
        if ! awk -v t="$u" '
            /^[[:space:]]*[a-z_]+:[[:space:]]*$/ { b=$1; gsub(":","",b); inb=(b==t) }
            inb && /^[[:space:]]+-[[:space:]]*UPDATE[[:space:]]*$/ { found=1 }
            END { exit found ? 0 : 1 }' "$matrix"; then
            echo "[role-grant] FAIL — UPDATE_OK_AUDIT names '$u', which grants no UPDATE in the matrix."
            echo "  The exception excuses nothing today, and would excuse it again unasked."
            violations=$((violations + 1))
        fi
    done

    # ── RULE: grants on unknown tables.
    local t
    for t in $ref_tables; do
        if ! printf '%s\n' "$declared_tables" | grep -qx "$t"; then
            echo "[role-grant] FAIL — matrix references unknown table $t (no migration exists)"
            violations=$((violations + 1))
        fi
    done

    # ── RULE: permissions come from the closed set. Advertised in the header
    # since this gate was written; never implemented until now.
    local perms bad_perm p ok
    # EXACTLY eight spaces — that is the permission level. `[[:space:]]+` also
    # matched the ten-space `allowed_callers:` lists and reported `publisher` as
    # an invalid permission on the real matrix, which is a rule mis-scoped into
    # crying wolf. Measured: list items sit at 2, 8 and 10 spaces; only the 74 at
    # depth 8 are grants (INSERT/SELECT/UPDATE). A lowercase typo at depth 8 is
    # still caught, which is the point of not narrowing to [A-Z] instead.
    perms=$(grep -oE '^ {8}- [A-Za-z_]+$' "$matrix" \
        | sed 's/^ *- //' | sort -u || true)
    local n_perms
    n_perms=$(printf '%s' "$perms" | grep -c . || true)
    if [[ "$n_perms" -eq 0 ]]; then
        echo "[role-grant] ERROR — 0 permission tokens parsed from the matrix; the closed-set" >&2
        echo "  rule would pass over nothing." >&2
        return 2
    fi
    for p in $perms; do
        ok=0
        for bad_perm in $VALID_PERMS; do
            [[ "$p" == "$bad_perm" ]] && ok=1
        done
        if [[ "$ok" -eq 0 ]]; then
            echo "[role-grant] FAIL — permission '$p' is not in {${VALID_PERMS// /,}}"
            violations=$((violations + 1))
        fi
    done

    if [[ $violations -gt 0 ]]; then
        echo "[role-grant] FAIL — $violations issue(s) (S04-D6 / §12T.7)"
        return 1
    fi
    echo "[role-grant] PASS — ${n_ref} matrix table(s) against ${n_declared} declared," \
         "${n_audit} audit table(s) append-only, ${n_perms} distinct permission(s) all valid"
    return 0
}

# ── SELF-TEST ────────────────────────────────────────────────────────────────
MATRIX_FIXTURE='services:
  svc-a:
    tables:
      thing:
        - SELECT
        - INSERT
      thing_audit:
        - INSERT
        - SELECT
      deploy_audit:
        - SELECT
        - UPDATE
    rpc:
      MetaWrite:
        allowed_callers:
          - publisher
          - world-service
'

seed_tree() {
    local d="$1"
    mkdir -p "$d/contracts/service_acl" "$d/migrations/meta" \
             "$d/contracts/migrations/per_reality"
    printf '%s' "$MATRIX_FIXTURE" > "$d/contracts/service_acl/matrix.yaml"
    printf 'CREATE TABLE thing (id UUID);\n'        > "$d/migrations/meta/001_thing.up.sql"
    printf 'CREATE TABLE thing_audit (id UUID);\n'  > "$d/migrations/meta/002_thing_audit.up.sql"
    printf 'CREATE TABLE deploy_audit (id UUID);\n' > "$d/migrations/meta/003_deploy_audit.up.sql"
}

selftest() {
    local failures=0

    probe() {
        local name="$1" want="$2" setup="$3"
        local d got
        d="$(mktemp -d)"
        seed_tree "$d"
        "$setup" "$d"
        set +e
        ( run_lint "$d" ) >/dev/null 2>&1
        got=$?
        set -e
        rm -rf "$d"
        if [[ "$got" == "$want" ]]; then
            echo "  ok   $name: rc=$got"
        else
            echo "  FAIL $name: rc=$got (want $want)"
            failures=$((failures + 1))
        fi
    }

    M='contracts/service_acl/matrix.yaml'
    s_none()        { :; }
    s_audit_update(){ sed -i 's/      thing_audit:\n/&/' "$1/$M"
                      python3 - "$1/$M" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("      thing_audit:\n        - INSERT\n",
              "      thing_audit:\n        - UPDATE\n        - INSERT\n")
open(p, "w", encoding="utf-8", newline="\n").write(s)
PY
                    }
    s_audit_delete(){ python3 - "$1/$M" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("      deploy_audit:\n        - SELECT\n",
              "      deploy_audit:\n        - DELETE\n        - SELECT\n")
open(p, "w", encoding="utf-8", newline="\n").write(s)
PY
                    }
    s_deploy_noupd(){ python3 - "$1/$M" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("      deploy_audit:\n        - SELECT\n        - UPDATE\n",
              "      deploy_audit:\n        - SELECT\n")
open(p, "w", encoding="utf-8", newline="\n").write(s)
PY
                    }
    s_unknown_tbl() { rm -f "$1/migrations/meta/001_thing.up.sql"; }
    s_bad_perm()    { python3 - "$1/$M" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("        - SELECT\n        - INSERT\n", "        - SELECT\n        - TRUNCATE\n", 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
PY
                    }
    s_no_matrix()   { rm -f "$1/$M"; }
    # Remove ONLY deploy_audit, leaving thing_audit behind. Removing every audit
    # migration empties the discovery walk and trips the reach floor instead —
    # the arm would pass on the floor's verdict, certifying the wrong rule.
    # Isolating shrink-arm death #1 (the row names a table that is not an audit
    # table) takes care: deleting deploy_audit outright makes death #2 fire too
    # (it then grants no UPDATE), and deleting its migration makes the
    # unknown-table rule fire. RENAMING the migration file is the one edit that
    # leaves the table declared and still granting UPDATE while removing it from
    # the `*_audit.up.sql` discovery walk — so only death #1 can speak.
    s_no_audit()    { mv "$1/migrations/meta/003_deploy_audit.up.sql" \
                         "$1/migrations/meta/003_deploy_state.up.sql"; }
    s_no_migs()     { rm -rf "$1/migrations" "$1/contracts/migrations"; }
    # every table key keeps its 6-space indent, but the 8-space grant lists go —
    # the tables are still referenced, so only the permission floor can speak
    s_no_perms()    { python3 - "$1/$M" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = re.sub(r"^        - [A-Z]+$\n", "", s, flags=re.M)
open(p, "w", encoding="utf-8", newline="\n").write(s)
PY
                    }
    s_no_refs()     { python3 - "$1/$M" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
# re-indent the table names so the 6-space grep stops matching them
s = re.sub(r"^      ([a-z_]+):$", r"    \1:", s, flags=re.M)
open(p, "w", encoding="utf-8", newline="\n").write(s)
PY
                    }

    echo "role-grant-validator --self-test"

    probe "a valid matrix passes" 0 s_none
    probe "an audit table granting UPDATE fails" 1 s_audit_update
    probe "an audit table granting DELETE fails even when UPDATE is sanctioned" 1 s_audit_delete
    probe "a matrix table with no migration fails" 1 s_unknown_tbl
    probe "a permission outside the closed set fails" 1 s_bad_perm
    # the false-positive twin: the fixture carries a 10-space allowed_callers
    # list, which the first draft of the closed-set rule reported as an invalid
    # permission on the REAL matrix (`publisher`). A clean tree must stay clean.
    probe "...but a 10-space allowed_callers list is not a permission list" 0 s_none

    # the shrink arm
    probe "an UPDATE exception whose table grants no UPDATE fails" 1 s_deploy_noupd
    probe "an UPDATE exception naming a non-audit table fails" 1 s_no_audit

    # floors
    probe "a MISSING matrix is misuse, not a skip" 2 s_no_matrix
    probe "zero declared tables is misuse, not agreement" 2 s_no_migs
    probe "zero matrix references is misuse, not a clean run" 2 s_no_refs
    probe "zero permission tokens is misuse, not a clean run" 2 s_no_perms

    if [[ $failures -gt 0 ]]; then
        echo "role-grant-validator --self-test: $failures rule(s) did not behave"
        return 2
    fi
    echo "role-grant-validator --self-test: every rule bites, and none cries wolf"
    return 0
}

case "${1:-}" in
    --self-test|--selftest) selftest ;;
    "")
        selftest || exit 2
        echo
        run_lint "$REPO_ROOT"
        ;;
    *)
        echo "usage: $0 [--self-test]" >&2
        exit 2
        ;;
esac
