// Package partition_picker discovers the oldest eligible per-reality monthly
// partition of `events` whose UpperBound is past the configured archive
// cutoff (default 90d).
//
// Picker filters out:
//   - partitions that are not eligible yet (still within retention window)
//   - partitions already recorded in `archive_state` (idempotency guard;
//     prevents re-uploading + re-DROP attempts)
//
// The IO boundary is abstracted as `Catalog` (Postgres pg_inherits) +
// `StateReader` (archive_state SELECT). Tests inject in-mem fakes.
package partition_picker

import (
	"context"
	"errors"
	"sort"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// Catalog enumerates the per-reality monthly partitions of `events`.
// Production impl runs:
//   SELECT inhrelid::regclass::text
//     FROM pg_inherits
//    WHERE inhparent = 'events'::regclass;
// and parses each name suffix `_YYYY_MM` into lower/upper bounds.
type Catalog interface {
	ListPartitions(ctx context.Context, realityID uuid.UUID) ([]types.Partition, error)
}

// StateReader looks up which partitions are already archived for a reality
// (the `archive_state` table populated by pkg/state.RecordArchived). Pass-
// through for the picker to filter the catalog list.
type StateReader interface {
	AlreadyArchived(ctx context.Context, realityID uuid.UUID) (map[string]struct{}, error)
}

// Clock allows tests to freeze the cutoff comparison.
type Clock interface{ Now() time.Time }

// RealClock binds the system time.
type RealClock struct{}

// Now returns the current system time.
func (RealClock) Now() time.Time { return time.Now() }

// Config is the constructor input.
type Config struct {
	Catalog Catalog
	State   StateReader
	Clock   Clock
	// Cutoff — how old must a partition's UpperBound be before it is
	// eligible. Default 90 days (matches R01 §12A.4 archive cadence).
	Cutoff time.Duration
}

// Picker is the partition selector.
type Picker struct {
	catalog Catalog
	state   StateReader
	clock   Clock
	cutoff  time.Duration
}

// New constructs a Picker. All deps MUST be non-nil; Cutoff defaults to 90d
// when <= 0.
func New(c Config) (*Picker, error) {
	if c.Catalog == nil {
		return nil, errors.New("partition_picker: Catalog nil")
	}
	if c.State == nil {
		return nil, errors.New("partition_picker: State nil")
	}
	if c.Clock == nil {
		return nil, errors.New("partition_picker: Clock nil")
	}
	cutoff := c.Cutoff
	if cutoff <= 0 {
		cutoff = 90 * 24 * time.Hour
	}
	return &Picker{
		catalog: c.Catalog,
		state:   c.State,
		clock:   c.Clock,
		cutoff:  cutoff,
	}, nil
}

// PickOldest returns the OLDEST eligible un-archived partition for the given
// reality, or (nil, nil) if none.
//
// "Oldest" = smallest UpperBound. This drains the historical backlog in
// strictly time-ascending order so an archive-worker that has been off for
// weeks catches up in the natural sequence.
func (p *Picker) PickOldest(ctx context.Context, realityID uuid.UUID) (*types.Partition, error) {
	parts, err := p.catalog.ListPartitions(ctx, realityID)
	if err != nil {
		return nil, err
	}
	already, err := p.state.AlreadyArchived(ctx, realityID)
	if err != nil {
		return nil, err
	}
	now := p.clock.Now()

	var eligible []types.Partition
	for _, pp := range parts {
		if _, done := already[pp.Name]; done {
			continue
		}
		if !pp.Eligible(now, p.cutoff) {
			continue
		}
		eligible = append(eligible, pp)
	}
	if len(eligible) == 0 {
		return nil, nil
	}
	sort.SliceStable(eligible, func(i, j int) bool {
		return eligible[i].UpperBound.Before(eligible[j].UpperBound)
	})
	chosen := eligible[0]
	return &chosen, nil
}
