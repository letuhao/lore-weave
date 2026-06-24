package events

import (
	"time"

	"github.com/google/uuid"
)

// admin.canon.override.* — RAID cycle 27, L5.H (force-propagate compensating
// event mechanism, M4-D3).
//
// # Why a NEW event family
//
// L5.H ships the **force-propagate** flow: an admin / author may push a
// canon edit through to per-reality `canon_projection` even when the
// reality has L3 history that would normally be shielded by R13-L2
// admin-override discipline. Each force-propagate is a 3-gate operation:
//
//   1. **Opt-in** at request time (the AdminCanonOverrideRequestedV1
//      emission BY ITSELF is the explicit opt-in).
//   2. **Per-reality owner consent** — collected per-reality with a 24h
//      timeout (Q-L5H-1 LOCKED). On ACK → AdminCanonOverrideConsentedV1.
//      On VETO → AdminCanonOverrideVetoedV1 (reality SKIPPED). On
//      no-response after 24h → DEFAULT-TO-CONSENT (Q-L5H-1) and the
//      consent collector emits an AdminCanonOverrideConsentedV1 with
//      `default_consent=true` for forensic clarity.
//   3. **R13 audit** — every emitted event is audit-distinguishable from
//      the regular canon.entry.updated (own audit prefix: see runbook).
//
// The compensating L3 event (AdminCanonOverrideCompensatingV1) is the
// per-reality side-effect that actually fixes the projection state for
// realities that consented (default or explicit). It is distinct from a
// normal `canon.entry.updated` because consumers (audit, change-history,
// L5.J timeline) MUST classify it as `force_propagate` for postmortem
// reconstruction.
//
// # LOCKED decisions consumed
//
//   - **Q-L5H-1**: 24h consent timeout; default-to-consent on no-response.
//     Carried as struct fields `consent_deadline_at` and `default_consent`.
//   - **Q-L5-3**: canon_layer enum unchanged (`L1_axiom` | `L2_seeded`).
//   - **Q-L1A-2**: glossary SSOT untouched; this family describes
//     ADMIN-AUTHORED edits propagated to the per-reality cache layer only.
//   - **Q-L1A-3**: full audit V1 — every event in this family appears in
//     the meta_write_audit table (no sampling).
//
// 4 event types (per L5.H.4 + foundation breakdown):
//   - admin.canon.override.requested     — admin opt-in starts the flow
//   - admin.canon.override.consented     — reality owner ACK (or default-to-consent timeout)
//   - admin.canon.override.vetoed        — reality owner refused; reality SKIPPED
//   - admin.canon.override.compensating  — per-reality compensating L3 event applied

// AdminCanonOverrideReason is a typed enum classifying the force-propagate
// rationale. Distinguishes (a) routine author edit that wants to reach all
// realities NOW (skip-cooldown) from (b) governance override required to
// fix a bad canon state from (c) emergency safety rollback.
//
// SRE forensic + L5.J change-timeline both branch on this value.
type AdminCanonOverrideReason string

const (
	// AdminOverrideReasonAuthorPush — author wants the edit on every
	// reality immediately; normal canon update flow would lag behind
	// per-reality projection runners.
	AdminOverrideReasonAuthorPush AdminCanonOverrideReason = "author_push"
	// AdminOverrideReasonGovernance — governance body overrides a
	// reality-local L3 event divergence; documented in runbook.
	AdminOverrideReasonGovernance AdminCanonOverrideReason = "governance"
	// AdminOverrideReasonSafetyRollback — emergency rollback of a
	// canon edit that should never have shipped.
	AdminOverrideReasonSafetyRollback AdminCanonOverrideReason = "safety_rollback"
)

// IsValid returns true if r is one of the LOCKED reason values.
func (r AdminCanonOverrideReason) IsValid() bool {
	switch r {
	case AdminOverrideReasonAuthorPush,
		AdminOverrideReasonGovernance,
		AdminOverrideReasonSafetyRollback:
		return true
	}
	return false
}

// @event       admin.canon.override.requested
// @version     1
// @aggregate   canon
// @description Admin / author has opted-in to a force-propagate operation
//              for a canon entry. THIS IS THE EXPLICIT OPT-IN GATE (gate 1
//              of 3 per M4 §9.8.3). Emission triggers the consent collector
//              which fans per-reality consent requests to reality owners
//              with a 24h timeout (Q-L5H-1).
type AdminCanonOverrideRequestedV1 struct {
	OverrideID    uuid.UUID                `json:"override_id"`
	CanonEntryID  uuid.UUID                `json:"canon_entry_id"`
	BookID        uuid.UUID                `json:"book_id"`
	AttributePath string                   `json:"attribute_path"`
	NewValue      []byte                   `json:"new_value"`
	CanonLayer    CanonLayer               `json:"canon_layer"`
	Reason        AdminCanonOverrideReason `json:"reason"`
	RequestedBy   uuid.UUID                `json:"requested_by"`
	RequestedAt   time.Time                `json:"requested_at"`
	// ConsentDeadlineAt is `requested_at + 24h` (Q-L5H-1). The consent
	// collector enforces this deadline.
	ConsentDeadlineAt time.Time `json:"consent_deadline_at"`
}

// @event       admin.canon.override.consented
// @version     1
// @aggregate   canon
// @description Reality owner ACKed the force-propagate (gate 2 of 3 per
//              M4 §9.8.3). Either explicit ACK (default_consent=false) or
//              24h timeout default-to-consent per Q-L5H-1 LOCKED
//              (default_consent=true). The compensating event for this
//              reality is then emitted.
type AdminCanonOverrideConsentedV1 struct {
	OverrideID  uuid.UUID `json:"override_id"`
	RealityID   uuid.UUID `json:"reality_id"`
	ConsentedAt time.Time `json:"consented_at"`
	// DefaultConsent is true when the consent collector fired
	// default-to-consent after the 24h timeout (Q-L5H-1).
	DefaultConsent bool      `json:"default_consent"`
	// ConsentedBy is the user UUID that ACKed (or uuid.Nil when
	// default_consent=true).
	ConsentedBy uuid.UUID `json:"consented_by,omitempty"`
}

// @event       admin.canon.override.vetoed
// @version     1
// @aggregate   canon
// @description Reality owner refused the force-propagate (gate 2 of 3 per
//              M4 §9.8.3). The reality is SKIPPED — no compensating event
//              emitted for this reality, projection state unchanged.
type AdminCanonOverrideVetoedV1 struct {
	OverrideID uuid.UUID `json:"override_id"`
	RealityID  uuid.UUID `json:"reality_id"`
	VetoedAt   time.Time `json:"vetoed_at"`
	VetoedBy   uuid.UUID `json:"vetoed_by"`
	Reason     string    `json:"reason"`
}

// @event       admin.canon.override.compensating
// @version     1
// @aggregate   canon
// @description Per-reality compensating L3 event applied — the actual
//              side-effect of force-propagate on this reality's
//              canon_projection. Audit-distinguishable from a regular
//              canon.entry.updated by event_type. L5.J change-timeline
//              classifies as `force_propagate`.
type AdminCanonOverrideCompensatingV1 struct {
	OverrideID    uuid.UUID  `json:"override_id"`
	RealityID     uuid.UUID  `json:"reality_id"`
	CanonEntryID  uuid.UUID  `json:"canon_entry_id"`
	BookID        uuid.UUID  `json:"book_id"`
	AttributePath string     `json:"attribute_path"`
	OldValue      []byte     `json:"old_value"`
	NewValue      []byte     `json:"new_value"`
	CanonLayer    CanonLayer `json:"canon_layer"`
	AppliedAt     time.Time  `json:"applied_at"`
	// DefaultConsent mirrors the consented event so audit downstream can
	// distinguish forensically WITHOUT a join.
	DefaultConsent bool `json:"default_consent"`
}
