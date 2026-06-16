package retention_loop

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"

	"github.com/loreweave/foundation/services/retention-worker/pkg/audit_invoker"
	"github.com/loreweave/foundation/services/retention-worker/pkg/outbox_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/snapshot_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

type fakeMode struct{ m lifecycle.ServiceMode }

func (f fakeMode) Mode() lifecycle.ServiceMode { return f.m }

type frozenClock struct{ t time.Time }

func (f frozenClock) Now() time.Time { return f.t }

func mkLoop(t *testing.T, mode lifecycle.ServiceMode, dsnMap map[uuid.UUID]string) (*Loop, *outbox_pruner.InMemoryDeleter, *audit_invoker.MockRunner) {
	t.Helper()
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	del := outbox_pruner.NewInMemoryDeleter()
	op, err := outbox_pruner.New(outbox_pruner.Config{
		Deleter: del,
		Clock:   frozenClock{t: now},
		Cfg:     types.DefaultConfig(),
	})
	if err != nil {
		t.Fatal(err)
	}
	mr := audit_invoker.NewMockRunner()
	ai, err := audit_invoker.New(mr, types.DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	sp := snapshot_pruner.New()
	l, err := New(Config{
		OutboxPruner:   op,
		AuditInvoker:   ai,
		SnapshotPruner: sp,
		DSNLookup:      &MapDSNLookup{M: dsnMap},
		Mode:           fakeMode{m: mode},
	})
	if err != nil {
		t.Fatal(err)
	}
	return l, del, mr
}

func TestRun_HappyPath_PrunesOutboxAndInvokesAudit(t *testing.T) {
	rid := uuid.New()
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	l, del, mr := mkLoop(t, lifecycle.ModeFull, map[uuid.UUID]string{rid: "postgres://x"})

	// Add 3 eligible + 1 pending + 1 dead-letter to the outbox.
	deadAt := now.Add(-48 * time.Hour)
	for i := 0; i < 3; i++ {
		del.Add(rid, outbox_pruner.OutboxCandidate{Published: true, LastAttemptAt: now.Add(-48 * time.Hour)})
	}
	del.Add(rid, outbox_pruner.OutboxCandidate{Published: false})
	del.Add(rid, outbox_pruner.OutboxCandidate{Published: true, LastAttemptAt: now.Add(-72 * time.Hour), DeadLetteredAt: &deadAt})

	// Audit mock returns 100 non-flagged + 5 flagged deleted.
	mr.Outcomes[rid] = types.AuditPruneStats{NonFlaggedDeleted: 100, FlaggedDeleted: 5}

	stats, err := l.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Skipped {
		t.Fatal("happy path MUST NOT be skipped")
	}
	if stats.Outbox.Deleted != 3 {
		t.Fatalf("outbox deleted: got %d want 3", stats.Outbox.Deleted)
	}
	if len(del.Rows[rid]) != 2 {
		t.Fatalf("expected 2 preserved (pending + dead-letter), got %d", len(del.Rows[rid]))
	}
	if stats.Audit.NonFlaggedDeleted != 100 || stats.Audit.FlaggedDeleted != 5 {
		t.Fatalf("audit propagation broken: %+v", stats.Audit)
	}
	if len(mr.Calls) != 1 || mr.Calls[0].DSN != "postgres://x" {
		t.Fatalf("audit-script invocation: %+v", mr.Calls)
	}
}

func TestRun_DegradedMode_Skipped(t *testing.T) {
	rid := uuid.New()
	l, del, mr := mkLoop(t, lifecycle.ModeEssentials, map[uuid.UUID]string{rid: "postgres://x"})
	del.Add(rid, outbox_pruner.OutboxCandidate{Published: true, LastAttemptAt: time.Now().Add(-48 * time.Hour)})

	stats, err := l.Run(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Skipped {
		t.Fatal("expected Skipped=true under ModeEssentials")
	}
	if len(mr.Calls) != 0 {
		t.Fatal("audit script MUST NOT be invoked under degraded mode")
	}
	// Outbox row preserved (DELETE skipped).
	if len(del.Rows[rid]) != 1 {
		t.Fatalf("expected outbox untouched under degraded mode, got %d rows", len(del.Rows[rid]))
	}
}

func TestRun_DSNLookupError_Propagates(t *testing.T) {
	rid := uuid.New()
	l, _, _ := mkLoop(t, lifecycle.ModeFull, map[uuid.UUID]string{}) // no DSN entry
	_, err := l.Run(context.Background(), rid)
	if err == nil {
		t.Fatal("expected DSN lookup error")
	}
}

func TestRun_RealityIDPreserved(t *testing.T) {
	rid := uuid.New()
	l, _, _ := mkLoop(t, lifecycle.ModeFull, map[uuid.UUID]string{rid: "postgres://x"})
	stats, _ := l.Run(context.Background(), rid)
	if stats.RealityID != rid {
		t.Fatalf("RealityID drift: got %s want %s", stats.RealityID, rid)
	}
}

func TestNew_RejectsNilDeps(t *testing.T) {
	if _, err := New(Config{}); err == nil {
		t.Fatal("expected nil OutboxPruner error")
	}
}
