#!/usr/bin/env bash
# L1.K.1 meta-write-discipline-lint.sh — I8 / S04 §12T.6
#
# Forbids direct INSERT/UPDATE/DELETE on meta tables OUTSIDE contracts/meta/.
# Services MUST go through MetaWrite() so the same-TX audit invariant holds.
# Exit 0 = clean; 1 = violations; 2 = misuse.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Authoritative table list — derived from migrations/meta/*.up.sql filenames.
#
# Exemptions (outbox TRANSPORT tables, not audited domain tables):
#   - meta_outbox (030): written by MetaWrite's own appender (sdks/go/metaoutbox)
#     INSIDE the write TX, and its publish-state is UPDATEd by the dedicated
#     meta-outbox-relay drain (services/meta-outbox-relay) — exactly as the
#     per-reality events_outbox is drained by the publisher. The relay's
#     UPDATE is the drain, not a domain write that must route through MetaWrite.
#     (events_outbox already escapes this lint by living in per_reality/, not meta/.)
meta_tables=$(ls "$repo_root/migrations/meta/" 2>/dev/null | grep -E '^[0-9]+_.*\.up\.sql$' | sed -E 's/^[0-9]+_(.*)\.up\.sql$/\1/' | grep -vxE 'meta_outbox' || true)

if [[ -z "$meta_tables" ]]; then
  echo "[meta-write-discipline] no meta tables discovered; nothing to lint"
  exit 0
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
)

for table in $meta_tables; do
  # Match INSERT INTO <table>, UPDATE <table>, DELETE FROM <table>
  # in Go/Rust/SQL/TS files OUTSIDE contracts/meta.
  hits=$(grep -rniE "(INSERT[[:space:]]+INTO[[:space:]]+${table}|UPDATE[[:space:]]+${table}|DELETE[[:space:]]+FROM[[:space:]]+${table})" \
    --include='*.go' --include='*.rs' --include='*.sql' --include='*.ts' \
    "${scan_dirs[@]}" 2>/dev/null \
    | grep -vE '/contracts/meta/' \
    | grep -vE '/crates/meta-rs/' \
    | grep -vE 'migrations/meta/' \
    | grep -vE '_test\.(go|rs|ts)' \
    | grep -vE ':[[:space:]]*(//|--|#|\*|///)' || true)
  # Drop sanctioned (path, table) writers for THIS table.
  for path in "${!sanctioned[@]}"; do
    if [[ "${sanctioned[$path]}" == "$table" && -n "$hits" ]]; then
      hits=$(printf '%s\n' "$hits" | grep -vF "$path" || true)
    fi
  done
  if [[ -n "$hits" ]]; then
    echo "[meta-write-discipline] FAIL — direct write on meta table $table outside contracts/meta:"
    echo "$hits" | sed 's/^/  /'
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[meta-write-discipline] FAIL — $violations table(s) with direct writes (I8 / S04 §12T.6)"
  exit 1
fi
echo "[meta-write-discipline] PASS"
exit 0
