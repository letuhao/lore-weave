// Package audit_emitter writes admin_action_audit rows on every command
// invocation. Wired via MetaWrite (contracts/meta) in production; tests use
// the in-memory Sink stub.
//
// Per cycle 4 (L1.A-3): admin_action_audit owner = admin-cli; events_allowlist
// confirms `events: []` (audit rows do NOT outbox).
//
// Per cycle 36 (L7.A): the framework wraps every command in Run() →
// Audit.Before/After/Failure so callers cannot bypass auditing. Audit hook
// lives at the FRAMEWORK level (DRY) — individual command handlers do NOT
// emit audit rows themselves.
package audit_emitter

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// Action is one audited admin invocation.
type Action struct {
	CommandName       string
	Actor             string
	ActorRole         string
	Reason            string
	ParamsHash        string // SHA-256 hash of normalized params (NEVER raw PII)
	ImpactClass       string
	DryRun            bool
	DoubleApprovalRef string // ticket / second-actor user_ref, if applicable
	StartedAt         time.Time
	FinishedAt        time.Time
	Outcome           string // "started" | "succeeded" | "failed"
	ErrorDetailHash   string // SHA-256(err); raw error scrubbed via S08 §12X.5
}

// Sink persists Actions. Prod wires to a contracts/meta MetaWrite adapter
// targeting the admin_action_audit table; tests use MemorySink.
type Sink interface {
	Write(ctx context.Context, a Action) error
}

// Emitter wraps a Sink and provides Before/After/Failure helpers.
type Emitter struct {
	sink Sink
	now  func() time.Time
}

// New returns an Emitter. now=nil → time.Now.
func New(sink Sink, now func() time.Time) *Emitter {
	if now == nil {
		now = time.Now
	}
	return &Emitter{sink: sink, now: now}
}

// ErrAudit is returned on sink errors.
var ErrAudit = errors.New("admin-cli/audit_emitter")

// Before records the start of an action and returns the started Action so the
// caller can mutate Outcome + FinishedAt before calling After / Failure.
func (e *Emitter) Before(ctx context.Context, a Action) (Action, error) {
	a.StartedAt = e.now()
	a.Outcome = "started"
	if err := e.sink.Write(ctx, a); err != nil {
		return a, fmt.Errorf("%w: before: %v", ErrAudit, err)
	}
	return a, nil
}

// After records a successful completion.
func (e *Emitter) After(ctx context.Context, a Action) error {
	a.FinishedAt = e.now()
	a.Outcome = "succeeded"
	if err := e.sink.Write(ctx, a); err != nil {
		return fmt.Errorf("%w: after: %v", ErrAudit, err)
	}
	return nil
}

// Failure records a failed completion.
func (e *Emitter) Failure(ctx context.Context, a Action, errDetailHash string) error {
	a.FinishedAt = e.now()
	a.Outcome = "failed"
	a.ErrorDetailHash = errDetailHash
	if err := e.sink.Write(ctx, a); err != nil {
		return fmt.Errorf("%w: failure: %v", ErrAudit, err)
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────────────────
// MemorySink — in-memory test sink, goroutine-safe.
// ─────────────────────────────────────────────────────────────────────────────

// MemorySink stores actions for inspection in tests.
type MemorySink struct {
	mu      sync.Mutex
	actions []Action
}

// NewMemorySink returns an empty MemorySink.
func NewMemorySink() *MemorySink { return &MemorySink{} }

// Write satisfies Sink.
func (m *MemorySink) Write(_ context.Context, a Action) error {
	m.mu.Lock()
	m.actions = append(m.actions, a)
	m.mu.Unlock()
	return nil
}

// All returns a defensive copy of every Action recorded.
func (m *MemorySink) All() []Action {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]Action, len(m.actions))
	copy(out, m.actions)
	return out
}

// Count returns the number of rows written.
func (m *MemorySink) Count() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.actions)
}
