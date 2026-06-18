// Package state is the archive-worker's idempotency ledger.
//
// `archive_state` is a per-reality table (not a meta table) recording every
// partition that has been successfully archived + DROPped. The picker reads
// it to filter out already-done work; the loop writes it AFTER a verified
// upload, BEFORE the partition DROP — that ordering guarantees a re-run
// after a mid-flight crash will skip the already-archived partition rather
// than re-uploading and double-DROPping.
//
// Production wiring binds to per-reality Postgres; tests use the in-mem
// impl below.
package state

import (
	"context"
	"sync"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// Store is the IO boundary. Production impl is `state.Postgres` (deferred
// to D-ARCHIVE-PARQUET-PROD-WIRING); tests use `state.InMemory`.
type Store interface {
	// AlreadyArchived returns the set of partition names already recorded
	// as archived for this reality. Matches partition_picker.StateReader.
	AlreadyArchived(ctx context.Context, realityID uuid.UUID) (map[string]struct{}, error)
	// RecordArchived inserts the manifest row. MUST be idempotent on
	// (reality_id, partition_name) — re-runs use INSERT ... ON CONFLICT
	// DO NOTHING. Returns the row that landed.
	RecordArchived(ctx context.Context, obj types.ArchivedObject) error
	// List returns all manifest rows for a reality (used by
	// cmd/archive-restore to enumerate restorable months).
	List(ctx context.Context, realityID uuid.UUID) ([]types.ArchivedObject, error)
}

// InMemory is the test-fake impl. Concurrent-safe.
type InMemory struct {
	mu   sync.Mutex
	rows map[uuid.UUID]map[string]types.ArchivedObject
}

// NewInMemory constructs an empty in-mem store.
func NewInMemory() *InMemory {
	return &InMemory{rows: map[uuid.UUID]map[string]types.ArchivedObject{}}
}

// AlreadyArchived returns the partition-name set for a reality.
func (s *InMemory) AlreadyArchived(_ context.Context, realityID uuid.UUID) (map[string]struct{}, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := map[string]struct{}{}
	for name := range s.rows[realityID] {
		out[name] = struct{}{}
	}
	return out, nil
}

// RecordArchived idempotently inserts the manifest row. Re-inserts on the
// same (reality, partition) leave the existing row unchanged (mirrors the
// production ON CONFLICT DO NOTHING semantics).
func (s *InMemory) RecordArchived(_ context.Context, obj types.ArchivedObject) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.rows[obj.RealityID] == nil {
		s.rows[obj.RealityID] = map[string]types.ArchivedObject{}
	}
	if _, exists := s.rows[obj.RealityID][obj.Partition]; exists {
		return nil // idempotent — first writer wins
	}
	s.rows[obj.RealityID][obj.Partition] = obj
	return nil
}

// List enumerates all manifest rows for a reality.
func (s *InMemory) List(_ context.Context, realityID uuid.UUID) ([]types.ArchivedObject, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	per := s.rows[realityID]
	out := make([]types.ArchivedObject, 0, len(per))
	for _, o := range per {
		out = append(out, o)
	}
	return out, nil
}
