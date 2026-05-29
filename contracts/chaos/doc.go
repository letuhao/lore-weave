// Package chaos is the cycle-22 L4.O Chaos SDK SKELETON.
//
// Q-L4-4 LOCKED — `contracts/chaos/` deployment is V1+30d per SR07 §12AJ.
// This cycle ships ONLY the SDK contracts (interfaces + types) + ONE
// example drill class + an audit-row constructor for the cycle-22-deferred
// `chaos_drills` meta table. The runtime chaos-engine service (L4.O.2)
// + experiments.yaml registry (L4.O.1) + scheduled drill execution land
// V1+30d.
//
// Production posture: hooks DEFAULT TO OFF. A real chaos run requires:
//   - explicit env-var or config flag enabling the hook (NoopHook is the
//     default for every service)
//   - allowlist of services that may participate (chaos-engine V1+30d will
//     check service identity via SVID before triggering)
//
// Why ship an SDK now: services that already exist need a stable contract
// to bind against so V1+30d chaos-engine rollout is non-disruptive. The
// pattern matches L4.D (prompt skeleton) + L4.L (ws skeleton) — Q-L6L-1
// style "interface + Noop default + LOCKED-decision-deferred-to-sub-program".
//
// The four primitives:
//   - Hook                  — instrumentation point on a code path
//                             (RPC handler, DB call, channel read).
//   - FailOnce / DelayOnce  — concrete Hook implementations.
//   - HookRegistry          — service-local store of (path_id → Hook); the
//                             default is empty (no chaos fires).
//   - DrillAuditEntry       — schema for the V1+30d `chaos_drills` table
//                             written via MetaWrite() at drill outcome.
package chaos
