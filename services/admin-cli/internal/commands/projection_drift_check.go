package commands

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
)

// allowedProjectionTables mirrors the CHECK constraint on projection_drift_state
// (contracts/migrations/per_reality/0007_drift_metadata.up.sql). `projection
// drift-check` validates --projection_name against this list BEFORE any DB work (D3)
// so an arbitrary string never reaches N per-reality queries.
var allowedProjectionTables = map[string]bool{
	"pc_projection":                  true,
	"pc_inventory_projection":        true,
	"pc_relationship_projection":     true,
	"npc_projection":                 true,
	"npc_session_memory_projection":  true,
	"npc_pc_relationship_projection": true,
	"npc_session_memory_embedding":   true,
	"region_projection":              true,
	"world_kv_projection":            true,
	"session_participants":           true,
}

// DriftRow is one reality's projection_drift_state summary for a projection table
// (read-only). projection_drift_state is per-reality (one row per table_name in each
// reality's shard DB), so a fleet read returns one DriftRow per reality.
type DriftRow struct {
	RealityID          uuid.UUID
	TableName          string
	LastVerifiedAt     *time.Time
	LastSampleSize     *int
	DriftCount         int
	LastDriftedAggID   *uuid.UUID
	LastDriftedEventID *uuid.UUID
	ExpectedNextSweep  *time.Time
	Notes              string
	UpdatedAt          time.Time
	// MissingRow is true when the shard has no projection_drift_state row for this
	// projection (ErrNoRows) — operationally distinct from a seeded-but-never-swept
	// shard (a missing row means the 0007 seed didn't run, a real anomaly).
	MissingRow bool
	// ReadErr is set when this reality's shard could not be read. Captured, not
	// fatal: one down shard must not fail a fleet-wide informational read (D1).
	ReadErr string
}

// ProjectionDriftReader returns the per-reality drift summary for one projection
// across the fleet (enumerate realities → read each shard's projection_drift_state).
// Prod impl: PgProjectionDriftReader; tests use a fake.
type ProjectionDriftReader interface {
	DriftForProjection(ctx context.Context, projectionName string) ([]DriftRow, error)
}

// RunProjectionDriftCheck validates the projection name against the schema allowlist,
// reads the maintained drift ledger fleet-wide, and formats a per-reality + aggregate
// summary. sampleSize is validated but NOT applied: projection_drift_state is a SUMMARY
// ledger (migration 0007: "DO NOT widen with sample-row payloads. Drift INVESTIGATION
// queries should be issued live ... by SRE"); live re-sampling is the integrity-checker's
// job (D-DRIFT-LIVE-RESAMPLE). Read-only — no mutation.
func RunProjectionDriftCheck(ctx context.Context, projectionName string, sampleSize int, reader ProjectionDriftReader) (string, error) {
	if reader == nil {
		return "", fmt.Errorf("projection drift-check: reader not wired")
	}
	projectionName = strings.TrimSpace(projectionName)
	if !allowedProjectionTables[projectionName] {
		return "", fmt.Errorf("projection drift-check: unknown projection %q; allowed: %s",
			projectionName, strings.Join(sortedAllowedProjections(), ", "))
	}
	if sampleSize < 1 {
		return "", fmt.Errorf("projection drift-check: sample_size must be >= 1 (got %d)", sampleSize)
	}
	rows, err := reader.DriftForProjection(ctx, projectionName)
	if err != nil {
		return "", err
	}

	var b strings.Builder
	fmt.Fprintf(&b, "projection drift-check — %s (read-only; maintained drift ledger)\n", projectionName)
	fmt.Fprintf(&b, "realities reporting: %d\n", len(rows))

	var totalDrift, drifting, neverVerified, missing, unreachable int
	for _, r := range rows {
		if r.ReadErr != "" {
			unreachable++
			fmt.Fprintf(&b, "  reality %s  UNREACHABLE: %s\n", r.RealityID, r.ReadErr)
			continue
		}
		if r.MissingRow {
			missing++
			fmt.Fprintf(&b, "  reality %s  MISSING drift row (shard not seeded by migration 0007?)\n", r.RealityID)
			continue
		}
		totalDrift += r.DriftCount
		if r.DriftCount > 0 {
			drifting++
		}
		verified := "never"
		if r.LastVerifiedAt != nil {
			verified = r.LastVerifiedAt.UTC().Format(time.RFC3339)
		} else {
			neverVerified++
		}
		fmt.Fprintf(&b, "  reality %s  drift=%d  last_verified=%s  next_sweep=%s  last_sample=%s%s%s\n",
			r.RealityID, r.DriftCount, verified, sweepStr(r.ExpectedNextSweep),
			sampleStr(r.LastSampleSize), driftDetail(r), notesDetail(r))
	}
	fmt.Fprintf(&b, "summary: total_drift=%d  drifting_realities=%d  never_verified=%d  missing_row=%d  unreachable=%d\n",
		totalDrift, drifting, neverVerified, missing, unreachable)
	fmt.Fprintf(&b, "note: --sample_size=%d not applied in v1 — this reads the maintained drift ledger; "+
		"live re-sampling is the integrity-checker's path (D-DRIFT-LIVE-RESAMPLE).\n", sampleSize)
	return b.String(), nil
}

func sortedAllowedProjections() []string {
	out := make([]string, 0, len(allowedProjectionTables))
	for k := range allowedProjectionTables {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func sampleStr(n *int) string {
	if n == nil {
		return "n/a"
	}
	return fmt.Sprintf("%d", *n)
}

// sweepStr renders the expected_next_sweep_at staleness signal (migration 0007:
// "if NOW() > expected_next_sweep_at + grace, alert STALE_VERIFICATION").
func sweepStr(t *time.Time) string {
	if t == nil {
		return "n/a"
	}
	return t.UTC().Format(time.RFC3339)
}

// notesDetail appends the shard's free-form drift note (e.g. "skipped — pgvector ext
// missing") when present, so SRE context recorded by the integrity-checker surfaces.
func notesDetail(r DriftRow) string {
	if strings.TrimSpace(r.Notes) == "" {
		return ""
	}
	return fmt.Sprintf("  note=%q", r.Notes)
}

func driftDetail(r DriftRow) string {
	if r.DriftCount == 0 || r.LastDriftedAggID == nil {
		return ""
	}
	return fmt.Sprintf("  [last_drifted_aggregate=%s]", r.LastDriftedAggID)
}
