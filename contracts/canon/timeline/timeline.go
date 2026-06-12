package timeline

import (
	"context"
	"errors"
	"time"

	"github.com/google/uuid"
)

// CanonChangeKind mirrors contracts/events/canon_change_history.go to
// avoid an import cycle for downstream consumers that only need the SDK
// surface. The string values MUST stay byte-equal.
type CanonChangeKind string

const (
	CanonChangeKindAuthored             CanonChangeKind = "authored"
	CanonChangeKindForcePropagate       CanonChangeKind = "force_propagate"
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

// Entry is one row in the change timeline. Maps 1:1 to the
// `canon_change_history` table row + `canon.change.recorded` event.
type Entry struct {
	ChangeID        uuid.UUID       `json:"change_id"`
	CanonEntryID    uuid.UUID       `json:"canon_entry_id"`
	BookID          uuid.UUID       `json:"book_id"`
	AttributePath   string          `json:"attribute_path"`
	RealityID       uuid.UUID       `json:"reality_id,omitempty"`
	Kind            CanonChangeKind `json:"kind"`
	OldValue        []byte          `json:"old_value,omitempty"`
	NewValue        []byte          `json:"new_value"`
	CanonLayer      string          `json:"canon_layer"`
	SourceEventID   uuid.UUID       `json:"source_event_id"`
	SourceEventType string          `json:"source_event_type"`
	RecordedAt      time.Time       `json:"recorded_at"`
}

// Query is the input to TimelineQueryer.Query. Either CanonEntryID is set
// (entry-scoped) OR (BookID + AttributePath) (path-scoped). One mode must
// be picked — see Validate.
type Query struct {
	// CanonEntryID is the strongest filter: returns ALL history for one
	// canon row (across all realities + book scope).
	CanonEntryID uuid.UUID
	// BookID + AttributePath together filter by attribute (covers all
	// canon rows whose attribute path matches). Use when the canon_entry
	// has been replaced (e.g. promote from L2 to L1 created a new entry).
	BookID        uuid.UUID
	AttributePath string
	// RealityID — optional; further filters to per-reality changes
	// (e.g. force-propagate compensating events for one reality).
	RealityID uuid.UUID
	// Since — optional; returns only entries with recorded_at >= Since.
	Since time.Time
	// Limit — optional; 0 means "use TimelineQueryer default" (capped at
	// 1000 by production impls).
	Limit int
}

// Validate enforces "one query mode must be picked".
func (q Query) Validate() error {
	hasEntry := q.CanonEntryID != uuid.Nil
	hasPath := q.BookID != uuid.Nil && q.AttributePath != ""
	if !hasEntry && !hasPath {
		return errors.New("timeline: Query requires CanonEntryID OR (BookID + AttributePath)")
	}
	if q.Limit < 0 {
		return errors.New("timeline: Query.Limit must be >= 0")
	}
	return nil
}

// TimelineQueryer is the foundational read-side contract. Author-UI
// implementations call Query to fetch the change timeline for an entity.
//
// **APPEND-ONLY discipline**: no Update / Delete / Amend method exists
// on this surface. The contract is read + append-only-via-event-producer
// (canon_history_writer).
type TimelineQueryer interface {
	Query(ctx context.Context, q Query) ([]Entry, error)
}

// TimelineAppender is the WRITER side — used by canon_history_writer.
// Production binds this to an INSERT into the canon_change_history table.
// The interface has NO update/delete by design.
type TimelineAppender interface {
	Append(ctx context.Context, e Entry) error
}

// InMemoryStore is a reference impl used by tests + by foundation V1
// when no DB is bound. Thread-safe.
//
// Provides both Append (TimelineAppender) and Query (TimelineQueryer).
type InMemoryStore struct {
	mu      mu
	entries []Entry
}

// mu wraps a sync.Mutex via an interface seam so the package go.mod
// can stay sync-free. We use the std-lib mutex directly through embedded
// usage; mu is just the field type alias to keep the struct definition
// readable.
type mu struct {
	syncMu
}

type syncMu = lockable

// lockable lets tests inject a noop lock if desired (e.g. for single-
// threaded property tests). Production wraps sync.Mutex.
type lockable interface {
	Lock()
	Unlock()
}

// NewInMemoryStore constructs an InMemoryStore backed by sync.Mutex.
func NewInMemoryStore() *InMemoryStore {
	return &InMemoryStore{mu: mu{syncMu: newSyncMutex()}}
}

// Append inserts the entry. APPEND-ONLY — no overwrite path exists.
func (s *InMemoryStore) Append(_ context.Context, e Entry) error {
	if e.ChangeID == uuid.Nil {
		return errors.New("timeline: ChangeID required")
	}
	if !e.Kind.IsValid() {
		return errors.New("timeline: invalid Kind")
	}
	if e.RecordedAt.IsZero() {
		return errors.New("timeline: RecordedAt required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	// Defensive: enforce no overwrite on duplicate ChangeID (would
	// indicate either retry or a producer bug; either way the second
	// write is rejected to preserve append-only).
	for _, existing := range s.entries {
		if existing.ChangeID == e.ChangeID {
			return errors.New("timeline: duplicate ChangeID (APPEND-ONLY)")
		}
	}
	s.entries = append(s.entries, e)
	return nil
}

// Query returns matching entries in RecordedAt-ascending order.
func (s *InMemoryStore) Query(_ context.Context, q Query) ([]Entry, error) {
	if err := q.Validate(); err != nil {
		return nil, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	var out []Entry
	for _, e := range s.entries {
		if !matchesQuery(e, q) {
			continue
		}
		out = append(out, e)
	}
	// Sort ascending by RecordedAt to give author-UI a deterministic order.
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && out[j-1].RecordedAt.After(out[j].RecordedAt); j-- {
			out[j-1], out[j] = out[j], out[j-1]
		}
	}
	if q.Limit > 0 && len(out) > q.Limit {
		out = out[:q.Limit]
	}
	return out, nil
}

// Count returns the total entry count (test helper).
func (s *InMemoryStore) Count() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.entries)
}

func matchesQuery(e Entry, q Query) bool {
	if q.CanonEntryID != uuid.Nil {
		if e.CanonEntryID != q.CanonEntryID {
			return false
		}
	} else {
		if e.BookID != q.BookID || e.AttributePath != q.AttributePath {
			return false
		}
	}
	if q.RealityID != uuid.Nil && e.RealityID != q.RealityID {
		return false
	}
	if !q.Since.IsZero() && e.RecordedAt.Before(q.Since) {
		return false
	}
	return true
}
