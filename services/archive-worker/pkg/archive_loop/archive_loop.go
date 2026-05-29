// Package archive_loop is the orchestrator. One Run() iteration per reality
// per scheduling tick. Flow:
//
//  1. partition_picker.PickOldest → chosen Partition (or nil → no-op)
//  2. RowSource.LoadPartition(chosen) → []EventRow
//  3. parquet_writer.Encode(rows) → blob
//  4. object_store.Put(bucket, key, blob)
//  5. object_store.Get(...) + parquet_writer.VerifyHeader(blob, rowcount)
//     — REJECT on mismatch; DO NOT drop the partition (invariant guard)
//  6. state.RecordArchived(...) — BEFORE the DROP so a crash mid-DROP
//     leaves the partition still attached, just marked as archived. Next
//     run picks it up via PickOldest (skips because state says done) ⇒
//     the operator's healing job DROPs it.
//  7. PartitionDropper.Drop(chosen) — DROP TABLE events_p_YYYY_MM
//
// CRITICAL INVARIANT: steps 5+6 MUST succeed BEFORE step 7. If 4 succeeds
// but 5 fails (corrupt upload), step 7 MUST NOT fire. The integration test
// `TestRun_FailedVerify_DoesNotDrop` drives this.
package archive_loop

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/archive-worker/pkg/object_store"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
	"github.com/loreweave/foundation/services/archive-worker/pkg/partition_picker"
	"github.com/loreweave/foundation/services/archive-worker/pkg/state"
	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// RowSource reads all rows from a partition. Production wires the
// ATTACH-to-staging-then-COPY-out flow (avoids holding a long lock on
// the live `events` table); tests inject a slice.
type RowSource interface {
	LoadPartition(ctx context.Context, p types.Partition) ([]types.EventRow, error)
}

// PartitionDropper removes the partition from Postgres. Production runs:
//   ALTER TABLE events DETACH PARTITION <name>;
//   DROP TABLE <name>;
// in a single TX. Tests record the call.
type PartitionDropper interface {
	Drop(ctx context.Context, p types.Partition) error
}

// ModeReader exposes ServiceMode for L1.J degraded-mode gating — at
// ModeEssentials+ the archive loop PAUSES (archive is background work).
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// Clock allows freezing the ArchivedAt timestamp in tests.
type Clock interface{ Now() time.Time }

// RealClock binds system time.
type RealClock struct{}

// Now returns the current system time.
func (RealClock) Now() time.Time { return time.Now() }

// Config is the constructor input.
type Config struct {
	Picker     *partition_picker.Picker
	Source     RowSource
	Encoder    parquet_writer.Writer
	Decoder    parquet_writer.Reader
	Store      object_store.Store
	State      state.Store
	Dropper    PartitionDropper
	Mode       ModeReader
	Clock      Clock
	BucketName string // "lw-event-archive"
}

// Loop is the orchestrator.
type Loop struct {
	picker  *partition_picker.Picker
	source  RowSource
	encoder parquet_writer.Writer
	decoder parquet_writer.Reader
	store   object_store.Store
	state   state.Store
	dropper PartitionDropper
	mode    ModeReader
	clock   Clock
	bucket  string
}

// New constructs a Loop. All deps MUST be non-nil; bucket MUST be non-empty.
func New(c Config) (*Loop, error) {
	if c.Picker == nil {
		return nil, errors.New("archive_loop: Picker nil")
	}
	if c.Source == nil {
		return nil, errors.New("archive_loop: Source nil")
	}
	if c.Encoder == nil {
		return nil, errors.New("archive_loop: Encoder nil")
	}
	if c.Decoder == nil {
		return nil, errors.New("archive_loop: Decoder nil")
	}
	if c.Store == nil {
		return nil, errors.New("archive_loop: Store nil")
	}
	if c.State == nil {
		return nil, errors.New("archive_loop: State nil")
	}
	if c.Dropper == nil {
		return nil, errors.New("archive_loop: Dropper nil")
	}
	if c.Mode == nil {
		return nil, errors.New("archive_loop: Mode nil")
	}
	if c.Clock == nil {
		return nil, errors.New("archive_loop: Clock nil")
	}
	if c.BucketName == "" {
		return nil, errors.New("archive_loop: BucketName empty")
	}
	return &Loop{
		picker:  c.Picker,
		source:  c.Source,
		encoder: c.Encoder,
		decoder: c.Decoder,
		store:   c.Store,
		state:   c.State,
		dropper: c.Dropper,
		mode:    c.Mode,
		clock:   c.Clock,
		bucket:  c.BucketName,
	}, nil
}

// IterationStats is the per-Run summary.
type IterationStats struct {
	RealityID  uuid.UUID
	Picked     bool   // false ⇒ nothing eligible
	Partition  string // populated when Picked
	Uploaded   bool
	Verified   bool
	Recorded   bool
	Dropped    bool
	Skipped    bool
	SkipReason string
	RowCount   int64
	ByteSize   int64
}

// Run executes ONE archive iteration for the given reality. Skips entirely
// when mode >= ModeEssentials (degraded-mode gating).
func (l *Loop) Run(ctx context.Context, realityID uuid.UUID) (IterationStats, error) {
	stats := IterationStats{RealityID: realityID}

	if l.mode.Mode() >= lifecycle.ModeEssentials {
		stats.Skipped = true
		stats.SkipReason = fmt.Sprintf("degraded_mode=%s", l.mode.Mode())
		return stats, nil
	}

	part, err := l.picker.PickOldest(ctx, realityID)
	if err != nil {
		return stats, fmt.Errorf("archive_loop: pick: %w", err)
	}
	if part == nil {
		return stats, nil // nothing eligible
	}
	stats.Picked = true
	stats.Partition = part.Name

	rows, err := l.source.LoadPartition(ctx, *part)
	if err != nil {
		return stats, fmt.Errorf("archive_loop: load %s: %w", part.Name, err)
	}
	stats.RowCount = int64(len(rows))

	blob, err := l.encoder.Encode(rows)
	if err != nil {
		return stats, fmt.Errorf("archive_loop: encode %s: %w", part.Name, err)
	}
	stats.ByteSize = int64(len(blob))

	// Derive YYYY-MM from the partition lower bound — single source of
	// truth (vs parsing the name; defense against rename drift).
	yearMonth := part.LowerBound.Format("2006-01")
	objKey := object_store.ObjectKey(realityID.String(), yearMonth)

	if err := l.store.Put(ctx, l.bucket, objKey, blob); err != nil {
		return stats, fmt.Errorf("archive_loop: put %s/%s: %w", l.bucket, objKey, err)
	}
	stats.Uploaded = true

	// Verify: read back the JUST-UPLOADED object and check header + row count.
	readBack, err := l.store.Get(ctx, l.bucket, objKey)
	if err != nil {
		// Upload appeared to succeed but readback failed — DO NOT drop.
		return stats, fmt.Errorf("archive_loop: verify get %s/%s: %w", l.bucket, objKey, err)
	}
	if err := parquet_writer.VerifyHeader(readBack, stats.RowCount); err != nil {
		// Corrupt or partial upload — DO NOT drop. The next run will
		// re-encounter the partition (no state row was written) and retry.
		return stats, fmt.Errorf("archive_loop: verify header %s/%s: %w", l.bucket, objKey, err)
	}
	stats.Verified = true

	// Record BEFORE drop (invariant: an archive_state row means the object
	// is in MinIO + verified; the partition may or may not still be in PG).
	obj := types.ArchivedObject{
		RealityID:    realityID,
		Partition:    part.Name,
		ObjectKey:    objKey,
		ByteSize:     stats.ByteSize,
		RowCount:     stats.RowCount,
		ArchivedAt:   l.clock.Now(),
		FormatHeader: parquet_writer.Magic,
	}
	if err := l.state.RecordArchived(ctx, obj); err != nil {
		return stats, fmt.Errorf("archive_loop: record %s: %w", part.Name, err)
	}
	stats.Recorded = true

	// Finally, drop the partition. If this fails the operator runbook
	// covers manual DROP — the state row says the data is safe in MinIO.
	if err := l.dropper.Drop(ctx, *part); err != nil {
		return stats, fmt.Errorf("archive_loop: drop %s: %w", part.Name, err)
	}
	stats.Dropped = true

	return stats, nil
}
