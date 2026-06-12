// retention_worker_live_smoke_test.go — L2.K retention-worker live wiring (058).
//
// End-to-end on REAL Postgres (foundation-dev): both retention paths.
//
//   retention_loop.Run:
//     1. outbox prune (pgx Deleter) — DELETE published+old events_outbox rows,
//        NEVER pending / dead-lettered.
//     2. audit retention (os/exec → scripts/event-audit-retention-cron.sh → psql)
//        — per-class DELETE (30d non-flagged / 90d flagged) in event_audit.
//
// gated by `integration`; needs LW_INTEGRATION_DB. Requires host `bash` + `psql`
// (the audit script shells out to psql against the DSN).
// Bootstrap: scripts/retention-worker-live-smoke.sh.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	_ "github.com/lib/pq"

	"github.com/loreweave/foundation/services/retention-worker/pkg/audit_invoker"
	"github.com/loreweave/foundation/services/retention-worker/pkg/outbox_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/pgio"
	"github.com/loreweave/foundation/services/retention-worker/pkg/retention_loop"
	"github.com/loreweave/foundation/services/retention-worker/pkg/scriptrun"
	"github.com/loreweave/foundation/services/retention-worker/pkg/snapshot_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

func TestRetentionWorkerLiveSmoke_OutboxAndAuditPrune(t *testing.T) {
	dsn := os.Getenv("LW_INTEGRATION_DB")
	if dsn == "" {
		t.Skip("LW_INTEGRATION_DB not set; live stack unavailable")
	}
	if _, err := exec.LookPath("psql"); err != nil {
		t.Skip("host psql not available; audit-retention script can't run")
	}
	ctx := context.Background()

	db := openSQL(t, dsn)
	mustApply(t, db, "contracts/migrations/per_reality/0003_event_audit_table.up.sql")
	mustApply(t, db, "contracts/migrations/per_reality/0005_events_outbox_table.up.sql")
	// 088 D-OUTBOX-PRUNE-INDEX: apply the prune-supporting partial index so the
	// prune below runs against it (proves the index doesn't change prune results).
	mustApply(t, db, "contracts/migrations/per_reality/0012_events_outbox_prune_index.up.sql")

	realityID := uuid.New()

	// ── Seed events_outbox ────────────────────────────────────────────────
	old := time.Now().Add(-25 * time.Hour) // past the 24h published grace
	recent := time.Now().Add(-1 * time.Hour)
	eligibleID := uuid.New()
	seedOutbox(t, db, eligibleID, realityID, true, &old, nil) // → DELETE
	seedOutbox(t, db, uuid.New(), realityID, false, nil, nil) // pending → keep
	dlAt := time.Now()
	seedOutbox(t, db, uuid.New(), realityID, true, &old, &dlAt)  // dead-lettered → keep
	seedOutbox(t, db, uuid.New(), realityID, true, &recent, nil) // within grace → keep

	// ── Seed event_audit: a 45-day-old partition (row-DELETE path) ────────
	t45 := time.Now().AddDate(0, 0, -45)
	mStart := time.Date(t45.Year(), t45.Month(), 1, 0, 0, 0, 0, time.UTC)
	mEnd := mStart.AddDate(0, 1, 0)
	auditPart := fmt.Sprintf("event_audit_p_%04d_%02d", mStart.Year(), int(mStart.Month()))
	t.Cleanup(func() {
		_, _ = db.Exec(`DROP TABLE IF EXISTS ` + auditPart)
		_, _ = db.Exec(`DELETE FROM event_audit WHERE reality_id=$1`, realityID)
		_, _ = db.Exec(`DELETE FROM events_outbox WHERE reality_id=$1`, realityID)
	})
	if _, err := db.Exec(fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s PARTITION OF event_audit FOR VALUES FROM ('%s') TO ('%s')`,
		auditPart, mStart.Format("2006-01-02"), mEnd.Format("2006-01-02"))); err != nil {
		t.Fatalf("create audit partition: %v", err)
	}
	nonFlaggedOld := uuid.New() // 45d non-flagged → DELETE (>30d)
	flaggedOld := uuid.New()    // 45d flagged → keep (<90d)
	recentAudit := uuid.New()   // now non-flagged → keep
	seedAudit(t, db, nonFlaggedOld, realityID, false, t45)
	seedAudit(t, db, flaggedOld, realityID, true, t45)
	seedAudit(t, db, recentAudit, realityID, false, time.Now())

	// ── Build the loop (pgx Deleter + exec ScriptRunner) ──────────────────
	pool := openTestPool(t, ctx, dsn)
	cfg := types.DefaultConfig()
	op, err := outbox_pruner.New(outbox_pruner.Config{
		Deleter: pgio.NewDeleter(map[string]*pgxpool.Pool{realityID.String(): pool}),
		Clock:   outbox_pruner.RealClock{}, Cfg: cfg,
	})
	if err != nil {
		t.Fatalf("outbox_pruner: %v", err)
	}
	scriptPath := filepath.Join(repoRoot(t), "scripts", "event-audit-retention-cron.sh")
	ai, err := audit_invoker.New(scriptrun.New(scriptPath), cfg)
	if err != nil {
		t.Fatalf("audit_invoker: %v", err)
	}
	loop, err := retention_loop.New(retention_loop.Config{
		OutboxPruner: op, AuditInvoker: ai, SnapshotPruner: snapshot_pruner.New(),
		DSNLookup: &retention_loop.MapDSNLookup{M: map[uuid.UUID]string{realityID: dsn}},
		Mode:      modeFull{},
	})
	if err != nil {
		t.Fatalf("retention_loop: %v", err)
	}

	stats, err := loop.Run(ctx, realityID)
	if err != nil {
		t.Fatalf("loop.Run: %v", err)
	}

	// ── Assert outbox prune ───────────────────────────────────────────────
	if stats.Outbox.Deleted != 1 {
		t.Errorf("Outbox.Deleted=%d want 1", stats.Outbox.Deleted)
	}
	var outboxLeft int
	if err := db.QueryRow(`SELECT count(*) FROM events_outbox WHERE reality_id=$1`, realityID).Scan(&outboxLeft); err != nil {
		t.Fatal(err)
	}
	if outboxLeft != 3 {
		t.Errorf("events_outbox left=%d want 3 (pending + dead-lettered + recent)", outboxLeft)
	}
	assertOutboxGone(t, db, eligibleID)

	// ── Assert audit prune (row-DELETE path) ──────────────────────────────
	if stats.Audit.NonFlaggedDeleted != 1 {
		t.Errorf("Audit.NonFlaggedDeleted=%d want 1", stats.Audit.NonFlaggedDeleted)
	}
	if stats.Audit.FlaggedDeleted != 0 {
		t.Errorf("Audit.FlaggedDeleted=%d want 0 (45d < 90d flagged threshold)", stats.Audit.FlaggedDeleted)
	}
	assertAuditPresent(t, db, nonFlaggedOld, false) // 45d non-flagged → deleted
	assertAuditPresent(t, db, flaggedOld, true)     // 45d flagged → kept
	assertAuditPresent(t, db, recentAudit, true)    // recent → kept
}

func seedOutbox(t *testing.T, db *sql.DB, eventID, realityID uuid.UUID, published bool, lastAttempt *time.Time, deadLettered *time.Time) {
	t.Helper()
	attempts := 0
	if published || deadLettered != nil {
		attempts = 1
	}
	if _, err := db.Exec(`
		INSERT INTO events_outbox (event_id, reality_id, published, attempts, last_attempt_at, dead_lettered_at)
		VALUES ($1,$2,$3,$4,$5,$6)`,
		eventID, realityID, published, attempts, lastAttempt, deadLettered); err != nil {
		t.Fatalf("seed outbox %s: %v", eventID, err)
	}
}

func seedAudit(t *testing.T, db *sql.DB, auditID, realityID uuid.UUID, flagged bool, recordedAt time.Time) {
	t.Helper()
	var flagReason *string
	if flagged {
		s := "smoke"
		flagReason = &s
	}
	if _, err := db.Exec(`
		INSERT INTO event_audit
		    (audit_id, reality_id, event_type, aggregate_type, aggregate_id, flagged, flag_reason, recorded_at)
		VALUES ($1,$2,'npc.said','npc','npc-1',$3,$4,$5)`,
		auditID, realityID, flagged, flagReason, recordedAt.UTC()); err != nil {
		t.Fatalf("seed audit %s: %v", auditID, err)
	}
}

func assertOutboxGone(t *testing.T, db *sql.DB, eventID uuid.UUID) {
	t.Helper()
	var n int
	if err := db.QueryRow(`SELECT count(*) FROM events_outbox WHERE event_id=$1`, eventID).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 0 {
		t.Errorf("outbox event %s should have been pruned", eventID)
	}
}

func assertAuditPresent(t *testing.T, db *sql.DB, auditID uuid.UUID, want bool) {
	t.Helper()
	var n int
	if err := db.QueryRow(`SELECT count(*) FROM event_audit WHERE audit_id=$1`, auditID).Scan(&n); err != nil {
		t.Fatal(err)
	}
	present := n == 1
	if present != want {
		t.Errorf("audit %s present=%v want %v", auditID, present, want)
	}
}
