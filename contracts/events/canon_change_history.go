package events

import (
	"time"

	"github.com/google/uuid"
)

// canon.change.* — RAID cycle 27 L5.J (per-attribute change history).
//
// # Why this event family
//
// L5.J ships the **change-timeline contract** for author-UI consumption.
// Each canon attribute mutation appends ONE `canon.change.recorded`
// event to an APPEND-ONLY history stream, joined to the per-reality
// propagation status from cycle 24 canon_writer + cycle 27 L5.H
// force-propagate compensating events.
//
// # APPEND-ONLY invariant
//
// History rows MUST NEVER be edited or deleted. The contract enforces
// this in three layers:
//
//   1. **Wire-level** — there is NO `canon.change.amended` or
//      `canon.change.deleted` event type. The schema doesn't model
//      retroactive edits.
//   2. **Storage-level** — the migration
//      `contracts/migrations/glossary/0001_canon_change_history.up.sql`
//      ships a CHECK trigger + `REVOKE UPDATE, DELETE`.
//   3. **Application-level** — `services/meta-worker/pkg/canon_history_writer/`
//      uses INSERT-ONLY semantics; no UPDATE / DELETE codepaths.
//
// Why three layers: defense-in-depth. Loss of any one of (CHECK trigger,
// REVOKE privilege, application code) STILL preserves the invariant.
//
// # LOCKED decisions consumed
//
//   - Q-L1A-2: canon SSOT (incl. change history) lives in glossary DB
//     conceptually; foundation ships the contract + the migration
//     proposal under `contracts/migrations/glossary/`. The glossary-service
//     sub-program (Q-L5A-1) APPLIES the migration.
//   - Q-L1A-3: full audit V1 (every change event has a corresponding
//     meta_write_audit row).
//   - Q-L5-3: `canon_layer` enum strings carried verbatim.

// CanonChangeKind enumerates the kinds of changes recorded in the history
// timeline. Distinct from canon.entry.* event_types (those are the
// CAUSE; this is the EFFECT recorded for author-UI consumption).
type CanonChangeKind string

const (
	// CanonChangeKindAuthored — author created/updated/promoted/decanonized.
	CanonChangeKindAuthored CanonChangeKind = "authored"
	// CanonChangeKindForcePropagate — L5.H force-propagate compensating
	// event landed (per-reality side effect of admin override).
	CanonChangeKindForcePropagate CanonChangeKind = "force_propagate"
	// CanonChangeKindPropagationCompleted — cycle 24 canon_writer landed
	// the projection write across N realities.
	CanonChangeKindPropagationCompleted CanonChangeKind = "propagation_completed"
)

// IsValid returns true if k is one of the LOCKED kinds.
func (k CanonChangeKind) IsValid() bool {
	switch k {
	case CanonChangeKindAuthored, CanonChangeKindForcePropagate, CanonChangeKindPropagationCompleted:
		return true
	}
	return false
}

// @event       canon.change.recorded
// @version     1
// @aggregate   canon
// @description APPEND-ONLY per-attribute change history entry. Emitted
//              after every canon.entry.* event has been propagated, OR
//              after every admin.canon.override.compensating event has
//              landed. Source of truth for author-UI change timeline.
//              NEVER edited / deleted — see canon_change_history.go header
//              for 3-layer APPEND-ONLY enforcement.
type CanonChangeRecordedV1 struct {
	ChangeID      uuid.UUID       `json:"change_id"`
	CanonEntryID  uuid.UUID       `json:"canon_entry_id"`
	BookID        uuid.UUID       `json:"book_id"`
	AttributePath string          `json:"attribute_path"`
	// RealityID — Nil when the change is book-wide (e.g. authored event
	// before per-reality propagation); populated when the change is
	// per-reality (e.g. force-propagate compensating event).
	RealityID  uuid.UUID       `json:"reality_id,omitempty"`
	Kind       CanonChangeKind `json:"kind"`
	OldValue   []byte          `json:"old_value,omitempty"`
	NewValue   []byte          `json:"new_value"`
	CanonLayer CanonLayer      `json:"canon_layer"`
	// SourceEventID is the originating event_id (canon.entry.* or
	// admin.canon.override.compensating) that produced this change.
	SourceEventID   uuid.UUID `json:"source_event_id"`
	SourceEventType string    `json:"source_event_type"`
	RecordedAt      time.Time `json:"recorded_at"`
}
