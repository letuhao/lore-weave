// Package main — eventgen codegen CLI (L2.G).
//
// eventgen reads `contracts/events/_registry.yaml` + the annotated Go structs
// in `contracts/events/*.go` and emits per-language type definitions used by
// runtime services + frontend.
//
// # CLI usage
//
//	eventgen --registry contracts/events/_registry.yaml \
//	         --events-dir contracts/events \
//	         --out-dir   contracts/events/generated \
//	         --target    all
//
// `--target` accepts `all | go | rust | ts | python`. Default is `all`. Empty
// target generates nothing (smoke-mode).
//
// # Codegen targets (Q-L4-1 LOCKED)
//
//   - go     — `<out>/registry_generated.go`  (Go dispatch table)
//   - rust   — `<out>/rust/<event_snake>.rs`  (Rust structs; world / travel)
//   - ts     — `<out>/ts/<event-kebab>.ts`    (TS interfaces; FE + WS envelope)
//   - python — `<out>/python/<event_snake>.py` (Pydantic-compatible TypedDict)
//
// Polyglot scope per Q-L4-1: Rust + Go + Python runtime types; TS only for
// events + WS envelope (no full runtime types). This MATCHES the eventgen
// scope — eventgen IS the event-types codegen path.
//
// # Q-L4-3 unification path → contractgen
//
// Per Q-L4-3 LOCKED, the polyglot codegen tool is `contractgen` — a SUPERSET
// of eventgen that also generates non-event contracts (API DTOs, capacity
// budgets, etc.). V1 ships eventgen with `--scope events` (the default).
// V2+ adds `--scope all` covering the wider contract surface. The CLI grammar
// here is forward-compatible: `--scope` already accepts `events` (default)
// and reserves `contracts` (errors out V1 — clean upgrade path).
//
// # Determinism
//
// Generated output MUST be byte-identical across re-runs (so `git diff` is
// meaningful + CI cache works). Achieved by:
//   - sorting events by name before emission
//   - sorting field lists by source-line position (which is determined by
//     the input file ordering — also stable)
//   - no embedded timestamps or hostnames in the generated code
//
// # CI gate: scripts/eventgen-validate.sh
//
// CI runs `eventgen` + `git diff --exit-code contracts/events/generated/`.
// Any drift = hand-edited generated file or stale generation = fail.
package main
