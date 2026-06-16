// Package audit_invoker is the retention-worker's wrapper around the
// already-shipped scripts/event-audit-retention-cron.sh script (cycle 9 / L2.B.3).
//
// Why wrap a shell script instead of porting the SQL to Go?
//   * The script is already battle-tested + dry-run-supported.
//   * Per-class retention policy (30d non-flagged / 90d flagged) is the
//     authority — re-implementing it in Go would create a drift surface.
//   * The script's partition-drop optimization (drop whole monthly
//     partitions whose upper bound is < cutoff) is tricky to get right
//     without psql introspection — keep one impl.
//
// The retention-worker schedules a per-reality invocation; each invocation
// passes the reality's PGURI as `--db`. Tests inject a `ScriptRunner` fake.
package audit_invoker

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

// ScriptRunner is the IO boundary. Production impl shells out via os/exec
// to `bash scripts/event-audit-retention-cron.sh --db <dsn> --batch-size N`.
// Tests substitute an in-mem recorder.
type ScriptRunner interface {
	// Run invokes the audit-retention script. Returns parsed counters
	// (NonFlaggedDeleted, FlaggedDeleted, PartitionsDropped) from the
	// script's stdout. The script exits 0 on success, non-zero on
	// failure; non-zero MUST be surfaced as an error.
	Run(ctx context.Context, realityID uuid.UUID, dsn string, batchSize int, nonFlaggedDays int, flaggedDays int) (types.AuditPruneStats, error)
}

// Invoker is the per-reality runner.
type Invoker struct {
	runner ScriptRunner
	cfg    types.RetentionConfig
}

// New constructs an Invoker.
func New(runner ScriptRunner, cfg types.RetentionConfig) (*Invoker, error) {
	if runner == nil {
		return nil, errors.New("audit_invoker: ScriptRunner nil")
	}
	if cfg.AuditNonFlaggedDays <= 0 {
		cfg.AuditNonFlaggedDays = 30
	}
	if cfg.AuditFlaggedDays <= 0 {
		cfg.AuditFlaggedDays = 90
	}
	if cfg.OutboxBatchSize <= 0 {
		cfg.OutboxBatchSize = 10000
	}
	return &Invoker{runner: runner, cfg: cfg}, nil
}

// InvokeReality runs the script for the given reality's DSN.
func (i *Invoker) InvokeReality(ctx context.Context, realityID uuid.UUID, dsn string) (types.AuditPruneStats, error) {
	if dsn == "" {
		return types.AuditPruneStats{}, fmt.Errorf("audit_invoker: empty DSN for reality %s", realityID)
	}
	return i.runner.Run(ctx, realityID, dsn,
		i.cfg.OutboxBatchSize, i.cfg.AuditNonFlaggedDays, i.cfg.AuditFlaggedDays)
}

// MockRunner records invocations for tests.
type MockRunner struct {
	Calls []MockCall
	// Per-reality outcomes (defaults to zero-row prune if not set).
	Outcomes map[uuid.UUID]types.AuditPruneStats
	Err      error
}

// MockCall captures one Run invocation.
type MockCall struct {
	RealityID       uuid.UUID
	DSN             string
	BatchSize       int
	NonFlaggedDays  int
	FlaggedDays     int
}

// NewMockRunner returns an empty mock.
func NewMockRunner() *MockRunner {
	return &MockRunner{Outcomes: map[uuid.UUID]types.AuditPruneStats{}}
}

// Run records the call + returns the configured outcome.
func (m *MockRunner) Run(_ context.Context, realityID uuid.UUID, dsn string, batchSize, nonFlaggedDays, flaggedDays int) (types.AuditPruneStats, error) {
	m.Calls = append(m.Calls, MockCall{
		RealityID:      realityID,
		DSN:            dsn,
		BatchSize:      batchSize,
		NonFlaggedDays: nonFlaggedDays,
		FlaggedDays:    flaggedDays,
	})
	if m.Err != nil {
		return types.AuditPruneStats{}, m.Err
	}
	out, ok := m.Outcomes[realityID]
	if !ok {
		out = types.AuditPruneStats{RealityID: realityID}
	}
	return out, nil
}
