#!/usr/bin/env bash
# L1.K.1 meta-write-discipline-lint.sh — I8 / S04 §12T.6
#
# Forbids direct INSERT/UPDATE/DELETE on meta tables OUTSIDE contracts/meta/.
# Services MUST go through MetaWrite() so the same-TX audit invariant holds.
# Exit 0 = clean; 1 = violations; 2 = misuse.
#
# ── WHY THIS WAS REWRITTEN (2026-08-06) ─────────────────────────────────────
#
# It was correct and IT DID NOT RUN. The old shape was
#
#     for table in $meta_tables; do   grep -rniE "...${table}..." <whole tree>
#
# — one full-tree walk PER TABLE, 33 of them. Measured at 74s standalone on a
# warm cache and >900s sharing a machine with the other gates, which is why
# `gate-wiring-gate.py` carried it as `TOO_SLOW` and skipped it, tracked as
# `D-GATE-SLOW-META-WRITE-DISCIPLINE`. So the invariant *"no direct meta write"*
# was held by human discipline, and the only reason it still held is that nobody
# had crossed it.
#
# Now: ONE walk, with the table list as a single alternation, and the table a
# hit named recovered from the matched text afterwards. Same rules, same
# exclusions, same output — the cost model is what changed.
#
# The same-day sibling is `meta-sensitive-read-bypass-lint.sh`, whose extractor
# had matched nothing since the day it was written. Both were found by one PO
# question: *"is there anywhere a module that may not touch the DB reaches down
# to it, and how is that guarded?"* — a gate that is too slow to run and a gate
# that scans nothing fail in exactly the same way, and neither says so.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# ── self-test: the gate's own teeth, before it is trusted about the repo ─────
#
# Convention borrowed from the Python gates in this directory. It runs on
# synthetic input in a temp dir, so it says nothing about repo state — only
# that the matcher can still tell a violation from a legitimate line.
selftest() {
  local tmp bad=0
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  mkdir -p "$tmp/services/x"
  cat >"$tmp/services/x/a.go" <<'EOF'
_ = `INSERT INTO reality_registry (a) VALUES (1)`
_ = `UPDATE pii_kek SET x = 1`
_ = `DELETE FROM user_consent_ledger WHERE u = $1`
// INSERT INTO reality_registry -- a comment, must NOT count
_ = `SELECT * FROM reality_registry`
_ = `INSERT INTO reality_registry_shadow (a) VALUES (1)`
EOF
  local alt='reality_registry_shadow|user_consent_ledger|reality_registry|pii_kek'
  local got
  got=$(grep -rniE "(INSERT[[:space:]]+INTO[[:space:]]+(${alt})|UPDATE[[:space:]]+(${alt})|DELETE[[:space:]]+FROM[[:space:]]+(${alt}))[^a-z0-9_]" \
    --include='*.go' "$tmp" 2>/dev/null | grep -vE ':[[:space:]]*(//|--|#|\*|///)' || true)

  # three real writes, and NEITHER the comment NOR the SELECT NOR the
  # longer-named sibling table counted as `reality_registry`.
  local n; n=$(printf '%s\n' "$got" | grep -c '[a-z]' || true)
  [[ "$n" -eq 4 ]] || { echo "  selftest: expected 4 hits (3 writes + the _shadow write), got $n"; bad=1; }
  printf '%s\n' "$got" | grep -q 'a comment' && { echo "  selftest: a commented-out write was counted"; bad=1; }
  printf '%s\n' "$got" | grep -q 'SELECT \*'  && { echo "  selftest: a SELECT was counted as a write"; bad=1; }
  printf '%s\n' "$got" | grep -q 'reality_registry_shadow' || { echo "  selftest: the sibling table's write was MISSED"; bad=1; }

  if [[ "$bad" -ne 0 ]]; then
    echo "[meta-write-discipline] SELFTEST FAIL"
    return 1
  fi
  echo "[meta-write-discipline] SELFTEST PASS — flags INSERT/UPDATE/DELETE, ignores a comment and a SELECT, and does not confuse a table with its longer-named sibling"
  return 0
}

selftest || exit 2
[[ "${1:-}" == "--selftest" ]] && exit 0

# Authoritative table list — derived from migrations/meta/*.up.sql filenames.
#
# Exemptions (outbox TRANSPORT tables, not audited domain tables):
#   - meta_outbox (030): written by MetaWrite's own appender (sdks/go/metaoutbox)
#     INSIDE the write TX, and its publish-state is UPDATEd by the dedicated
#     meta-outbox-relay drain (services/meta-outbox-relay) — exactly as the
#     per-reality events_outbox is drained by the publisher. The relay's
#     UPDATE is the drain, not a domain write that must route through MetaWrite.
#     (events_outbox already escapes this lint by living in per_reality/, not meta/.)
#
# `drop_`-prefixed migrations are filtered: `035_drop_player_character_index`
# names a table that no longer EXISTS, so linting writes to it would be a rule
# with no possible subject. The drop itself is what keeps it gone
# (contracts/meta/actor_control_binding_test.go).
meta_tables=$(ls "$repo_root/migrations/meta/" 2>/dev/null \
  | grep -E '^[0-9]+_.*\.up\.sql$' \
  | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' \
  | grep -vE '^drop_' \
  | grep -vxE 'meta_outbox' || true)

table_count=$(printf '%s\n' "$meta_tables" | grep -c '[a-z]' || true)

# A scan over zero tables passes trivially and prints success — the exact shape
# `docs/standards/non-vacuity.md` NV-3 names, and the shape this file's sibling
# had shipped in for months. It used to `exit 0` here.
if [[ "$table_count" -eq 0 ]]; then
  echo "[meta-write-discipline] FAIL — discovered ZERO meta tables from migrations/meta/." >&2
  echo "  A scan over no tables cannot fail, so a clean result means nothing. Either the" >&2
  echo "  migration directory moved, or the filename pattern stopped matching." >&2
  exit 1
fi

scan_dirs=(
  "$repo_root/services"
  "$repo_root/crates"
  "$repo_root/frontend-game"
)

# Sanctioned direct meta-table writers (file-path-regex → table). Each is a
# NARROW exemption (path AND table must match): a different file writing this
# table, or these files writing a different table, still FAILs. Two sanctioned
# categories per S04 §12T.6 intent:
#   - LIVENESS: high-frequency heartbeat upserts that must NOT emit a
#     meta_write_audit row per write (events:[] by design).
#   - AUDIT-SELF-WRITE: writing an audit table IS the audit; it has no
#     MetaWrite path (MetaWrite governs DOMAIN writes, and for meta_write_audit
#     would be infinite-regress). The canon path's per-reality projection apply
#     (meta-worker pgwrite) writes its own meta_write_audit row directly.
declare -A sanctioned=(
  ["services/publisher/pkg/metahb/"]="publisher_heartbeats"
  ["services/world-service/src/embedding_queue/live/audit_writer.rs"]="service_to_service_audit"
  ["services/meta-worker/pkg/pgwrite/"]="meta_write_audit"
  # W1.5 Rust→Go bridge records its OWN cross-service-call audit row — writing
  # service_to_service_audit IS the audit (self-write, like audit_writer.rs above).
  ["services/meta-worker/pkg/bridge/"]="service_to_service_audit"
  # S13 capacity-override CLI logs the operator override into scaling_events —
  # the scaling-decision EVENT LOG; writing it IS the record (no domain MetaWrite).
  ["services/meta-worker/cmd/capacity-override/"]="scaling_events"
)

# ── ONE walk ────────────────────────────────────────────────────────────────
#
# Tables sorted LONGEST FIRST so the alternation prefers the longest match:
# with `a|a_b`, POSIX ERE alternation would report `a` for a write to `a_b` and
# the sanctioned-writer lookup would then be asked about the wrong table.
#
# The trailing `[^a-z0-9_]` is a boundary the per-table version did not have.
# Without it `UPDATE reality_registry_shadow` matches the table
# `reality_registry` — a false positive on a table that has its own row in the
# list anyway. Strictly more correct, and the self-test above is what holds it.
alt=$(printf '%s\n' "$meta_tables" | awk '{ print length, $0 }' | sort -rn | cut -d' ' -f2- | paste -sd'|' -)

# The two drill exclusions below cover the W1/S13 LIVE-TEST DRILL harnesses —
# standalone binaries that set up + tear down test realities by writing meta
# tables DIRECTLY on purpose (driving the raw DB: CAS races, freeze, relocation
# — not the audited domain path). They are functionally tests (like _test.go),
# just compiled as runnable bins so they can drive a live stack.
all_hits=$(grep -rniE "(INSERT[[:space:]]+INTO[[:space:]]+(${alt})|UPDATE[[:space:]]+(${alt})|DELETE[[:space:]]+FROM[[:space:]]+(${alt}))[^a-z0-9_]" \
  --include='*.go' --include='*.rs' --include='*.sql' --include='*.ts' \
  "${scan_dirs[@]}" 2>/dev/null \
  | grep -vE '/contracts/meta/' \
  | grep -vE '/crates/meta-rs/' \
  | grep -vE 'migrations/meta/' \
  | grep -vE '_test\.(go|rs|ts)' \
  | grep -vE '/cmd/(closure-drill|lifecycle-race|migrate-drill)/' \
  | grep -vE '/src/bin/(provision_drill|capacity_place|freeze_drill)\.rs' \
  | grep -vE ':[[:space:]]*(//|--|#|\*|///)' || true)

violations=0
if [[ -n "$all_hits" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    # Which table did THIS line name? Recovered from the matched text rather
    # than from the loop variable the old shape had.
    table=$(printf '%s\n' "$line" \
      | grep -oiE "(INSERT[[:space:]]+INTO[[:space:]]+(${alt})|UPDATE[[:space:]]+(${alt})|DELETE[[:space:]]+FROM[[:space:]]+(${alt}))" \
      | head -1 | awk '{ print tolower($NF) }')
    [[ -z "$table" ]] && continue

    # Sanctioned (path, table) pairs — both must match, as before.
    skip=0
    for path in "${!sanctioned[@]}"; do
      if [[ "${sanctioned[$path]}" == "$table" ]] && [[ "$line" == *"$path"* ]]; then
        skip=1
        break
      fi
    done
    [[ "$skip" -eq 1 ]] && continue

    if [[ "$violations" -eq 0 ]]; then
      echo "[meta-write-discipline] FAIL — direct write(s) on meta table(s) outside contracts/meta:"
    fi
    echo "  [$table] $line"
    violations=$((violations + 1))
  done <<< "$all_hits"
fi

if [[ $violations -gt 0 ]]; then
  echo "[meta-write-discipline] FAIL — $violations direct write(s) (I8 / S04 §12T.6)."
  echo "  Route the write through contracts/meta MetaWrite() so the data row, the"
  echo "  meta_write_audit row and the outbox event land in ONE transaction."
  exit 1
fi
echo "[meta-write-discipline] PASS — $table_count meta table(s) scanned in one walk"
exit 0
