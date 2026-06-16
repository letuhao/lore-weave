// Package types holds the shared value types crossed between
// live / comparator / state_writer / full_check / metrics.
//
// Kept in its own package so sub-packages can depend on it without forming
// import cycles (matches services/archive-worker/pkg/types and
// services/retention-worker/pkg/types layout).
package types

import (
	"time"

	"github.com/google/uuid"
)

// L3ATables is the canonical allowlist of the 10 L3.A projection tables.
// This MUST match the projection_drift_table_name_allowlist CHECK in
// contracts/migrations/per_reality/0007_drift_metadata.up.sql.
//
// The list is exported so sampler + state_writer can both iterate it from
// the same source of truth. If a new projection table lands in L4+, BOTH
// this slice AND the migration's CHECK constraint MUST be extended.
var L3ATables = []string{
	"pc_projection",
	"pc_inventory_projection",
	"pc_relationship_projection",
	"npc_projection",
	"npc_session_memory_projection",
	"npc_pc_relationship_projection",
	"npc_session_memory_embedding",
	"region_projection",
	"world_kv_projection",
	"session_participants",
}

// TableConfig describes the integrity-check budget for one projection
// table. Loaded from contracts/integrity/config.yaml at startup.
type TableConfig struct {
	// TableName MUST be one of L3ATables (validated at config load).
	TableName string
	// SampleSize for daily mode (L3.E). Cycle-15 default: 20.
	// Monthly mode (L3.F) ignores this field and scans ALL rows.
	SampleSize int
	// FullScanBatchSize for monthly mode (L3.F). Cycle-15 default: 500.
	// Cursor-paginates the full table to avoid any single SELECT holding
	// a long lock on the projection table.
	FullScanBatchSize int
}

// DriftReport is the per-table summary the state_writer turns into a
// projection_drift_state UPDATE.
type DriftReport struct {
	RealityID  uuid.UUID
	TableName  string
	SampleSize int
	DriftCount int
	Skipped    int
	// LastDriftedAggregateID populated when DriftCount > 0; convenience
	// pointer for SRE investigation. NULL/uuid.Nil when DriftCount = 0.
	LastDriftedAggregateID uuid.UUID
	LastDriftedEventID     uuid.UUID
	CheckedAt              time.Time
	// CheckMode = "daily" or "monthly" — written to the `notes` field of
	// projection_drift_state so SRE can tell which sweep produced the row.
	CheckMode string
	// DurationSeconds for the metrics emitter (lw_projection_check_duration_seconds).
	DurationSeconds float64
	// LagSeconds = NOW() − max(applied_at) over the table (the freshness of the
	// most-recent projection write), for lw_projection_lag_seconds. Only valid
	// when HasLag is true (an empty table has no applied_at → no lag to report).
	LagSeconds float64
	HasLag     bool
}

// CheckMode is the enum for daily vs monthly. The same binary runs both;
// the choice is config-driven (contracts/integrity/config.yaml `mode:`).
type CheckMode string

const (
	// CheckModeDaily samples N random aggregates per table (L3.E).
	CheckModeDaily CheckMode = "daily"
	// CheckModeMonthly walks ALL aggregates per table via cursor batching (L3.F).
	CheckModeMonthly CheckMode = "monthly"
)

// IsValid reports whether the mode is one of the two known values.
func (m CheckMode) IsValid() bool {
	return m == CheckModeDaily || m == CheckModeMonthly
}
