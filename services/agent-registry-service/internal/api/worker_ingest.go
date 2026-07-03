package api

import (
	"context"
	"log/slog"
	"time"

	"github.com/google/uuid"
)

// ── P5 REG-P5-03 scheduled ingest worker (clears D-REG-P5-INGEST-SCHEDULED-WORKER
// + D-REG-P3-SCHEDULED-RESCAN) ───────────────────────────────────────────────
//
// A background loop (OFF by default) that keeps the ingested System catalog honest
// against a moving upstream. Each tick:
//   1. re-pull the official registry (refreshes descriptions + surfaces new servers),
//   2. denylist / retroactive-removal sync: an approved server the registry has
//      REMOVED is suspended (dropped from federation) + its queue row marked
//      revoked_upstream (§7b#1) — verification ≠ safety: a rug-pulled/removed server
//      must stop serving,
//   3. rug-pull rescan: re-run the P3 supply-chain scan on every ingested System
//      server so a clean-at-approval server that later serves poisoned tools flips to
//      suspended (§7b#2).
// All best-effort + logged; a failure never crashes the loop.

const minIngestIntervalSeconds = 300

// StartIngestWorker launches the loop iff cfg.IngestWorker is set. No-op otherwise
// (default off), so a dev/test boot never hits the network on a timer.
func (s *Server) StartIngestWorker(ctx context.Context) {
	if !s.cfg.IngestWorker {
		return
	}
	interval := s.cfg.IngestIntervalSeconds
	if interval < minIngestIntervalSeconds {
		interval = minIngestIntervalSeconds
	}
	ticker := time.NewTicker(time.Duration(interval) * time.Second)
	slog.Info("ingest worker started", "interval_s", interval)
	go func() {
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				s.runIngestCycle(ctx)
			}
		}
	}()
}

// runIngestCycle is one maintenance pass. Exported-for-test via the same package.
func (s *Server) runIngestCycle(ctx context.Context) {
	if s.db == nil {
		return
	}
	pullStart := time.Now().UTC()
	counts, err := s.pullOfficialRegistry(ctx)
	if err != nil {
		slog.Warn("ingest worker: pull failed", "err", err.Error())
	} else {
		slog.Info("ingest worker: pulled", "fetched", counts.Fetched, "new", counts.New,
			"updated", counts.Updated, "truncated", counts.Truncated)
		// Denylist sync is only sound on a COMPLETE pull — a truncated pull didn't see
		// every page, so an unseen-but-present server would be falsely "removed".
		if !counts.Truncated {
			s.denylistSync(ctx, pullStart)
		}
	}
	s.rescanIngestedSystem(ctx)
}

// denylistSync suspends every approved ingested server the just-completed pull did
// NOT refresh (its queue row's updated_at stayed < pullStart because the upsert never
// touched it → absent upstream). The linked System server is suspended (dropped from
// federation) and the queue row marked revoked_upstream. Audited.
func (s *Server) denylistSync(ctx context.Context, pullStart time.Time) {
	rows, err := s.db.Query(ctx,
		`SELECT ingest_id, name, approved_server_id FROM registry_ingest_queue
		 WHERE source='official' AND status='approved' AND approved_server_id IS NOT NULL
		   AND updated_at < $1`, pullStart)
	if err != nil {
		slog.Warn("ingest worker: denylist query failed", "err", err.Error())
		return
	}
	type revoked struct {
		ingestID uuid.UUID
		name     string
		serverID uuid.UUID
	}
	var toRevoke []revoked
	for rows.Next() {
		var r revoked
		if err := rows.Scan(&r.ingestID, &r.name, &r.serverID); err == nil {
			toRevoke = append(toRevoke, r)
		}
	}
	rows.Close()

	for _, r := range toRevoke {
		// Suspend the federated server (drop it) if not already suspended.
		_, _ = s.db.Exec(ctx,
			`UPDATE mcp_server_registrations SET status='suspended', updated_at=now()
			 WHERE mcp_server_id=$1 AND status <> 'suspended'`, r.serverID)
		_, _ = s.db.Exec(ctx,
			`UPDATE registry_ingest_queue SET status='revoked_upstream', updated_at=now()
			 WHERE ingest_id=$1`, r.ingestID)
		s.audit(ctx, uuid.Nil, "system", "registry_ingest", "revoke_upstream", &r.ingestID, r.name, "system",
			map[string]any{"mcp_server_id": r.serverID.String(), "reason": "absent from upstream registry"})
	}
	if len(toRevoke) > 0 {
		s.bumpCatalogVersion(ctx)
		slog.Info("ingest worker: revoked upstream-removed servers", "count", len(toRevoke))
	}
}

// rescanIngestedSystem re-runs the P3 supply-chain scan on every ingested System
// server (the rug-pull guard). runScan drives the status machine: clean→active,
// probe-fail→error, HIGH finding→suspended.
func (s *Server) rescanIngestedSystem(ctx context.Context) {
	rows, err := s.db.Query(ctx,
		`SELECT DISTINCT approved_server_id FROM registry_ingest_queue
		 WHERE status='approved' AND approved_server_id IS NOT NULL`)
	if err != nil {
		slog.Warn("ingest worker: rescan query failed", "err", err.Error())
		return
	}
	var ids []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err == nil {
			ids = append(ids, id)
		}
	}
	rows.Close()
	for _, id := range ids {
		if _, _, _, err := s.runScan(ctx, id); err != nil {
			slog.Debug("ingest worker: rescan probe failed", "server", id.String(), "err", err.Error())
		}
	}
	if len(ids) > 0 {
		slog.Info("ingest worker: rescanned ingested System servers", "count", len(ids))
	}
}
