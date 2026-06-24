package events

import (
	"time"

	"github.com/google/uuid"
)

// canon.* events — RAID cycle 23, L5.A.
//
// Authoritative `canon.*` event types emitted by **glossary-service** via its
// own outbox (R06 §12F pattern). These events are then drained by Publisher
// (L2.D) into Redis Streams and FANNED OUT additionally to the
// `xreality.book.canon.updated` stream (cross-reality flag set on the
// envelope metadata, per Q-L2-4 naming + cycle-10 xreality fanout protocol)
// where meta-worker (sole consumer per I7) writes them through to per-reality
// `canon_projection` (L5.D).
//
// LOCKED decisions consumed:
//   * Q-L5A-1: glossary-service outbox migration is a SEPARATE sub-program
//     before L5 push activates. Foundation owns ONLY this contract +
//     glossary-outbox emission contract document (docs/governance/
//     glossary-service-outbox-contract.md) + a test fixture that exercises
//     the schema. **THIS FILE DOES NOT MODIFY services/glossary-service/.**
//   * Q-L5-3: `canon_projection` schema is SINGLE table with `canon_layer`
//     column. The events carry `canon_layer` payload field so the L5.D
//     projection writer (cycle 24+ meta-worker) sets the right value.
//   * Q-L1A-2: canon tables (`canon_entries`, `canonization_audit`,
//     `book_authorship`, `canon_change_log`) live in glossary-service's
//     glossary DB (NOT meta DB). These events describe MUTATIONS to those
//     tables; the per-reality `canon_projection` is a separate concern
//     (per-reality cache for `[WORLD_CANON]` prompt assembly hot path).
//
// Annotation format matches reality.go / npc.go / xreality.go — consumed
// by `tools/eventgen` to populate the registry + polyglot codegen.
//
// 4 event types (per L5.A.1):
//   - canon.entry.created    — new canon entry authored
//   - canon.entry.updated    — existing canon entry value/attribute changed
//   - canon.entry.promoted   — L2_seeded promoted to L1_axiom (gated; M4 §9.7.4)
//   - canon.entry.decanonized — canon entry retracted (Q-L5A-1 sub-program
//                              handles outbox-tombstone semantics)

// CanonLayer enumerates the two canonization layers per Q-L5-3 LOCKED.
// The per-reality `canon_projection.canon_layer` column carries one of these
// string values; the L5.I L1-conflict-detector and L5.E `[WORLD_CANON]`
// prompt builder both branch on this value.
//
// Layers (S09 §12Y.4 + M4 §9.7):
//   - L1_axiom  — author-locked, immutable, governs ALL realities
//   - L2_seeded — author canonical default, per-reality L3 events MAY override
type CanonLayer string

const (
	// CanonLayerL1Axiom — author-locked axiomatic canon. Cannot be overridden
	// by per-reality L3 events. L5.I runtime guardrail rejects conflicting
	// future L3 writes.
	CanonLayerL1Axiom CanonLayer = "L1_axiom"
	// CanonLayerL2Seeded — author canonical default. L3 per-reality events
	// MAY override (sets `canon_projection.overridden_by_l3_event_id`).
	CanonLayerL2Seeded CanonLayer = "L2_seeded"
)

// IsValid returns true if l is one of the two LOCKED layer values. Defense vs
// typo / future-version drift in producers.
func (l CanonLayer) IsValid() bool {
	return l == CanonLayerL1Axiom || l == CanonLayerL2Seeded
}

// @event       canon.entry.created
// @version     1
// @aggregate   canon
// @description A new canon entry was authored in glossary-service. Emitted
//              via glossary-service outbox (Q-L5A-1 separate sub-program);
//              fanned out via xreality.book.canon.updated to per-reality
//              canon_projection writers.
type CanonEntryCreatedV1 struct {
	CanonEntryID  uuid.UUID  `json:"canon_entry_id"`
	BookID        uuid.UUID  `json:"book_id"`
	AttributePath string     `json:"attribute_path"`
	Value         []byte     `json:"value"` // canonical JSON-encoded value (validator job to inspect shape)
	CanonLayer    CanonLayer `json:"canon_layer"`
	LockLevel     string     `json:"lock_level"`
	AuthorUserID  uuid.UUID  `json:"author_user_id"`
	CreatedAt     time.Time  `json:"created_at"`
}

// @event       canon.entry.updated
// @version     1
// @aggregate   canon
// @description Existing canon entry value/attribute changed in
//              glossary-service. Emitted via outbox; carries old_value for
//              audit + new_value for projection write. Old value is opaque to
//              the projection writer; downstream consumers may use it for
//              diff / change-history (L5.J).
type CanonEntryUpdatedV1 struct {
	CanonEntryID  uuid.UUID  `json:"canon_entry_id"`
	BookID        uuid.UUID  `json:"book_id"`
	AttributePath string     `json:"attribute_path"`
	OldValue      []byte     `json:"old_value"`
	NewValue      []byte     `json:"new_value"`
	CanonLayer    CanonLayer `json:"canon_layer"`
	EditorUserID  uuid.UUID  `json:"editor_user_id"`
	UpdatedAt     time.Time  `json:"updated_at"`
}

// @event       canon.entry.promoted
// @version     1
// @aggregate   canon
// @description Canon entry promoted from L2_seeded to L1_axiom (gated per
//              M4 §9.7.4 harder L2→L1 gate). NOT the same as
//              xreality.canon.promoted (cycle 10), which is the cross-reality
//              fan-out signal — THIS event records the authoring action
//              itself in glossary-service.
type CanonEntryPromotedV1 struct {
	CanonEntryID uuid.UUID  `json:"canon_entry_id"`
	BookID       uuid.UUID  `json:"book_id"`
	FromLayer    CanonLayer `json:"from_layer"`
	ToLayer      CanonLayer `json:"to_layer"`
	PromotedBy   uuid.UUID  `json:"promoted_by"`
	PromotedAt   time.Time  `json:"promoted_at"`
}

// @event       canon.entry.decanonized
// @version     1
// @aggregate   canon
// @description Canon entry retracted (no longer canonical). Q-L5A-1 sub-
//              program handles the outbox-tombstone semantics; foundation
//              ships the schema so per-reality canon_projection writers can
//              mark the row tombstoned in cycle 24+.
type CanonEntryDecanonizedV1 struct {
	CanonEntryID    uuid.UUID `json:"canon_entry_id"`
	BookID          uuid.UUID `json:"book_id"`
	Reason          string    `json:"reason"`
	DecanonizedBy   uuid.UUID `json:"decanonized_by"`
	DecanonizedAt   time.Time `json:"decanonized_at"`
}
