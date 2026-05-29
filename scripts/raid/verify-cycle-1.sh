#!/usr/bin/env bash
# verify-cycle-1.sh — L1.E Meta HA Infrastructure
# Generated from scripts/raid/verify-cycle-template.sh for RAID cycle 1.
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Cycle 1 ships pure IaC + ops infrastructure: Terraform skeletons,
# Patroni config, Postgres conf, WAL ship script, PITR tooling, runbooks,
# chaos drill, and a Go integration test that runs against the
# docker-compose.meta-ha.yml stack (Q-L1B-5).
#
# Per Q-L1C-1: V1 = docker-compose; prod Terraform validate ships V1+30d.
# Local CI without terraform CLI runs structural validation only. The
# integration test (tests/integration/meta_failover_test.go) auto-skips
# when the meta-ha stack isn't running so this gate stays green in
# environments without docker.

set -euo pipefail

CYCLE=1
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FAILED=0

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE${2:+,$2}}" >> "$AUDIT_LOG"
}

step() { echo "[verify-cycle-$CYCLE] === $* ==="; }
fail() { echo "[verify-cycle-$CYCLE] FAIL: $*" >&2; FAILED=1; }
ok()   { echo "[verify-cycle-$CYCLE] ok:   $*"; }

cd "$REPO_ROOT"

step "1/8 — required artifacts present (L1.E.1..L1.E.12 + Q-L1B-5 compose)"
required=(
  "infra/terraform/meta-postgres/primary.tf"           # L1.E.1
  "infra/terraform/meta-postgres/sync_replica.tf"      # L1.E.2
  "infra/terraform/meta-postgres/async_replica.tf"     # L1.E.3
  "infra/patroni/patroni.yml"                          # L1.E.4
  "infra/etcd/etcd-cluster.tf"                         # L1.E.5
  "infra/postgres/postgresql.conf"                     # L1.E.6
  "infra/wal-archive/lw-wal-ship.sh"                   # L1.E.7
  "infra/wal-archive/README.md"                        # L1.E.7 doc
  "infra/pitr-tooling/lw-pitr-restore.sh"              # L1.E.8
  "infra/pitr-tooling/README.md"                       # L1.E.8 doc
  "runbooks/meta/failover.md"                          # L1.E.9
  "runbooks/meta/pitr_restore.md"                      # L1.E.10
  "chaos/drills/meta_failover.yaml"                    # L1.E.11
  "tests/integration/meta_failover_test.go"            # L1.E.12
  "infra/docker-compose.meta-ha.yml"                   # Q-L1B-5
)
for f in "${required[@]}"; do
  if [ -f "$f" ]; then ok "  $f"; else fail "missing: $f"; fi
done

step "2/8 — durability invariants in postgresql.conf"
if grep -qE '^synchronous_commit\s*=\s*on' infra/postgres/postgresql.conf; then
  ok "synchronous_commit = on"
else
  fail "infra/postgres/postgresql.conf missing 'synchronous_commit = on'"
fi
if grep -qE "synchronous_standby_names\s*=\s*'ANY 1 \(sync_replica_a\)'" infra/postgres/postgresql.conf; then
  ok "synchronous_standby_names = 'ANY 1 (sync_replica_a)'"
else
  fail "infra/postgres/postgresql.conf missing sync_standby_names invariant"
fi
if grep -qE '^archive_mode\s*=\s*on' infra/postgres/postgresql.conf && \
   grep -qE '^archive_timeout\s*=\s*60' infra/postgres/postgresql.conf; then
  ok "archive_mode=on, archive_timeout=60 (60s RPO bound)"
else
  fail "infra/postgres/postgresql.conf missing archive_mode/archive_timeout invariants"
fi

step "3/8 — Patroni config invariants"
if grep -qE 'synchronous_mode_strict:\s*true' infra/patroni/patroni.yml; then
  ok "synchronous_mode_strict: true"
else
  fail "infra/patroni/patroni.yml missing synchronous_mode_strict: true"
fi
if grep -q 'etcd3:' infra/patroni/patroni.yml; then
  ok "etcd3 DCS configured (Q-L1E-2: self-hosted etcd)"
else
  fail "infra/patroni/patroni.yml missing etcd3 DCS block (Q-L1E-2)"
fi
if grep -q "synchronous_standby_names: 'ANY 1 (sync_replica_a)'" infra/patroni/patroni.yml; then
  ok "Patroni bootstrap synchronous_standby_names matches postgresql.conf"
else
  fail "Patroni synchronous_standby_names mismatches postgresql.conf"
fi

step "4/8 — shell script discipline (set -euo pipefail, no hardcoded secrets)"
for s in infra/wal-archive/lw-wal-ship.sh infra/pitr-tooling/lw-pitr-restore.sh; do
  if grep -q 'set -euo pipefail' "$s"; then
    ok "$s has 'set -euo pipefail'"
  else
    fail "$s missing 'set -euo pipefail'"
  fi
  # required-secret env vars must use :? (fail-fast if unset) per CLAUDE.md
  if grep -qE '\$\{WAL_ARCHIVE_(ACCESS|SECRET)_KEY:\?' "$s"; then
    ok "$s requires WAL_ARCHIVE_*_KEY env (no hardcoded secrets)"
  else
    fail "$s does not enforce required-env contract for WAL_ARCHIVE_*_KEY"
  fi
done

step "5/8 — docker-compose.meta-ha.yml syntactic validity"
if command -v docker >/dev/null 2>&1; then
  if docker compose -f infra/docker-compose.meta-ha.yml config -q 2>/dev/null; then
    ok "docker compose config -q passed"
  else
    fail "docker compose config -q on infra/docker-compose.meta-ha.yml failed"
  fi
else
  echo "[verify-cycle-$CYCLE] note: docker CLI absent — skipping compose-config validation"
fi

step "6/8 — Q-L1B-5 stack composition (primary + sync + async + etcd + minio)"
required_services=(etcd minio primary sync_replica_a async_replica_0)
for svc in "${required_services[@]}"; do
  if grep -qE "^  ${svc}:" infra/docker-compose.meta-ha.yml; then
    ok "compose service: $svc"
  else
    fail "compose service missing: $svc"
  fi
done

step "7/8 — Go integration test syntactic correctness"
# tests/integration is NOT a Go module yet — foundation-wide `go.mod` ships
# with cycle 2 (L1.A-1 + L1.B meta library). For cycle 1 we validate syntax
# only via `gofmt -e`, deferring full `go build -tags=integration` to cycle 2.
if command -v go >/dev/null 2>&1; then
  if gofmt_out=$(gofmt -e -l tests/integration/meta_failover_test.go 2>&1); then
    if [ -z "$gofmt_out" ]; then
      ok "gofmt -e clean on tests/integration/meta_failover_test.go"
    else
      fail "gofmt -e found formatting/syntax issues: $gofmt_out"
    fi
  else
    fail "gofmt -e failed: $gofmt_out"
  fi
else
  echo "[verify-cycle-$CYCLE] note: go CLI absent — skipping gofmt"
fi

step "8/8 — Terraform syntactic structure (terraform fmt -check if available)"
if command -v terraform >/dev/null 2>&1; then
  if terraform -chdir=infra/terraform/meta-postgres fmt -check -recursive 2>&1; then
    ok "terraform fmt -check clean on infra/terraform/meta-postgres"
  else
    fail "terraform fmt -check failed; run 'terraform fmt' to auto-format"
  fi
else
  echo "[verify-cycle-$CYCLE] note: terraform CLI absent — full prod validate deferred per Q-L1C-1 (V1+30d)"
  # Structural fallback: every .tf file must have a `terraform {` block + required_version
  for tf in infra/terraform/meta-postgres/*.tf infra/etcd/*.tf; do
    if grep -q 'terraform {' "$tf" && grep -q 'required_version' "$tf"; then
      ok "$tf has terraform{} block + required_version"
    else
      fail "$tf missing terraform{} or required_version (structural check)"
    fi
  done
fi

audit "verify_cycle_complete" "\"failed\":$FAILED"

if [ "$FAILED" -ne 0 ]; then
  echo "[verify-cycle-$CYCLE] FAIL: one or more checks failed"
  exit 1
fi
echo "[verify-cycle-$CYCLE] PASS"
exit 0
