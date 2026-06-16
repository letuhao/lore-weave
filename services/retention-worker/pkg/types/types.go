// Package types holds shared data shapes used across the retention-worker's
// internal packages.
package types

import (
	"time"

	"github.com/google/uuid"
)

// OutboxPruneStats is the per-reality pruner outcome. Used for metrics +
// integration-test assertions.
type OutboxPruneStats struct {
	RealityID    uuid.UUID
	Scanned      int64
	Deleted      int64
	DeadLetterSkipped int64
	PendingSkipped    int64
}

// AuditPruneStats is the per-reality audit-script outcome.
type AuditPruneStats struct {
	RealityID         uuid.UUID
	PartitionsDropped int64
	NonFlaggedDeleted int64
	FlaggedDeleted    int64
}

// RetentionConfig is the worker's runtime config (loaded from
// contracts/retention/event_classes.yaml in production wiring).
type RetentionConfig struct {
	// OutboxPublishedGrace — how long after a row is marked published=TRUE
	// before it's eligible for deletion. Default 24h.
	OutboxPublishedGrace time.Duration
	// OutboxBatchSize — max rows per DELETE statement to keep TX small.
	// Default 10000.
	OutboxBatchSize int
	// AuditNonFlaggedDays — 30d default per R01 §12A.3.
	AuditNonFlaggedDays int
	// AuditFlaggedDays — 90d default per R01 §12A.3.
	AuditFlaggedDays int
}

// DefaultConfig returns the V1 defaults.
func DefaultConfig() RetentionConfig {
	return RetentionConfig{
		OutboxPublishedGrace: 24 * time.Hour,
		OutboxBatchSize:      10000,
		AuditNonFlaggedDays:  30,
		AuditFlaggedDays:     90,
	}
}
