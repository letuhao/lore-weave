package meta

import (
	"fmt"
	"strings"

	"github.com/google/uuid"
)

// MetaWriteOp enumerates the SQL operations MetaWrite emits. Mirrors the
// CHECK constraint on meta_write_audit.operation (S04 §12T.5).
type MetaWriteOp string

const (
	OpInsert MetaWriteOp = "INSERT"
	OpUpdate MetaWriteOp = "UPDATE"
	OpDelete MetaWriteOp = "DELETE"
)

// IsValid returns true for the enumerated set.
func (o MetaWriteOp) IsValid() bool {
	switch o {
	case OpInsert, OpUpdate, OpDelete:
		return true
	}
	return false
}

// MetaWriteIntent is the input to MetaWrite. See L1.B §3 for behavior.
//
// For UPDATEs, populate ExpectedBefore when you want CAS — the library
// converts to `UPDATE ... WHERE pk = :pk AND <expected_before>` and returns
// ErrConcurrentStateTransition on 0 rows affected.
//
// NewValues is required for INSERT and UPDATE. For DELETE, the library
// ignores NewValues but still writes the before-image row to audit.
type MetaWriteIntent struct {
	Table          string
	Operation      MetaWriteOp
	PK             map[string]any
	ExpectedBefore map[string]any // CAS UPDATE only — optional
	NewValues      map[string]any
	Actor          Actor
	Reason         string // required for destructive ops (DELETE)
	RequestContext RequestContext
	// OutboxPayload OPTIONALLY overrides the emitted outbox event's payload
	// (P2/113). nil ⇒ the generic CDC payload {table, operation, pk, after}.
	// When set, this exact map is the OutboxEvent.Payload — so a caller can emit
	// the canonical DOMAIN event shape (e.g. XRealityUserErasedV1 {user_id,
	// erased_at}) that cross-reality consumers expect, instead of the CDC view.
	// Only consulted when the (table, op) is allowlisted to emit an event AND a
	// cfg.Outbox is configured. The caller owns this payload's PII posture
	// (the generic CDC default's unscrubbed-NewValues caveat — 114 — does not
	// apply; this is exactly what the caller put here).
	OutboxPayload map[string]any
	// LifecycleAudit, when non-nil, inserts ONE lifecycle_transition_audit row in
	// the SAME TX as this write (S13: makes the I9 transition + its lifecycle audit
	// atomic — a crash can no longer leave the status changed but the lifecycle
	// audit missing). Set by AttemptStateTransition on the SUCCESS path only; the
	// failed-attempt audit still writes in its own TX by design (it must survive the
	// data-write rollback).
	LifecycleAudit *LifecycleTransitionAuditRow
}

// Validate checks the intent against fail-fast rules:
//   - Table is non-empty and in the allowlist
//   - Operation is enumerated
//   - PK is non-empty
//   - NewValues required for INSERT/UPDATE
//   - Reason required for DELETE
//   - Actor.Type is enumerated
func (i MetaWriteIntent) Validate(allowlist Allowlist) error {
	if strings.TrimSpace(i.Table) == "" {
		return fmt.Errorf("%w: table is empty", ErrBadIntent)
	}
	if allowlist != nil && !allowlist.AllowsTable(i.Table) {
		return fmt.Errorf("%w: %q", ErrTableNotAllowlisted, i.Table)
	}
	if !i.Operation.IsValid() {
		return fmt.Errorf("%w: operation=%q", ErrBadIntent, i.Operation)
	}
	if len(i.PK) == 0 {
		return fmt.Errorf("%w: PK is empty", ErrBadIntent)
	}
	if (i.Operation == OpInsert || i.Operation == OpUpdate) && len(i.NewValues) == 0 {
		return fmt.Errorf("%w: NewValues required for %s", ErrBadIntent, i.Operation)
	}
	if i.Operation == OpDelete && strings.TrimSpace(i.Reason) == "" {
		return fmt.Errorf("%w: Reason required for DELETE", ErrBadIntent)
	}
	if !i.Actor.Type.IsValid() {
		return fmt.Errorf("%w: actor.type=%q", ErrBadIntent, i.Actor.Type)
	}
	return nil
}

// MetaWriteResult is the post-write echo returned by MetaWrite.
type MetaWriteResult struct {
	AuditID      uuid.UUID
	RowsAffected int
	NewValues    map[string]any
}

// TransitionRequest is the input to AttemptStateTransition. See L1.B §4.
type TransitionRequest struct {
	ResourceType string // "reality" | "incident" | "deploy" | …
	ResourceID   string
	FromState    string
	ToState      string
	Reason       string
	Actor        Actor
	Payload      map[string]any // extra fields to set in same UPDATE (e.g., close_initiated_by)
}

// Validate checks the request against fail-fast rules.
func (t TransitionRequest) Validate() error {
	if strings.TrimSpace(t.ResourceType) == "" {
		return fmt.Errorf("%w: resource_type empty", ErrBadIntent)
	}
	if strings.TrimSpace(t.ResourceID) == "" {
		return fmt.Errorf("%w: resource_id empty", ErrBadIntent)
	}
	if strings.TrimSpace(t.FromState) == "" || strings.TrimSpace(t.ToState) == "" {
		return fmt.Errorf("%w: from/to state empty", ErrBadIntent)
	}
	if !t.Actor.Type.IsValid() {
		return fmt.Errorf("%w: actor.type=%q", ErrBadIntent, t.Actor.Type)
	}
	return nil
}

// TransitionResult is returned by AttemptStateTransition on success.
type TransitionResult struct {
	AuditID      uuid.UUID
	NewState     string
	TransitionAt int64 // unix nanos — caller-side conversion to time.Time
}
