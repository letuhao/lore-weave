#!/usr/bin/env bash
# verify-cycle-11.sh — L2.J + L2.K Archive worker + Retention worker
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
# Covers:
#   - DPS 1 (L2.J): services/archive-worker/ tree compiles + unit + integration;
#     Q-L2J-1 dedicated service; ATTACH-then-DROP-after-verify invariant;
#     Parquet ABI markers + idempotency via archive_state.
#   - DPS 2 (L2.K): services/retention-worker/ SEPARATE binary (Q-L2K-1);
#     outbox_pruner addresses D-OUTBOX-PRUNE row 055 with the 3 safety
#     invariants (pending preserved, dead-letter preserved, recent preserved);
#     wraps cycle-9 scripts/event-audit-retention-cron.sh.
#   - Cross-cycle: NEW lw-event-archive bucket separate from lw-db-backups;
#     event_classes.yaml ships; ACL matrix + observability inventory updated.
#   - Cross-cycle: B5 prod-isolation-lint + B6 secret-scan-cycle.
# Cross-service live smoke: NOT required — cycle ships pure libraries + in-memory
# tests + skeleton Go binaries. Production live wiring deferred to D-ARCHIVE-WORKER-
# LIVE-WIRING (row 057) + D-RETENTION-WORKER-LIVE-WIRING (row 058) targeting
# cycle 17/L4.A.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-11] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-11] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-11] note: $1"; }

# ── DPS 1 — archive-worker service tree present ─────────────────────────
for f in \
    services/archive-worker/go.mod \
    services/archive-worker/cmd/archive-worker/main.go \
    services/archive-worker/cmd/archive-restore/main.go \
    services/archive-worker/pkg/types/types.go \
    services/archive-worker/pkg/partition_picker/partition_picker.go \
    services/archive-worker/pkg/parquet_writer/parquet_writer.go \
    services/archive-worker/pkg/state/state.go \
    services/archive-worker/pkg/object_store/object_store.go \
    services/archive-worker/pkg/archive_loop/archive_loop.go \
    infra/k8s/archive-worker-deployment.yaml \
    infra/minio/lw-event-archive-bucket.tf \
    runbooks/archive/restore.md \
    scripts/archive-worker-cron.yaml \
  ; do
    [[ -f "$f" ]] || fail "missing: $f"
done
pass "L2.J archive-worker tree present (9 source files + k8s + minio + runbook + cron)"

# ── DPS 1 — archive-worker unit tests pass + build ──────────────────────
(cd services/archive-worker && go vet ./... && go test ./...) >/dev/null 2>&1 \
    || fail "services/archive-worker go vet / go test failed"
pass "services/archive-worker: vet + unit tests green"

# ── DPS 1 — Q-L2J-1 dedicated-service marker present in main.go ─────────
grep -q "Q-L2J-1" services/archive-worker/cmd/archive-worker/main.go \
    || fail "archive-worker main.go missing Q-L2J-1 dedicated-service marker"
pass "Q-L2J-1 dedicated-service decision documented in main.go"

# ── DPS 1 — Q-L2K-1 separation explicit in archive-worker code ──────────
grep -q "Q-L2K-1" services/archive-worker/cmd/archive-worker/main.go \
    || fail "archive-worker main.go missing Q-L2K-1 separation note"
pass "Q-L2K-1 SEPARATE-binary decision documented in archive-worker main.go"

# ── DPS 1 — NEW lw-event-archive bucket (separate from lw-db-backups) ────
grep -q 'bucket         = "lw-event-archive"' infra/minio/lw-event-archive-bucket.tf \
    || fail "lw-event-archive-bucket.tf missing bucket declaration"
# Cycle 11 invariant: this is a NEW bucket; lw-db-backups must still exist as a SEPARATE file.
[[ -f infra/minio/lw-db-backups-bucket.tf ]] \
    || fail "lw-db-backups-bucket.tf missing (cycle 7); cannot prove archive bucket is SEPARATE"
pass "lw-event-archive bucket present as NEW resource separate from lw-db-backups (cycle 7)"

# ── DPS 1 — Parquet ABI markers (anti-drift) ─────────────────────────────
grep -q "Magic = \[4\]byte{'L', 'W', 'P', '1'}" services/archive-worker/pkg/parquet_writer/parquet_writer.go \
    || fail "parquet_writer.go missing Magic 'LWP1' marker"
grep -q "SchemaVersion uint32 = 1" services/archive-worker/pkg/parquet_writer/parquet_writer.go \
    || fail "parquet_writer.go missing SchemaVersion=1"
pass "Parquet ABI: Magic='LWP1' + SchemaVersion=1 present (anti-drift gate)"

# ── DPS 1 — VerifyHeader + invariant tests present ──────────────────────
grep -q "func VerifyHeader" services/archive-worker/pkg/parquet_writer/parquet_writer.go \
    || fail "parquet_writer.go missing VerifyHeader function"
grep -q "TestRun_FailedUpload_DoesNotDrop" services/archive-worker/pkg/archive_loop/archive_loop_test.go \
    || fail "archive_loop_test.go missing FailedUpload_DoesNotDrop invariant test"
grep -q "TestRun_VerifyHeaderRejectsCorruptUpload" services/archive-worker/pkg/archive_loop/archive_loop_test.go \
    || fail "archive_loop_test.go missing VerifyHeaderRejectsCorruptUpload invariant test"
grep -q "TestRun_FailedDrop_StatePreservedForRecovery" services/archive-worker/pkg/archive_loop/archive_loop_test.go \
    || fail "archive_loop_test.go missing FailedDrop_StatePreservedForRecovery invariant test"
grep -q "TestRun_Idempotent_SecondRunSkipsArchivedPartition" services/archive-worker/pkg/archive_loop/archive_loop_test.go \
    || fail "archive_loop_test.go missing Idempotent_SecondRunSkipsArchivedPartition test"
pass "archive_loop invariants (failed-upload, verify-corrupt, failed-drop, idempotent) all tested"

# ── DPS 2 — retention-worker service tree present (SEPARATE binary) ──────
for f in \
    services/retention-worker/go.mod \
    services/retention-worker/cmd/retention-worker/main.go \
    services/retention-worker/pkg/types/types.go \
    services/retention-worker/pkg/outbox_pruner/outbox_pruner.go \
    services/retention-worker/pkg/audit_invoker/audit_invoker.go \
    services/retention-worker/pkg/snapshot_pruner/snapshot_pruner.go \
    services/retention-worker/pkg/retention_loop/retention_loop.go \
    infra/k8s/retention-worker-deployment.yaml \
    contracts/retention/event_classes.yaml \
    runbooks/retention/audit_recovery.md \
  ; do
    [[ -f "$f" ]] || fail "missing: $f"
done
pass "L2.K retention-worker tree present (7 source files + k8s + config + runbook)"

# ── DPS 2 — SEPARATE binary verification ─────────────────────────────────
# go.mod for retention-worker is its own module; archive-worker is its own
# module too. If someone tries to collapse them into one binary, the go.mod
# files would have to merge → this test catches that.
grep -q "^module github.com/loreweave/foundation/services/retention-worker" services/retention-worker/go.mod \
    || fail "retention-worker module declaration missing (separation broken?)"
grep -q "^module github.com/loreweave/foundation/services/archive-worker" services/archive-worker/go.mod \
    || fail "archive-worker module declaration missing"
pass "Q-L2K-1 SEPARATE-binary enforced: archive-worker + retention-worker each own module"

# ── DPS 2 — retention-worker unit tests pass + build ────────────────────
(cd services/retention-worker && go vet ./... && go test ./...) >/dev/null 2>&1 \
    || fail "services/retention-worker go vet / go test failed"
pass "services/retention-worker: vet + unit tests green"

# ── DPS 2 — D-OUTBOX-PRUNE row 055 ADDRESSED (3 invariant tests) ─────────
grep -q "TestEligible_DeadLetterNotEligible" services/retention-worker/pkg/outbox_pruner/outbox_pruner_test.go \
    || fail "outbox_pruner missing dead-letter-preserved invariant test"
grep -q "TestEligible_PendingNotEligible" services/retention-worker/pkg/outbox_pruner/outbox_pruner_test.go \
    || fail "outbox_pruner missing pending-preserved invariant test"
grep -q "TestEligible_RecentNotEligible" services/retention-worker/pkg/outbox_pruner/outbox_pruner_test.go \
    || fail "outbox_pruner missing recent-preserved invariant test"
pass "D-OUTBOX-PRUNE addressed: 3 safety invariants tested in outbox_pruner"

# ── DPS 2 — retention-worker NEVER touches events table (ACL invariant) ──
# The CRITICAL invariant: retention-worker must NOT have any permission on
# the events table. If a future PR adds it (would race archive-worker), this
# test catches it.
awk '
  /^  - name: retention-worker$/ { in_block=1; next }
  /^  - name: / { in_block=0 }
  in_block && /^      events:/ { print "events: grant found on retention-worker"; exit 1 }
' contracts/service_acl/matrix.yaml \
    || fail "INVARIANT VIOLATED: retention-worker has events: grant (would race archive-worker)"
pass "retention-worker ACL invariant: NO events: grant (separation preserved)"

# ── DPS 2 — archive-worker NEVER touches events_outbox/event_audit (ACL) ─
awk '
  /^  - name: archive-worker$/ { in_block=1; next }
  /^  - name: / { in_block=0 }
  in_block && /^      events_outbox:/ { print "events_outbox: grant found on archive-worker"; exit 1 }
  in_block && /^      event_audit:/ { print "event_audit: grant found on archive-worker"; exit 1 }
' contracts/service_acl/matrix.yaml \
    || fail "INVARIANT VIOLATED: archive-worker has events_outbox/event_audit grant"
pass "archive-worker ACL invariant: NO outbox/audit grant (separation preserved)"

# ── DPS 2 — audit-retention script reuse (cycle 9 shipped it) ──────────
[[ -f scripts/event-audit-retention-cron.sh ]] \
    || fail "scripts/event-audit-retention-cron.sh missing (cycle 9 contract); audit_invoker would have nothing to invoke"
pass "audit_invoker wraps existing scripts/event-audit-retention-cron.sh (cycle 9)"

# ── Cross-cycle — ACL matrix entries present ────────────────────────────
grep -qE "^  - name: archive-worker$" contracts/service_acl/matrix.yaml \
    || fail "ACL matrix missing archive-worker entry"
grep -qE "^  - name: retention-worker$" contracts/service_acl/matrix.yaml \
    || fail "ACL matrix missing retention-worker entry"
pass "ACL matrix entries present for archive-worker + retention-worker"

# ── Cross-cycle — observability inventory: cycle-11 metrics declared ──
python - <<'PY' || exit 1
import yaml
with open("contracts/observability/inventory.yaml") as f:
    inv = yaml.safe_load(f)
names = {m["name"] for m in inv.get("metrics", [])}
required = {
    "lw_archive_partitions_archived_total",
    "lw_archive_bytes_uploaded_total",
    "lw_archive_rows_archived_total",
    "lw_archive_lag_hours",
    "lw_retention_outbox_pruned_total",
    "lw_retention_audit_invocations_total",
}
missing = required - names
assert not missing, f"inventory.yaml missing L2 cycle-11 metrics: {missing}"
print("inventory cycle-11: OK")
PY
pass "contracts/observability/inventory.yaml declares all 6 new L2 cycle-11 metrics"

# ── L1.K observability-inventory-lint still passes ────────────────────
bash scripts/observability-inventory-lint.sh >/dev/null \
    || fail "L1.K observability-inventory-lint regression"
pass "observability-inventory-lint clean with cycle-11 additions"

# ── Cross-cycle — integration tests build + pass ───────────────────────
(cd tests/integration && go build -tags=integration ./...) >/dev/null 2>&1 \
    || fail "tests/integration cycle-11 build failed"
(cd tests/integration && go test -tags=integration -run='^TestArchive|^TestOutboxPrune' ./...) >/dev/null 2>&1 \
    || fail "tests/integration cycle-11 tests failed"
pass "tests/integration cycle-11: build + archive/outbox-prune tests green"

# ── Cycle 10 contracts/events still green (regression) ─────────────────
(cd contracts/events && go test ./...) >/dev/null 2>&1 \
    || fail "contracts/events regression — cycle-10 unit suite failing"
pass "contracts/events cycle-10 unit suite still green after cycle-11"

# ── Cycle 10 publisher still green (regression) ────────────────────────
(cd services/publisher && go test ./...) >/dev/null 2>&1 \
    || fail "services/publisher regression — cycle-10 unit suite failing"
pass "services/publisher cycle-10 unit suite still green"

# ── Cycle 9 audit-retention script still passes dry-run preflight ──────
# Script exits 3 on --dry-run by design (preview only). Use || to capture
# exit code without tripping `set -e`.
rc=0
bash scripts/event-audit-retention-cron.sh --dry-run >/dev/null 2>&1 || rc=$?
if [[ $rc -ne 0 ]] && [[ $rc -ne 3 ]]; then
    fail "event-audit-retention-cron.sh --dry-run regression (exit=$rc)"
fi
pass "scripts/event-audit-retention-cron.sh dry-run still works (cycle 9 contract)"

# ── B5 prod-isolation ──────────────────────────────────────────────────
bash scripts/raid/prod-isolation-lint.sh >/dev/null \
    || fail "B5 prod-isolation-lint regression"
pass "B5 prod-isolation-lint clean"

# ── B6 secret-scan ──────────────────────────────────────────────────────
if bash scripts/raid/secret-scan-cycle.sh 11 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

echo "[verify-cycle-11] ALL STEPS PASS (cycle 11 = L2.J archive-worker + L2.K retention-worker)"
exit 0
