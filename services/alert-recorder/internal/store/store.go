// Package store is the alert-recorder persistence layer. It writes
// `alert_outcomes` (received, dispatched, resolved, silenced) +
// `alert_silences` (silence policy enforcement).
//
// V1 SKELETON: in-memory store. Live wiring to meta-postgres via
// MetaWrite is tracked as a follow-up (same pattern as cycle 11
// retention-worker — pure library here, RPC binding later).
package store

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/foundation/contracts/alerts"
)

// Outcome is a row of alert_outcomes (SR2 §12AE.8).
type Outcome struct {
	OutcomeID     uuid.UUID
	AlertID       uuid.UUID
	RuleID        string
	Severity      alerts.Severity
	Action        alerts.Action
	SLIRef        string
	Tier          string
	CorrelationID string
	State         string // "received" | "dispatched" | "resolved" | "silenced"
	StateAt       time.Time
	ReceivedAt    time.Time
}

// Silence is a row of alert_silences (matches silence_admission_policy.yaml).
type Silence struct {
	SilenceID    uuid.UUID
	Actor        string
	Category     string
	Reason       string
	CreatedAt    time.Time
	ExpiresAt    time.Time
	AlertMatcher string
	Origin       string
	IncidentID   string // optional
	TicketID     string // optional
}

// Store is the storage facade. The concrete implementation here is in-memory;
// the live wiring (D-ALERT-RECORDER-LIVE-WIRING follow-up) binds a pgx adapter.
type Store interface {
	WriteOutcome(ctx context.Context, o Outcome) error
	ListOutcomes(ctx context.Context, limit int) ([]Outcome, error)
	WriteSilence(ctx context.Context, s Silence) error
	ListActiveSilences(ctx context.Context, now time.Time) ([]Silence, error)
}

// MemoryStore is a goroutine-safe in-memory Store for V1 + tests.
type MemoryStore struct {
	mu       sync.Mutex
	outcomes []Outcome
	silences []Silence
}

// NewMemoryStore returns a fresh in-memory store.
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{}
}

// WriteOutcome appends an outcome row.
func (m *MemoryStore) WriteOutcome(_ context.Context, o Outcome) error {
	if o.AlertID == uuid.Nil {
		return errors.New("store: WriteOutcome: alert_id required")
	}
	if o.State == "" {
		return errors.New("store: WriteOutcome: state required")
	}
	if o.OutcomeID == uuid.Nil {
		o.OutcomeID = uuid.New()
	}
	m.mu.Lock()
	m.outcomes = append(m.outcomes, o)
	m.mu.Unlock()
	return nil
}

// ListOutcomes returns the most-recent N outcomes (newest first).
func (m *MemoryStore) ListOutcomes(_ context.Context, limit int) ([]Outcome, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	n := len(m.outcomes)
	if limit > 0 && n > limit {
		n = limit
	}
	out := make([]Outcome, n)
	// Newest first
	for i := 0; i < n; i++ {
		out[i] = m.outcomes[len(m.outcomes)-1-i]
	}
	return out, nil
}

// WriteSilence appends a silence row.
func (m *MemoryStore) WriteSilence(_ context.Context, s Silence) error {
	if s.Actor == "" {
		return errors.New("store: WriteSilence: actor required (audit)")
	}
	if s.Category == "" {
		return errors.New("store: WriteSilence: category required")
	}
	if s.Reason == "" {
		return errors.New("store: WriteSilence: reason required (audit)")
	}
	if s.AlertMatcher == "" {
		return errors.New("store: WriteSilence: alert_matcher required")
	}
	if s.ExpiresAt.Before(s.CreatedAt) {
		return errors.New("store: WriteSilence: expires_at must be after created_at")
	}
	if s.SilenceID == uuid.Nil {
		s.SilenceID = uuid.New()
	}
	m.mu.Lock()
	m.silences = append(m.silences, s)
	m.mu.Unlock()
	return nil
}

// ListActiveSilences returns silences where ExpiresAt > now.
func (m *MemoryStore) ListActiveSilences(_ context.Context, now time.Time) ([]Silence, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	active := make([]Silence, 0, len(m.silences))
	for _, s := range m.silences {
		if s.ExpiresAt.After(now) {
			active = append(active, s)
		}
	}
	return active, nil
}
