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
# Exit 0 = clean; 1 = violations; 2 = the gate cannot see its corpus.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
sensitive="$repo_root/contracts/meta/meta-sensitive-read-paths.yml"

# The trees a bypass could live in. Measured 2026-08-11: 14333 .go/.rs/.ts files
# across the three. The floor is 2000 — well below the real number and far above
# zero, because a floor set AT the measurement turns the arms above it into
# floor tests (`BDR-82`).
SCAN_ROOTS=(services contracts crates)
MIN_SCANNED=2000

# ── EXTRACTION ───────────────────────────────────────────────────────────────
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
#
# Both extractors take the YAML path as an argument so `--selftest` can prove
# them on synthetic contracts instead of on whatever this repo happens to ship.

all_tables_of() {
  awk '
    /^[[:space:]]*tables:[[:space:]]*$/ { in_tables = 1; next }
    in_tables && /^[[:space:]]*-[[:space:]]*[a-z_"*]+/ {
      line = $0
      sub(/^[[:space:]]*-[[:space:]]*/, "", line); sub(/[[:space:]]*#.*$/, "", line)
      sub(/[[:space:]]*$/, "", line); gsub(/"/, "", line)
      if (line != "*") print line
      next
    }
    { in_tables = 0 }
  ' "$1" 2>/dev/null | sort -u || true
}

cross_user_tables_of() {
  awk '
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
  ' "$1" 2>/dev/null | sort -u || true
}

count_of() { echo "$1" | grep -c '[a-z]' || true; }

# Bare SELECTs on $1 under the roots given as $2.. — the exclusions are the
# audit wrapper itself, tests, and the GDPR erasure cascade.
bare_selects() {
  local table="$1"; shift
  grep -rniE "SELECT.*FROM[[:space:]]+${table}" \
    --include='*.go' --include='*.rs' --include='*.ts' \
    "$@" 2>/dev/null \
    | grep -vE '/contracts/meta/' \
    | grep -vE '_test\.go|_test\.rs' \
    | grep -vE 'services/meta-worker/pkg/user_erased_writer/' \
    | grep -vE 'services/commit-service/src/subject\.rs' \
    | grep -vE 'services/meta-worker/pkg/bridge/actor_control\.go' || true
  # ^ The GDPR erasure cascade (P2/071) reads actor_control_binding OWNER-scoped
  #   (WHERE user_ref_id = $1) to find which realities to scrub for the subject
  #   being erased — NOT a cross-user read (the != case the discipline targets).
  #   The erasure is audited end-to-end (each per-reality scrub writes a
  #   meta_write_audit row); a separate read-audit would be redundant. Tracked.
  #
  # ^ commit-service/src/subject.rs — SEALED-SUBJECT's resolver. Two reasons,
  #   and the second is a gap in the discipline rather than in the caller:
  #     1. It is OWNER-SCOPED — `WHERE reality_id = $1 AND user_ref_id = $2`,
  #        resolving the SUBMITTER'S OWN binding. Exactly the class the erasure
  #        exclusion above is written for; the yml's own description of this
  #        path is the `!=` case.
  #     2. There is NO RUST-SIDE SANCTIONED READER. The audit wrapper this lint
  #        points callers at is `contracts/meta`, which is Go, and the read
  #        audit writer is `sdks/go/piikms`. A Rust service therefore cannot
  #        comply by any route — the only compliant Rust read is one that does
  #        not happen. Recorded as PC-NO-RUST-READ-AUDIT rather than left as an
  #        exclusion that looks like a preference.
  #
  # ^ meta-worker/pkg/bridge/actor_control.go — genuinely CROSS-USER (keyed by
  #   actor, no user predicate: "who drives this actor"), and it now WRITES the
  #   meta_read_audit row — `ReadAuditor.RecordBindingRead`, tag
  #   `actor_binding_cross_user`, which had no SDK constant until 2026-08-14 and
  #   so was unreachable for this table. The exclusion is here because this lint
  #   tests WHERE a SELECT lives, not whether it audits; the discipline it
  #   enforces is satisfied, the grep cannot see it.
}

run_lint() {
  if [[ ! -f "$sensitive" ]]; then
    echo "[meta-sensitive-read] FAIL — $sensitive is absent." >&2
    echo "  This used to WARN and exit 0. That is the silent-nothing path: the" >&2
    echo "  contract IS the scan list, so losing it turned the gate off while it" >&2
    echo "  kept reporting success." >&2
    exit 2
  fi

  # REACH, part 1: every tree this gate claims to search must exist. A renamed
  # root makes `grep -r` find nothing, and `2>/dev/null … || true` swallows the
  # error — indistinguishable from a clean tree.
  local roots=() r scanned
  for r in "${SCAN_ROOTS[@]}"; do
    if [[ ! -d "$repo_root/$r" ]]; then
      echo "[meta-sensitive-read] FAIL — scan root '$r' does not exist." >&2
      echo "  A bypass living under it would be invisible, and this gate would" >&2
      echo "  still print PASS." >&2
      exit 2
    fi
    roots+=("$repo_root/$r")
  done

  # REACH, part 2: the roots exist and are non-empty of the languages we grep.
  scanned=$(find "${roots[@]}" \( -name '*.go' -o -name '*.rs' -o -name '*.ts' \) 2>/dev/null | wc -l)
  if [[ "$scanned" -lt "$MIN_SCANNED" ]]; then
    echo "[meta-sensitive-read] FAIL — only $scanned greppable file(s) under the scan roots (floor $MIN_SCANNED, measured 14333)." >&2
    echo "  The walk is not reaching the source tree; every table below would" >&2
    echo "  report clean." >&2
    exit 2
  fi

  local all_tables sensitive_tables sensitive_table_count all_table_count violations=0
  all_tables=$(all_tables_of "$sensitive")
  sensitive_tables=$(cross_user_tables_of "$sensitive")
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
  echo "[meta-sensitive-read] $scanned file(s) under $((${#roots[@]})) scan root(s)"
  echo "[meta-sensitive-read] NOT scanned here: $((all_table_count - sensitive_table_count)) table(s) on non-cross-user paths (SDK-tagged; D-AUDIT-READ-BYPASS-UNSCANNED)"

  local table hits
  for table in $sensitive_tables; do
    hits=$(bare_selects "$table" "${roots[@]}")
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
}

selftest() {
  local tmp fails=0 y out
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN
  y="$tmp/paths.yml"

  # A contract with BOTH kinds of path: one cross-user (this gate's subject) and
  # one that is sensitive for a different reason (the SDK's subject).
  cat > "$y" <<'YML'
version: 1
paths:
  - id: binding_cross_user
    description: "SELECT * FROM actor_control_binding WHERE user_ref_id != $caller"
    tables:
      - actor_control_binding  # a trailing comment
      - second_cross_table
    rationale: impersonation
  - id: admin_bulk_export
    description: "operator exports everything"
    tables:
      - cost_ledger
      - "*"
    rationale: bulk
YML

  # ARM 1 — only the CROSS-USER path's tables are scanned.
  out=$(cross_user_tables_of "$y" | tr '\n' ' ')
  if [[ "$out" != "actor_control_binding second_cross_table " ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — cross-user extraction gave '$out'"; fails=1
  fi

  # ARM 2 — the non-cross-user path is NOT swept in (that is the other mechanism).
  if cross_user_tables_of "$y" | grep -q cost_ledger; then
    echo "[meta-sensitive-read] SELFTEST FAIL — a non-cross-user table entered the scan"; fails=1
  fi

  # ARM 3 — the all-tables count sees both paths and drops the `*` wildcard.
  out=$(all_tables_of "$y" | tr '\n' ' ')
  if [[ "$out" != "actor_control_binding cost_ledger second_cross_table " ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — all-tables extraction gave '$out'"; fails=1
  fi

  # ARM 4 — REACH ON THE CONTRACT. A YAML the extractor cannot parse yields zero
  # tables, which is the case that used to pass trivially.
  echo "version: 1" > "$tmp/empty.yml"
  if [[ "$(count_of "$(cross_user_tables_of "$tmp/empty.yml")")" -ne 0 ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — an empty contract yielded tables"; fails=1
  fi

  # ── the grep half, on a synthetic tree ──────────────────────────────────────
  mkdir -p "$tmp/src/svc" "$tmp/src/contracts/meta"
  echo 'q := "SELECT id FROM actor_control_binding WHERE x"' > "$tmp/src/svc/leak.go"

  # ARM 5 — a bare SELECT outside the wrapper is caught.
  if [[ -z "$(bare_selects actor_control_binding "$tmp/src")" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — a bare SELECT on a sensitive table was not caught"; fails=1
  fi

  # ARM 6 — the audit wrapper itself is exempt (it IS the sanctioned reader).
  mv "$tmp/src/svc/leak.go" "$tmp/src/contracts/meta/read_audit.go"
  if [[ -n "$(bare_selects actor_control_binding "$tmp/src")" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — flagged the contracts/meta audit wrapper"; fails=1
  fi

  # ARM 7 — a test file is exempt, and a NON-test file with the same SQL is not.
  # Both directions, because a one-sided exemption test proves nothing about the
  # exemption (`NV-2`).
  mv "$tmp/src/contracts/meta/read_audit.go" "$tmp/src/svc/thing_test.go"
  if [[ -n "$(bare_selects actor_control_binding "$tmp/src")" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — flagged a _test.go file"; fails=1
  fi
  cp "$tmp/src/svc/thing_test.go" "$tmp/src/svc/thing.go"
  if [[ -z "$(bare_selects actor_control_binding "$tmp/src")" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — the SAME sql in a non-test file was not caught,"
    echo "  so the _test exemption is not what excused it"; fails=1
  fi

  # ARM 8 — an unrelated table is not swept in.
  if [[ -n "$(bare_selects some_other_table "$tmp/src")" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — matched a table the contract never named"; fails=1
  fi

  # ARM 9 — REACH ON THE SOURCE. An empty tree finds nothing, which is
  # byte-identical to a clean one; the floor in run_lint is what separates them,
  # so prove it is calibrated: live, and not already saturated.
  mkdir -p "$tmp/nothing"
  if [[ -n "$(bare_selects actor_control_binding "$tmp/nothing")" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — an empty tree produced hits"; fails=1
  fi
  local real
  real=$(find "$repo_root/services" "$repo_root/contracts" "$repo_root/crates" \
           \( -name '*.go' -o -name '*.rs' -o -name '*.ts' \) 2>/dev/null | wc -l)
  if [[ "$MIN_SCANNED" -le 0 || "$MIN_SCANNED" -ge "$real" ]]; then
    echo "[meta-sensitive-read] SELFTEST FAIL — floor $MIN_SCANNED is not between 0 and the real"
    echo "  corpus ($real); a floor at or above the measurement pre-empts every arm (BDR-82)"; fails=1
  fi

  if [[ "$fails" -ne 0 ]]; then
    exit 2
  fi
  echo "[meta-sensitive-read] SELFTEST PASS — 9 arm(s): extracts only cross-user tables (and drops"
  echo "  the wildcard), reads zero from an unparseable contract, catches a bare SELECT, exempts the"
  echo "  audit wrapper and _test files while still catching the SAME sql in a sibling, ignores"
  echo "  unnamed tables, and the reach floor is calibrated live-but-unsaturated against $real file(s)"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
