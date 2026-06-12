package tasks

import (
	"context"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/worker-infra/internal/config"
)

type OutboxCleanup struct {
	Sources     []config.OutboxSource
	SourcePools map[string]*pgxpool.Pool
	RetainDays  int
}

func (t *OutboxCleanup) Name() string { return "outbox-cleanup" }

func (t *OutboxCleanup) Run(ctx context.Context) error {
	slog.Info("outbox-cleanup starting", "retain_days", t.RetainDays)

	// Run once immediately, then daily
	t.cleanup(ctx)

	ticker := time.NewTicker(24 * time.Hour)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			slog.Info("outbox-cleanup shutting down")
			return nil
		case <-ticker.C:
			t.cleanup(ctx)
		}
	}
}

func (t *OutboxCleanup) cleanup(ctx context.Context) {
	for _, src := range t.Sources {
		pool, ok := t.SourcePools[src.Name]
		if !ok {
			continue
		}
		// make_interval(days => $1) binds RetainDays as an INT directly. The old
		// ($1 || ' days')::interval forced $1 to TEXT, which pgx v5 refuses to
		// encode from an int ("cannot find encode plan") — so cleanup errored on
		// every run and never purged a row (D-OUTBOX-CLEANUP-ENCODE).
		tag, err := pool.Exec(ctx, `
DELETE FROM outbox_events
WHERE published_at IS NOT NULL AND published_at < now() - make_interval(days => $1)
`, t.RetainDays)
		if err != nil {
			slog.Error("outbox-cleanup error", "source", src.Name, "error", err)
			continue
		}
		if tag.RowsAffected() > 0 {
			slog.Info("outbox-cleanup cleaned events", "source", src.Name, "count", tag.RowsAffected())
		}
	}
}
