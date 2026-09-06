package commands

import (
	"context"
	"os"
	"path/filepath"
	"regexp"
	"sort"
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
	if !strings.Contains(err.Error(), "canon_projection") {
		t.Errorf("error should list allowed projections: %v", err)
	}
}

func TestRunProjectionDriftCheck_RejectsBadSampleSize(t *testing.T) {
	_, err := RunProjectionDriftCheck(context.Background(), "canon_projection", 0, fakeDriftReader{})
	if err == nil || !strings.Contains(err.Error(), "sample_size must be >= 1") {
		t.Fatalf("want sample_size error, got %v", err)
	}
}

func TestRunProjectionDriftCheck_NilReader(t *testing.T) {
	_, err := RunProjectionDriftCheck(context.Background(), "canon_projection", 100, nil)
	if err == nil || !strings.Contains(err.Error(), "not wired") {
		t.Fatalf("want not-wired error, got %v", err)
	}
}

func TestRunProjectionDriftCheck_FleetAggregate(t *testing.T) {
	verified := time.Date(2026, 5, 30, 12, 0, 0, 0, time.UTC)
	nextSweep := time.Date(2026, 6, 2, 12, 0, 0, 0, time.UTC)
	agg := uuid.New()
	rows := []DriftRow{
		{RealityID: uuid.New(), TableName: "canon_projection", DriftCount: 3, LastVerifiedAt: &verified, ExpectedNextSweep: &nextSweep, LastDriftedAggID: &agg, LastSampleSize: intPtr(100), Notes: "pgvector skipped"},
		{RealityID: uuid.New(), TableName: "canon_projection", DriftCount: 0, LastVerifiedAt: &verified},
		{RealityID: uuid.New(), TableName: "canon_projection"},                   // never verified
		{RealityID: uuid.New(), TableName: "canon_projection", MissingRow: true}, // shard not seeded
		{RealityID: uuid.New(), TableName: "canon_projection", ReadErr: "dial timeout"},
	}
	out, err := RunProjectionDriftCheck(context.Background(), "canon_projection", 100, fakeDriftReader{rows: rows})
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
	out, err := RunProjectionDriftCheck(context.Background(), "canon_projection", 37, fakeDriftReader{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "--sample_size=37 not applied") {
		t.Errorf("output should echo the caller's sample_size (37), got:\n%s", out)
	}
}

func TestRunProjectionDriftCheck_EmptyFleet(t *testing.T) {
	out, err := RunProjectionDriftCheck(context.Background(), "canon_projection", 100, fakeDriftReader{rows: nil})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(out, "realities reporting: 0") || !strings.Contains(out, "total_drift=0") {
		t.Errorf("empty-fleet output unexpected:\n%s", out)
	}
}

func intPtr(n int) *int { return &n }

// TestAllowlist_MatchesMigrationCheck is the drift tripwire D3 lacked: the Go
// allowedProjectionTables map is a hand-copy of the projection_drift_state CHECK
// constraint, so this parses the constraint out of the migrations and asserts
// set-equality.
//
// **It read ONE FILE until 2026-08-04, and that is why it did not fire.** The
// original pinned `0007_drift_metadata.up.sql` and its comment anticipated only
// growth — "the next time the CHECK GROWS, this fails". `0017` SHRANK the same
// constraint, from a different file, and this test went on comparing the Go map
// against 0007's ten names: it stayed green while the map it guards named seven
// tables the database no longer had. A tripwire pinned to one file cannot see a
// later file redefine its subject.
//
// So it now derives the EFFECTIVE constraint: walk every per_reality up-migration
// in filename order and keep the LAST `ADD CONSTRAINT
// projection_drift_table_name_allowlist ... CHECK (table_name IN (...))`, which
// is what Postgres would be left holding. It must also anchor on ADD CONSTRAINT
// rather than on `table_name IN (` alone — 0017 contains a `DELETE FROM
// projection_drift_state WHERE table_name IN (<the seven dropped names>)`, and a
// looser pattern happily parses that instead and asserts the exact opposite of
// the truth.
func TestAllowlist_MatchesMigrationCheck(t *testing.T) {
	const dir = "../../../../contracts/migrations/per_reality"
	files, err := filepath.Glob(filepath.Join(dir, "*.up.sql"))
	if err != nil || len(files) == 0 {
		t.Fatalf("glob %s: %v (found %d)", dir, err, len(files))
	}
	sort.Strings(files) // migration order == filename order (0001..NNNN)

	// Anchored on the constraint NAME, so an unrelated `table_name IN (...)`
	// elsewhere in the same file cannot be mistaken for the constraint.
	constraintRe := regexp.MustCompile(
		`(?s)ADD CONSTRAINT projection_drift_table_name_allowlist\s+CHECK \(table_name IN \((.*?)\)\s*\)`)

	effective, from := "", ""
	for _, f := range files {
		src, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if ms := constraintRe.FindAllStringSubmatch(string(src), -1); len(ms) > 0 {
			effective = ms[len(ms)-1][1] // last one in this file wins
			from = filepath.Base(f)
		}
	}
	if effective == "" {
		t.Fatal("no ADD CONSTRAINT projection_drift_table_name_allowlist found in any " +
			"per_reality migration — the tripwire has lost its subject, which is a failure, " +
			"not a pass")
	}

	got := map[string]bool{}
	for _, m := range regexp.MustCompile(`'([a-z_]+)'`).FindAllStringSubmatch(effective, -1) {
		got[m[1]] = true
	}
	if len(got) == 0 {
		t.Fatalf("parsed 0 table names from the effective CHECK (%s)", from)
	}
	for k := range allowedProjectionTables {
		if !got[k] {
			t.Errorf("allowlist has %q but the effective CHECK (%s) does not", k, from)
		}
	}
	for k := range got {
		if !allowedProjectionTables[k] {
			t.Errorf("the effective CHECK (%s) has %q but allowedProjectionTables does not — "+
				"extend the Go map", from, k)
		}
	}
}
