package commands

// Live `reality capacity-override` (073). S5-D5 Tier-2 griefing command: records
// a 24h-auto-expiring capacity-gate override into scaling_events via contracts/
// meta MetaWrite (so the write is itself audited in meta_write_audit, same TX).
//
// The 24h cap is enforced in THREE places (defense in depth):
//   1. Validate() rejects hours > 24 with a clear message.
//   2. ExpiresAt is computed from the SAME clock read as CreatedAt.
//   3. migration 025 CHECK scaling_events_override_expiry_within_24h is the DB
//      backstop (override_expires_at <= created_at + INTERVAL '24 hours').
//
// Consolidates the cycle-7 pure-logic prototype (was services/admin-cli/commands/
// capacity_override.go — dead, never wired) into the live internal/commands path.

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

// ErrInvalidOverride is returned by Validate / RunCapacityOverride on bad input.
var ErrInvalidOverride = errors.New("capacity-override: invalid request")

// CapacityOverrideRequest captures the input to `admin reality capacity-override`.
// Actor is the admin subject (JWT sub, a UUID string) set by the dispatcher.
type CapacityOverrideRequest struct {
	ShardHost string
	Reason    string
	Hours     int
	Actor     string
	DryRun    bool
}

// Validate enforces the S5-D5 Tier-2 invariants. The dispatcher already enforces
// reason >= 10 chars for tier-2; we additionally guard the structural fields.
func (r CapacityOverrideRequest) Validate() error {
	if strings.TrimSpace(r.ShardHost) == "" {
		return fmt.Errorf("%w: shard_host empty", ErrInvalidOverride)
	}
	if strings.TrimSpace(r.Reason) == "" {
		return fmt.Errorf("%w: reason empty (audit requires explanation)", ErrInvalidOverride)
	}
	if r.Hours <= 0 {
		return fmt.Errorf("%w: hours must be > 0", ErrInvalidOverride)
	}
	if r.Hours > 24 {
		return fmt.Errorf("%w: hours=%d exceeds S5-D5 24h cap (chained overrides allowed, each capped)", ErrInvalidOverride, r.Hours)
	}
	if strings.TrimSpace(r.Actor) == "" {
		return fmt.Errorf("%w: actor empty", ErrInvalidOverride)
	}
	return nil
}

// ScalingOverride is the resolved override record handed to the writer (one
// scaling_events row, event_type='override').
type ScalingOverride struct {
	ShardHost string
	Reason    string
	Actor     string // admin subject UUID string → scaling_events.initiated_by
	Hours     int
	CreatedAt time.Time
	ExpiresAt time.Time
}

// ScalingEventWriter persists an override row. The prod impl is
// PgScalingEventWriter (MetaWrite); tests use a fake.
type ScalingEventWriter interface {
	WriteOverride(ctx context.Context, ov ScalingOverride) error
}

// RunCapacityOverride validates, computes the 24h-bounded expiry, and (unless
// dry-run) writes the override. Returns a human-readable confirmation.
func RunCapacityOverride(ctx context.Context, req CapacityOverrideRequest, writer ScalingEventWriter, clock func() time.Time) (string, error) {
	if err := req.Validate(); err != nil {
		return "", err
	}
	if clock == nil {
		clock = time.Now
	}
	now := clock().UTC()
	ov := ScalingOverride{
		ShardHost: req.ShardHost,
		Reason:    req.Reason,
		Actor:     req.Actor,
		Hours:     req.Hours,
		CreatedAt: now,
		ExpiresAt: now.Add(time.Duration(req.Hours) * time.Hour),
	}

	if req.DryRun {
		return fmt.Sprintf(
			"capacity-override DRY-RUN — would record override for shard %q (%dh, expires %s). No row written.",
			ov.ShardHost, ov.Hours, ov.ExpiresAt.Format(time.RFC3339)), nil
	}

	if writer == nil {
		return "", fmt.Errorf("capacity-override: writer not wired")
	}
	if err := writer.WriteOverride(ctx, ov); err != nil {
		return "", fmt.Errorf("capacity-override: write: %w", err)
	}
	return fmt.Sprintf(
		"capacity-override recorded — shard %q override active for %dh (expires %s, scaling_events).",
		ov.ShardHost, ov.Hours, ov.ExpiresAt.Format(time.RFC3339)), nil
}
