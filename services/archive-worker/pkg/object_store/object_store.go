// Package object_store is the MinIO/S3 abstraction the archive-worker uses to
// upload Parquet blobs.
//
// Production binding (deferred to D-ARCHIVE-PARQUET-PROD-WIRING) is minio-go
// against the `lw-event-archive` bucket. Tests use the in-mem fake here.
//
// Key shape: `events/<reality_id>/<YYYY>-<MM>.parquet`. The
// reality_id-first prefix is INTENTIONAL — it enables:
//   - per-tenant restore (LIST by `events/<reality_id>/` lists all months)
//   - per-tenant cost accounting in V3+
//   - per-tenant erasure (GDPR right-to-be-forgotten) via key-prefix delete
package object_store

import (
	"context"
	"errors"
	"fmt"
	"sync"
)

// Store is the IO boundary.
type Store interface {
	// Put uploads a blob. Idempotent on (bucket, key) — re-uploading the
	// same key overwrites. The archive-worker NEVER re-uploads (idempotency
	// is enforced upstream by archive_state); a Put on an existing key is
	// treated as a contract violation and the production wiring SHOULD
	// reject via S3 versioning + the verify-after-upload step.
	Put(ctx context.Context, bucket, key string, blob []byte) error
	// Get reads back a blob — used by the verify-after-upload step + the
	// archive-restore CLI.
	Get(ctx context.Context, bucket, key string) ([]byte, error)
	// Exists is a cheap HEAD check used by archive_loop to detect a prior
	// partial upload (rare; primary idempotency is via archive_state).
	Exists(ctx context.Context, bucket, key string) (bool, error)
}

// ObjectKey builds the canonical key shape used by every archive object.
func ObjectKey(realityID, yearMonth string) string {
	return fmt.Sprintf("events/%s/%s.parquet", realityID, yearMonth)
}

// InMemory is the test-fake impl.
type InMemory struct {
	mu    sync.Mutex
	blobs map[string][]byte // bucket/key → blob
}

// NewInMemory constructs an empty in-mem store.
func NewInMemory() *InMemory {
	return &InMemory{blobs: map[string][]byte{}}
}

func key(bucket, k string) string { return bucket + "/" + k }

// Put uploads.
func (s *InMemory) Put(_ context.Context, bucket, k string, blob []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if bucket == "" || k == "" {
		return errors.New("object_store: empty bucket or key")
	}
	cp := make([]byte, len(blob))
	copy(cp, blob)
	s.blobs[key(bucket, k)] = cp
	return nil
}

// Get reads.
func (s *InMemory) Get(_ context.Context, bucket, k string) ([]byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	b, ok := s.blobs[key(bucket, k)]
	if !ok {
		return nil, fmt.Errorf("object_store: not found: %s/%s", bucket, k)
	}
	cp := make([]byte, len(b))
	copy(cp, b)
	return cp, nil
}

// Exists checks.
func (s *InMemory) Exists(_ context.Context, bucket, k string) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.blobs[key(bucket, k)]
	return ok, nil
}

// FailingStore is a test util whose Put always fails — used to drive the
// "DO NOT DROP the partition if upload failed" invariant test.
type FailingStore struct {
	Err error
}

// Put always returns the configured error.
func (f *FailingStore) Put(_ context.Context, _, _ string, _ []byte) error {
	if f.Err != nil {
		return f.Err
	}
	return errors.New("object_store: forced failure")
}

// Get always fails.
func (f *FailingStore) Get(_ context.Context, _, _ string) ([]byte, error) {
	return nil, errors.New("object_store: forced failure")
}

// Exists returns false.
func (*FailingStore) Exists(_ context.Context, _, _ string) (bool, error) {
	return false, nil
}
