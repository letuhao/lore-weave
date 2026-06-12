package commands

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
)

// MigrationStatusRow is the per-reality migration summary derived from the
// central meta table instance_schema_migrations (the orchestrator records every
// per-reality migration application there).
type MigrationStatusRow struct {
	RealityID       uuid.UUID
	Applied         int
	Failures        int
	LatestMigration string
	LatestAppliedAt time.Time
}

// MigrationStatusReader lists the per-reality migration summary. Prod impl is
// PgMigrationStatusReader; tests use a fake.
type MigrationStatusReader interface {
	ListMigrationStatus(ctx context.Context) ([]MigrationStatusRow, error)
}

// RunMigrationStatus reports per-reality migration state (tier-3 informational,
// read-only). scope ∈ {meta, per-reality, all} (default all/per-reality).
//
// Honest scope note: instance_schema_migrations tracks per-REALITY (instance)
// migrations only. The meta DB's own migrations (001-029) are applied at
// bootstrap and are NOT recorded in this table, so scope=meta has no rows here
// (reported explicitly rather than silently returning empty).
func RunMigrationStatus(ctx context.Context, scope string, reader MigrationStatusReader) (string, error) {
	if reader == nil {
		return "", fmt.Errorf("migration status: reader not wired")
	}
	scope = strings.TrimSpace(strings.ToLower(scope))
	if scope == "" {
		scope = "all"
	}
	if scope != "meta" && scope != "per-reality" && scope != "all" {
		return "", fmt.Errorf("migration status: invalid scope %q (want meta|per-reality|all)", scope)
	}

	var b strings.Builder
	fmt.Fprintf(&b, "migration status — scope=%s (read-only)\n", scope)
	if scope == "meta" {
		// The meta DB's own migrations are not tracked in instance_schema_migrations.
		fmt.Fprintln(&b, "  meta-DB migrations are applied at bootstrap and not recorded in")
		fmt.Fprintln(&b, "  instance_schema_migrations; per-DB meta tracking is not yet wired.")
		return b.String(), nil
	}

	rows, err := reader.ListMigrationStatus(ctx)
	if err != nil {
		return "", err
	}
	if len(rows) == 0 {
		fmt.Fprintln(&b, "  no per-reality migrations recorded yet.")
		return b.String(), nil
	}
	sort.SliceStable(rows, func(i, j int) bool { return rows[i].RealityID.String() < rows[j].RealityID.String() })
	totalFailures := 0
	for _, r := range rows {
		totalFailures += r.Failures
		flag := ""
		if r.Failures > 0 {
			flag = fmt.Sprintf("  ⚠ %d FAILED", r.Failures)
		}
		fmt.Fprintf(&b, "  reality %s: %d applied, latest=%s @ %s%s\n",
			r.RealityID, r.Applied, r.LatestMigration, r.LatestAppliedAt.UTC().Format(time.RFC3339), flag)
	}
	fmt.Fprintf(&b, "  — %d realities, %d total failures\n", len(rows), totalFailures)
	return b.String(), nil
}
