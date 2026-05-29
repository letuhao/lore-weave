# Runbook — meta-worker lag

**Scope:** the L2.L meta-worker; sole consumer of `xreality.*` Redis
Streams (I7 invariant).

**SLO thresholds:**

| Threshold | Action |
|---|---|
| `lw_meta_worker_lag_seconds > 2s` | WARN — Slack `#data-platform` |
| `lw_meta_worker_lag_seconds > 10s` | PAGE — primary on-call SRE |
| `lw_meta_worker_lag_seconds > 60s` | DEGRADED — page secondary |

Lag is `now() - LastConsumedAt`. Latency budget reflects the 2s P99
acceptance criteria in `docs/plans/.../L2_event_sourcing.md` §L2.L.

## Triage steps

1. **Check that meta-worker is the ONLY xreality consumer.** Run:
   ```sh
   redis-cli XINFO CONSUMERS xreality.canon.promoted lw-meta-worker
   ```
   Only `meta-worker-<podname>` consumers should appear. If another
   service has registered against `xreality.*`, file a security incident
   (I7 violated) and revoke its SVID grant in `contracts/service_acl/matrix.yaml`.
2. **Check pending entries list (PEL):**
   ```sh
   redis-cli XPENDING xreality.canon.promoted lw-meta-worker
   ```
   Large PEL → meta-worker is consuming but not ACKing. Investigate
   handler errors via `lw_meta_worker_dispatch_total{outcome=handler_error}`.
3. **Check for ALLOWLIST gaps.** `lw_meta_worker_dispatch_total{outcome=no_handler}`
   tells you the publisher is emitting xreality events the dispatcher
   has no handler for. Add the handler to `services/meta-worker/pkg/dispatch/dispatch.go`
   `NewWithSkeletons` (V1) or the cycle 12+ real-projection wiring.
4. **Restart loop.** `kubectl rollout restart deploy/meta-worker`. Redis
   Streams re-delivers PEL entries when a new consumer joins the group.

## Adding a new xreality.* event

1. Add the event entry to `contracts/events/_registry.yaml` with
   `cross_reality: true`.
2. Add the struct to `contracts/events/xreality.go` with `@event` /
   `@version` / `@aggregate` / `@description` annotations.
3. Add validator schema to `contracts/events/validators_go/validator.go`
   `BuildSeedRegistry`.
4. Add handler to `services/meta-worker/pkg/dispatch/dispatch.go`
   `NewWithSkeletons` (V1 — sink) OR the cycle 12+ real projection
   writer.
5. Update ACL matrix if the handler needs new meta-side tables.
6. Re-run `tests/integration/xreality_propagation_test.go`.
