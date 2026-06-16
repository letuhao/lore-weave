#!/usr/bin/env bash
# scripts/perf/bencher-gate.sh
#
# S7 deliverable F5 — the cross-language perf gate via self-hosted Bencher.
# Ingests the SAME `go test -bench` output as the benchstat gate (F2) into a
# self-hosted Bencher as a per-commit time-series and fails on a threshold alert
# (`--err` = --error-on-alert). Per spec §8 we START with t_test/percentage and
# graduate to change-point once a multi-commit series exists (D-S7-BENCHER-
# CHANGEPOINT) — there is no series yet, so this slice VALIDATES the path.
#
# Validation outcome is recorded honestly in
#   docs/specs/2026-06-13-S7-bencher-selfhost-decision.md
# PASS → Bencher becomes the gate; NEGATIVE → benchstat (F2) stays + a deferred
# row. "Validate" includes "validated as impractical".
#
# Verdict: bencher CLI absent OR self-host not booted → NOTRUN(setup); a real
# Bencher threshold alert → FAIL.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/bencher/docker-compose.yml"
API_PORT="${BENCHER_API_PORT:-61016}"
HOST="${BENCHER_HOST:-http://127.0.0.1:${API_PORT}}"
PROJECT="${BENCHER_PROJECT:-loreweave-foundation}"
TESTBED="${BENCHER_TESTBED:-ci-runner}"
BRANCH="${BENCHER_BRANCH:-main}"
PERF_DIR="tests/perf"

log()    { printf '[bencher] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

command -v bencher >/dev/null 2>&1 || notrun "bencher CLI not installed (curl -sSfL https://bencher.dev/download/install-cli.sh | sh)"
command -v docker  >/dev/null 2>&1 || notrun "docker not available to boot self-hosted Bencher"

# Boot self-host (idempotent) + wait for the version endpoint.
log "booting self-hosted Bencher (api :$API_PORT) ..."
docker compose -f "$COMPOSE" up -d >/dev/null 2>&1 || notrun "bencher compose up failed (image pull / daemon)"
up=0
for _ in $(seq 1 40); do
  if curl -fsS "$HOST/v0/server/version" >/dev/null 2>&1; then up=1; break; fi
  sleep 2
done
[ "$up" = 1 ] || notrun "Bencher API did not answer /v0/server/version (self-host boot unverified)"
log "Bencher API up: $(curl -fsS "$HOST/v0/server/version" 2>/dev/null)"

# A token is required. On a fresh self-host the first token comes from the
# signup→confirm flow (the API logs the confirm token when SMTP is unset). That
# bootstrap is environment-specific; require it via env rather than fragile log
# scraping in CI.
TOKEN="${BENCHER_API_TOKEN:-}"
[ -n "$TOKEN" ] || notrun "BENCHER_API_TOKEN unset — bootstrap a token (signup→confirm) and export it; see the F5 decision doc"

# Ensure the project exists (ignore 'already exists').
bencher project create --token "$TOKEN" --host "$HOST" --name "$PROJECT" --slug "$PROJECT" >/dev/null 2>&1 || true

log "bencher run (go_bench adapter, --err) ..."
if bencher run \
     --host "$HOST" --token "$TOKEN" --project "$PROJECT" \
     --branch "$BRANCH" --testbed "$TESTBED" \
     --adapter go_bench --err \
     "cd $PERF_DIR && go test -run='^\$' -bench=. -count=10 ./bench/..."; then
  log "PASS: Bencher ingested + no threshold alert"
else
  rc=$?
  # Bencher exits non-zero on a threshold alert (--err). Distinguish alert (FAIL)
  # from infra trouble (NOTRUN) is hard from rc alone; treat as FAIL since the
  # CLI ran — an operator inspects the Bencher report URL printed above.
  fail "bencher run exited $rc — threshold alert or run error (see report URL above)"
fi
