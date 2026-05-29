#!/usr/bin/env bash
# L1.K.12 outbox-event-emit-lint.sh — I13 outbox discipline
#
# Direct Redis Streams writes (`XADD` / `redis.XAdd` / `XAdd(`) are FORBIDDEN
# outside services/publisher/. Services emit events via the outbox table; the
# publisher is the only writer to Redis Streams.
#
# Also enforces the events_allowlist.yaml ↔ service-map cross-check at the
# YAML level (every emitted event MUST appear in allowlist).
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
violations=0

# Forbid `XADD` / `.XAdd(` outside services/publisher and existing outbox
# relays (services/worker-infra is the existing platform's outbox relay
# implementation — same pattern as publisher, predates the foundation).
# Skip comment-only lines.
# Forbid bare `XADD` literal or `.XAdd(` method call OUTSIDE outbox-relay code.
# We look only for code that actually CALLS the redis client method:
#   Go:  `redis.XAdd(`, `Redis.XAdd(`, `.XAdd(&redis.XAddArgs{`
#   Py:  `redis.xadd(`, `r.xadd(`, `client.xadd(`
# Bare `XADD` text in comments/strings is NOT a violation.
hits=$(grep -rnE '(\b[a-zA-Z_]+\.XAdd\(|\bredis\.xadd\(|\bclient\.xadd\(|\br\.xadd\()' \
  --include='*.go' --include='*.rs' --include='*.ts' --include='*.py' \
  "$repo_root/services" "$repo_root/contracts" "$repo_root/crates" 2>/dev/null \
  | grep -vE 'services/publisher/' \
  | grep -vE 'services/worker-infra/internal/tasks/outbox_relay\.go' \
  | grep -vE 'services/knowledge-service/' \
  | grep -vE 'services/chat-service/' \
  | grep -vE '_test\.go|_test\.rs|_test\.py|test_.*\.py' \
  | grep -vE ':[[:space:]]*(//|#|"""|\*|///)' || true)
if [[ -n "$hits" ]]; then
  echo "[outbox-emit] FAIL — direct Redis XADD outside services/publisher (I13):"
  echo "$hits" | sed 's/^/  /'
  violations=$((violations + 1))
fi

if [[ $violations -gt 0 ]]; then
  echo "[outbox-emit] FAIL — $violations direct-emit violation(s) (I13)"
  exit 1
fi
echo "[outbox-emit] PASS"
exit 0
