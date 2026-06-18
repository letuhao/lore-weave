// Package timeline is L5.J — the glossary entity change timeline contract
// (RAID cycle 27 DPS 3).
//
// # Why this package
//
// The `canon.change.recorded` event family (contracts/events/canon_change_history.go)
// describes the wire shape. This package ships the **query contract** + SDK
// types that author-UI consumers use to walk the timeline of a given
// `(book_id, attribute_path)` — distinct from the event source side which
// is producer-only.
//
// # APPEND-ONLY invariant
//
// The SDK exposes NO `Update` / `Delete` / `Amend` methods. The interface
// surface itself enforces append-only at compile-time.
//
// # LOCKED decisions consumed
//
//   - Q-L1A-2: canon SSOT (incl. change history) lives in glossary DB
//     conceptually; foundation ships the contract + migration proposal.
//     The glossary-service sub-program (Q-L5A-1) APPLIES the migration.
//   - Q-L5-3: canon_layer enum strings carried verbatim.
//
// # Cross-cycle wiring
//
//   - Producer: services/meta-worker/pkg/canon_history_writer/ (cycle 27)
//     emits canon.change.recorded events on every canon.entry.* +
//     admin.canon.override.compensating delivery.
//   - Consumer: author-UI in glossary-service (out of foundation scope).
//     Foundation owns the contract.
//
// # OpenAPI binding
//
// `contracts/api/glossary-service/canon_history.yaml` carries the RPC
// surface (HTTP/JSON V1 per Q-L5-4). The Go types in this package match
// the OpenAPI response shapes.
package timeline
