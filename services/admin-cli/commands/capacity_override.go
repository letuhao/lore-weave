// Package commands implements admin-cli sub-commands.
//
// L1.L.3 (cycle 7) ships `admin capacity-override`. S5-D5 Tier-2 destructive
// command with 24h auto-expire enforced by the DB CHECK constraint on
// scaling_events.override_expires_at (see migrations/meta/025_scaling_events.up.sql).
//
// admin-cli main binary lands cycle 36; this file ships the command logic +
// tests so the design pattern is locked.
package commands

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// CapacityOverrideRequest captures the input to admin capacity-override.
type CapacityOverrideRequest struct {
	ShardHost string
	Reason    string
	Hours     int
	Actor     string // user_ref_id
}

// ErrInvalidOverride is returned by Validate / Apply when input fails policy.
var ErrInvalidOverride = errors.New("admin-cli: invalid capacity override")

// Validate enforces S5-D5 invariants. Returns ErrInvalidOverride.
func (r CapacityOverrideRequest) Validate() error {
	if r.ShardHost == "" {
		return fmt.Errorf("%w: shard_host empty", ErrInvalidOverride)
	}
	if r.Reason == "" {
		return fmt.Errorf("%w: reason empty (audit requires explanation)", ErrInvalidOverride)
	}
	if r.Hours <= 0 {
		return fmt.Errorf("%w: hours must be > 0", ErrInvalidOverride)
	}
	if r.Hours > 24 {
		return fmt.Errorf("%w: hours=%d exceeds S5-D5 24h cap (chained overrides allowed but each capped)", ErrInvalidOverride, r.Hours)
	}
	if r.Actor == "" {
		return fmt.Errorf("%w: actor empty", ErrInvalidOverride)
	}
	return nil
}

// OverrideRecord is what gets written to scaling_events.
type OverrideRecord struct {
	ShardHost        string
	Reason           string
	Actor            string
	CreatedAtNanos   int64
	ExpiresAtNanos   int64
}

// MetaWriter is the contract for persisting an override row. The real
// MetaWrite() binding lives in contracts/meta; for the command we depend on
// this small interface so the unit test can stub.
type MetaWriter interface {
	WriteOverride(ctx context.Context, rec OverrideRecord) error
}

// ClockFn returns "now" — injectable for tests.
type ClockFn func() time.Time

// Apply persists the override. Returns the written record or an error.
//
// Implementation contract:
//   1. Validate request.
//   2. Compute ExpiresAt = now + hours.
//   3. Call MetaWriter.WriteOverride which MUST go through MetaWrite() so
//      the same-TX meta_write_audit row is written.
//   4. Return the record so the caller can confirm to operator.
func Apply(ctx context.Context, req CapacityOverrideRequest, writer MetaWriter, clock ClockFn) (OverrideRecord, error) {
	if err := req.Validate(); err != nil {
		return OverrideRecord{}, err
	}
	now := clock()
	rec := OverrideRecord{
		ShardHost:      req.ShardHost,
		Reason:         req.Reason,
		Actor:          req.Actor,
		CreatedAtNanos: now.UnixNano(),
		ExpiresAtNanos: now.Add(time.Duration(req.Hours) * time.Hour).UnixNano(),
	}
	if err := writer.WriteOverride(ctx, rec); err != nil {
		return OverrideRecord{}, fmt.Errorf("admin-cli: write override: %w", err)
	}
	return rec, nil
}
