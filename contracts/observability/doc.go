// Package observability — L4.H (RAID cycle 19) — formalizes the
// canonical schema, loader, and admission-control entry-points for the
// inventory.yaml file shipped in cycle 6.
//
// Scope (SR12 §12AO):
//
//   - inventory.yaml — the AUTHORITATIVE list of every `lw_*` metric +
//     log channel + trace span the platform emits. Cycle 6 shipped the
//     file; THIS cycle (19) formalizes its typed schema + loader +
//     admission API so non-shell consumers can validate at runtime.
//   - admission.go — `EmitMetric(name, labels, value)` admission control
//     façade. Rejects unregistered metric names (V1+30d hard-reject; V1
//     warn-and-drop per SR12 §12AO acceptance).
//   - inventory_loader.go — reads inventory.yaml + builds an in-memory
//     name→entry lookup. Strict mode (unknown YAML keys rejected) or
//     lax mode (forward-compat for non-admission consumers like the
//     observability-inventory-lint shell script).
//   - budget_breach_writer.go — writes an `observability_budget_breaches`
//     (meta) row on admission rejection. V1 warn-and-drop, V1+30d
//     hard-reject (SR12 §12AO).
//
// Companion lint: `scripts/observability-inventory-lint.sh` (L1.K.6,
// shipped cycle 7) continues to grep code for emitted `lw_*` symbols
// and cross-checks against this inventory. Cycle 19 does NOT replace
// the lint; the lint remains the build-time gate. This package is the
// RUNTIME gate for ad-hoc EmitMetric callers.
//
// Q-L4-1 parity: Rust mirror lives in `crates/dp-kernel/src/observability.rs`.
// Schema field names + enum wire strings are 1-for-1.
package observability
