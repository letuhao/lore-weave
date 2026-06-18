package commands

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

type fakeMigReader struct {
	rows []MigrationStatusRow
	err  error
}

func (f fakeMigReader) ListMigrationStatus(_ context.Context) ([]MigrationStatusRow, error) {
	return f.rows, f.err
}

func TestRunMigrationStatus_PerReality(t *testing.T) {
	at := time.Date(2026, 5, 31, 12, 0, 0, 0, time.UTC)
	r := fakeMigReader{rows: []MigrationStatusRow{
		{RealityID: uuid.New(), Applied: 12, Failures: 0, LatestMigration: "012_x", LatestAppliedAt: at},
		{RealityID: uuid.New(), Applied: 11, Failures: 1, LatestMigration: "011_y", LatestAppliedAt: at},
	}}
	out, err := RunMigrationStatus(context.Background(), "all", r)
	if err != nil {
		t.Fatalf("RunMigrationStatus: %v", err)
	}
	for _, want := range []string{"scope=all", "12 applied", "latest=012_x", "FAILED", "2 realities, 1 total failures"} {
		if !strings.Contains(out, want) {
			t.Errorf("output missing %q:\n%s", want, out)
		}
	}
}

func TestRunMigrationStatus_MetaScopeNoData(t *testing.T) {
	// scope=meta must NOT silently return empty — it explains meta isn't tracked here.
	out, err := RunMigrationStatus(context.Background(), "meta", fakeMigReader{})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if !strings.Contains(out, "not yet wired") && !strings.Contains(out, "not recorded") {
		t.Errorf("scope=meta must explain it isn't tracked:\n%s", out)
	}
}

func TestRunMigrationStatus_Empty(t *testing.T) {
	out, _ := RunMigrationStatus(context.Background(), "all", fakeMigReader{rows: nil})
	if !strings.Contains(out, "no per-reality migrations recorded") {
		t.Errorf("empty must be reported clearly:\n%s", out)
	}
}

func TestRunMigrationStatus_InvalidScope(t *testing.T) {
	if _, err := RunMigrationStatus(context.Background(), "bogus", fakeMigReader{}); err == nil {
		t.Fatal("invalid scope must error")
	}
}

func TestRunMigrationStatus_ReaderError(t *testing.T) {
	if _, err := RunMigrationStatus(context.Background(), "all", fakeMigReader{err: errors.New("db down")}); err == nil {
		t.Fatal("reader error must propagate")
	}
}

func TestRunMigrationStatus_NilReader(t *testing.T) {
	if _, err := RunMigrationStatus(context.Background(), "all", nil); err == nil {
		t.Fatal("nil reader must error")
	}
}
