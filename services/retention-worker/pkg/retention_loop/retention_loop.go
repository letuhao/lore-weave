// Package retention_loop is the retention-worker's per-reality orchestrator.
// One Run() iteration per reality per scheduling tick. Flow:
//
//   1. outbox_pruner.PruneReality — DELETE published+old rows from events_outbox
//   2. audit_invoker.InvokeReality — exec scripts/event-audit-retention-cron.sh
//   3. snapshot_pruner.PruneReality — V1 no-op; L3 cycle 12+ implements
//
// L1.J degraded-mode gating: at ModeEssentials+ the loop PAUSES (retention
// is background work; we'd rather grow tables than risk DELETE-storming a
// stressed DB).
package retention_loop

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/retention-worker/pkg/audit_invoker"
	"github.com/loreweave/foundation/services/retention-worker/pkg/outbox_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/snapshot_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

// ModeReader exposes ServiceMode for L1.J degraded-mode gating.
type ModeReader interface {
	Mode() lifecycle.ServiceMode
}

// DSNLookup maps reality_id → per-reality Postgres DSN. Production binds
// to the reality_registry table; tests inject a map.
type DSNLookup interface {
	Lookup(ctx context.Context, realityID uuid.UUID) (string, error)
}

// Config is the constructor input.
type Config struct {
	OutboxPruner   *outbox_pruner.Pruner
	AuditInvoker   *audit_invoker.Invoker
	SnapshotPruner *snapshot_pruner.Pruner
	DSNLookup      DSNLookup
	Mode           ModeReader
}

// Loop is the orchestrator.
type Loop struct {
	outbox   *outbox_pruner.Pruner
	audit    *audit_invoker.Invoker
	snapshot *snapshot_pruner.Pruner
	dsn      DSNLookup
	mode     ModeReader
}

// New constructs a Loop.
func New(c Config) (*Loop, error) {
	if c.OutboxPruner == nil {
		return nil, errors.New("retention_loop: OutboxPruner nil")
	}
	if c.AuditInvoker == nil {
		return nil, errors.New("retention_loop: AuditInvoker nil")
	}
	if c.SnapshotPruner == nil {
		return nil, errors.New("retention_loop: SnapshotPruner nil")
	}
	if c.DSNLookup == nil {
		return nil, errors.New("retention_loop: DSNLookup nil")
	}
	if c.Mode == nil {
		return nil, errors.New("retention_loop: Mode nil")
	}
	return &Loop{
		outbox:   c.OutboxPruner,
		audit:    c.AuditInvoker,
		snapshot: c.SnapshotPruner,
		dsn:      c.DSNLookup,
		mode:     c.Mode,
	}, nil
}

// IterationStats is the per-Run summary.
type IterationStats struct {
	RealityID  uuid.UUID
	Outbox     types.OutboxPruneStats
	Audit      types.AuditPruneStats
	Skipped    bool
	SkipReason string
}

// Run executes ONE retention iteration for the given reality. Skips entirely
// when mode >= ModeEssentials.
func (l *Loop) Run(ctx context.Context, realityID uuid.UUID) (IterationStats, error) {
	stats := IterationStats{RealityID: realityID}

	if l.mode.Mode() >= lifecycle.ModeEssentials {
		stats.Skipped = true
		stats.SkipReason = fmt.Sprintf("degraded_mode=%s", l.mode.Mode())
		return stats, nil
	}

	// 1. outbox prune (addresses D-OUTBOX-PRUNE row 055)
	op, err := l.outbox.PruneReality(ctx, realityID)
	if err != nil {
		return stats, fmt.Errorf("retention_loop: outbox prune reality=%s: %w", realityID, err)
	}
	stats.Outbox = op

	// 2. audit retention (wraps scripts/event-audit-retention-cron.sh)
	dsn, err := l.dsn.Lookup(ctx, realityID)
	if err != nil {
		return stats, fmt.Errorf("retention_loop: dsn lookup reality=%s: %w", realityID, err)
	}
	ap, err := l.audit.InvokeReality(ctx, realityID, dsn)
	if err != nil {
		return stats, fmt.Errorf("retention_loop: audit invoke reality=%s: %w", realityID, err)
	}
	stats.Audit = ap

	// 3. snapshot prune (V1 no-op; L3 cycle 12+)
	if _, err := l.snapshot.PruneReality(ctx, realityID); err != nil {
		return stats, fmt.Errorf("retention_loop: snapshot prune reality=%s: %w", realityID, err)
	}

	return stats, nil
}

// MapDSNLookup is a test-fake DSNLookup.
type MapDSNLookup struct {
	M map[uuid.UUID]string
}

// Lookup returns the map entry or empty + error.
func (m *MapDSNLookup) Lookup(_ context.Context, realityID uuid.UUID) (string, error) {
	if dsn, ok := m.M[realityID]; ok {
		return dsn, nil
	}
	return "", fmt.Errorf("MapDSNLookup: no DSN for reality %s", realityID)
}
