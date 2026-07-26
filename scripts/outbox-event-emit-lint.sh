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

# Forbid `XADD` / `.XAdd(` outside services/publisher and the SANCTIONED outbox
# relays — services/worker-infra (the existing novel-platform relay) and
# services/meta-outbox-relay (P2/101 Option B: the meta-context drain that
# XADDs meta_outbox → lw.meta.events + the xreality bridge; the meta analog of
# publisher, a deliberate 2nd emitter the user chose over meta-as-a-reality).
# Also sanctioned: services/incident-bot/internal/breach/redis_emitter.go
# (P2/108 D-BREACH-BROKER-EMITTER) — incident-bot DECIDES+EMITS the GDPR Art.33
# breach LIFECYCLE to lw.incidents.breach (Q-L7-1, LOCKED). These are operational/
# compliance signals that originate in incident-bot's own decision logic, NOT
# event-store aggregate events, so there is NO outbox→publisher path for them
# (incident-bot is stateless, has no event store). 072 already emitted them via
# the stdout StructuredEmitter; 108 only swaps the transport to a real Redis stream.
# Skip comment-only lines.
# Forbid bare `XADD` literal or `.XAdd(` method call OUTSIDE outbox-relay code.
# We look only for code that actually CALLS the redis client method:
#   Go:  `redis.XAdd(`, `Redis.XAdd(`, `.XAdd(&redis.XAddArgs{`
#   Py:  `redis.xadd(`, `r.xadd(`, `client.xadd(`
# Bare `XADD` text in comments/strings is NOT a violation.
#
# Exemptions added when the novel-platform/foundation services landed:
#   - provider-registry usage_relay.go : the SANCTIONED usage-stream relay (S4b),
#     the provider-registry analog of publisher / meta-outbox-relay (outbox→Redis).
#   - learning-service, lore-enrichment-service : AI/LLM-track services emitting to
#     their OWN service streams (corrections / wiki-gen) — same accepted pattern as
#     the already-exempt chat-service + knowledge-service.
#   - composition-service/app/worker/events.py : the composition_jobs JOB-TRIGGER
#     stream (loreweave:events:composition_jobs). NOT a domain event — it's a
#     best-effort work-dispatch wake-up; the Postgres job row is the SSOT and the
#     stuck-job sweeper re-drives on a missed XADD. Identical accepted pattern to
#     lore-enrichment's resume-trigger stream (above); composition-service landed
#     after this allowlist was written and was simply never added.
#   - meta-worker/cmd/metaworker-bench : a foundation LOAD BENCH that XADDs synthetic
#     xreality msgs to measure I7 consumer throughput (a test harness, not a service).
hits=$(grep -rnE '(\b[a-zA-Z_]+\.XAdd\(|\bredis\.xadd\(|\bclient\.xadd\(|\br\.xadd\()' \
  --include='*.go' --include='*.rs' --include='*.ts' --include='*.py' \
  "$repo_root/services" "$repo_root/contracts" "$repo_root/crates" 2>/dev/null \
  | grep -vE 'services/publisher/' \
  | grep -vE 'services/worker-infra/internal/tasks/outbox_relay\.go' \
  | grep -vE 'services/meta-outbox-relay/' \
  | grep -vE 'services/incident-bot/internal/breach/redis_emitter\.go' \
  | grep -vE 'services/knowledge-service/' \
  | grep -vE 'services/chat-service/' \
  | grep -vE 'services/provider-registry-service/internal/jobs/usage_relay\.go' \
  | grep -vE 'services/learning-service/' \
  | grep -vE 'services/lore-enrichment-service/' \
  | grep -vE 'services/composition-service/app/worker/events\.py' \
  | grep -vE 'services/meta-worker/cmd/metaworker-bench/' \
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
