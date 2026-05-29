// Package meta is the canonical Go library for accessing the `loreweave_meta`
// database. Every service that needs to read or write meta tables imports this
// package; direct SQL on meta tables outside this package is a CI lint error
// (I8 invariant — see L1.B layer plan §1).
//
// Cycle 2 (L1.B) ships the foundational artifacts:
//
//   - MetaWrite() / MetaWriteBatch() — canonical write + audit path (Q-L1B-3)
//   - AttemptStateTransition()       — CAS-based reality state machine
//   - transitions.yaml               — per-resource transition graph + validator
//   - events_allowlist.yaml          — which MetaWrite ops emit outbox events (Q-L1B-1)
//   - meta-sensitive-read-paths.yml  — which read paths trigger meta_read_audit (Q-L1B-2)
//
// Hot-path read accessors (cache, routing, entity_status) ship in later cycles
// alongside their dependent kernel infrastructure (Redis, etc.).
//
// # Runtime dependency note
//
// MetaWrite inserts into meta_write_audit in the same TX as the data write.
// The meta_write_audit + meta_read_audit tables ship in a later cycle (L1.A-3
// audit infrastructure). Until then, real production use of MetaWrite will
// fail on the audit insert; cycle 2 tests pass because the in-memory fake
// Tx accepts any SQL. This is intentional — services don't bind to meta in
// production until both cycles land.
//
// Parent layer plan:
//   docs/plans/2026-05-29-foundation-mega-task/L1B_meta_access_library.md
//
// LOCKED decisions consumed this cycle:
//   Q-L1A-1, Q-L1A-3, Q-L1B-1, Q-L1B-2, Q-L1B-3, Q-L1B-4
package meta
