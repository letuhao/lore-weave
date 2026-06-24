package commands

import (
	"context"
	"os"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeDriftReader struct {
	rows []DriftRow
	err  error
}

func (f fakeDriftReader) DriftForProjection(_ context.Context, _ string) ([]DriftRow, error) {
	return f.rows, f.err
}

func TestRunProjectionDriftCheck_RejectsUnknownProjection(t *testing.T) {
	_, err := RunProjectionDriftCheck(context.Background(), "not_a_real_table", 100, fakeDriftReader{})
	if err == nil || !strings.Contains(err.Error(), "unknown projection") {
		t.Fatalf("want unknown-projection error, got %v", err)
	}
	// The error must list the allowlist so the operator can self-correct.
	if !strings.Contains(err.Error(), "pc_projection") {
		t.Errorf("error should list allowed projections: %v", err)
	}
}

func TestRunProjectionDriftCheck_RejectsBadSampleSize(t *testing.T) {
	_, err := RunProjectionDriftCheck(context.Background(), "pc_projection", 0, fakeDriftReader{})
	if err == nil || !strings.Contains(err.Error(), "sample_size must be >= 1") {
		t.Fatalf("want sample_size error, got %v", err)
	}
}

func TestRunProjectionDriftCheck_NilReader(t *testing.T) {
	_, err := RunProjectionDriftCheck(context.Background(), "pc_projection", 100, nil)
	if err == nil || !strings.Contains(err.Error(), "not wired") {
		t.Fatalf("want not-wired error, got %v", err)
	}
}

func TestRunProjectionDriftCheck_FleetAggregate(t *testing.T) {
	verified := time.Date(2026, 5, 30, 12, 0, 0, 0, time.UTC)
	nextSweep := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	agg := uuid.New()
	rows := []DriftRow{
		{RealityID: uuid.New(), TableName: "pc_projection", DriftCount: 3, LastVerifiedAt: &verified, ExpectedNextSweep: &nextSweep, LastDriftedAggID: &agg, LastSampleSize: intPtr(100), Notes: "pgvector skipped"},
		{RealityID: uuid.New(), TableName: "pc_projection", DriftCount: 0, LastVerifiedAt: &verified},
		{RealityID: uuid.New(), TableName: "pc_projection"},                   // never verified
		{RealityID: uuid.New(), TableName: "pc_projection", MissingRow: true}, // shard not seeded
		{RealityID: uuid.New(), TableName: "pc_projection", ReadErr: "dial timeout"},
	}
	out, err := RunProjectionDriftCheck(context.Background(), "pc_projection", 100, fakeDriftReader{rows: rows})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, want := range []string{
		"realities reporting: 5",
		"total_drift=3",
		"drifting_realities=1",
		"never_verified=1",
		"missing_row=1",
		"unreachable=1",
		"UNREACHABLE: dial timeout",
		"MISSING drift row",
		"next_sweep=" + nextSweep.Format(time.RFC3339), // staleness signal rendered, not dropped
		"last_drifted_aggregate=" + agg.String(),
		`note="pgvector skipped"`,       // DB free-form note surfaced
		"--sample_size=100 not applied", // honest-status: documented, not silent
	} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q\n---\n%s", want, out)
		}
	}
}

func TestRunProjectionDriftCheck_SampleSizeEchoIsNotConstant(t *testing.T) {
	// Proves the "not applied" note echoes the CALLER's value, not a hardcoded 100 —
	// closing the honest-status loop (a constant 100 would pass the FleetAggregate test).
	out, err := RunProjectionDriftCheck(context.Background(), "pc_projection", 37, fakeDriftReader{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "--sample_size=37 not applied") {
		t.Errorf("output should echo the caller's sample_size (37), got:\n%s", out)
	}
}

func TestRunProjectionDriftCheck_EmptyFleet(t *testing.T) {
	out, err := RunProjectionDriftCheck(context.Background(), "world_kv_projection", 100, fakeDriftReader{rows: nil})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "realities reporting: 0") || !strings.Contains(out, "total_drift=0") {
		t.Errorf("empty-fleet output unexpected:\n%s", out)
	}
}

func intPtr(n int) *int { return &n }

// TestAllowlist_MatchesMigrationCheck is the drift tripwire D3 lacked: the Go
// allowedProjectionTables map is a hand-copy of the CHECK constraint in migration
// 0007, whose own comment says "New tables added in L4+ MUST extend this CHECK". This
// parses the table_name IN (...) list out of the migration and asserts set-equality,
// so the next time the CHECK grows, this fails and points at the Go copy.
func TestAllowlist_MatchesMigrationCheck(t *testing.T) {
	const mig = "../../../../contracts/migrations/per_reality/0007_drift_metadata.up.sql"
	src, err := os.ReadFile(mig)
	if err != nil {
		t.Fatalf("read migration %s: %v", mig, err)
	}
	block := regexp.MustCompile(`(?s)table_name IN \((.*?)\)`).FindStringSubmatch(string(src))
	if block == nil {
		t.Fatalf("could not find `table_name IN (...)` CHECK in %s", mig)
	}
	got := map[string]bool{}
	for _, m := range regexp.MustCompile(`'([a-z_]+)'`).FindAllStringSubmatch(block[1], -1) {
		got[m[1]] = true
	}
	if len(got) == 0 {
		t.Fatalf("parsed 0 table names from the CHECK block")
	}
	for k := range allowedProjectionTables {
		if !got[k] {
			t.Errorf("allowlist has %q but migration CHECK does not", k)
		}
	}
	for k := range got {
		if !allowedProjectionTables[k] {
			t.Errorf("migration CHECK has %q but allowedProjectionTables does not — extend the Go map", k)
		}
	}
}
