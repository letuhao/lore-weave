package outbox_pruner

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

type frozenClock struct{ t time.Time }

func (f frozenClock) Now() time.Time { return f.t }

func TestEligible_PublishedAndOldAndNotDeadLettered(t *testing.T) {
	cutoff := time.Date(2026, 5, 28, 0, 0, 0, 0, time.UTC)
	c := OutboxCandidate{
		Published:     true,
		LastAttemptAt: cutoff.Add(-time.Hour),
	}
	if !c.Eligible(cutoff) {
		t.Fatal("expected eligible")
	}
}

func TestEligible_PendingNotEligible(t *testing.T) {
	cutoff := time.Date(2026, 5, 28, 0, 0, 0, 0, time.UTC)
	c := OutboxCandidate{Published: false, LastAttemptAt: cutoff.Add(-time.Hour)}
	if c.Eligible(cutoff) {
		t.Fatal("pending row MUST NOT be eligible (invariant: never prune unpublished)")
	}
}

func TestEligible_DeadLetterNotEligible(t *testing.T) {
	cutoff := time.Date(2026, 5, 28, 0, 0, 0, 0, time.UTC)
	d := cutoff.Add(-48 * time.Hour)
	c := OutboxCandidate{
		Published:      true,
		LastAttemptAt:  cutoff.Add(-time.Hour),
		DeadLetteredAt: &d,
	}
	if c.Eligible(cutoff) {
		t.Fatal("dead-lettered row MUST NOT be eligible (invariant: SRE evidence)")
	}
}

func TestEligible_RecentNotEligible(t *testing.T) {
	cutoff := time.Date(2026, 5, 28, 0, 0, 0, 0, time.UTC)
	c := OutboxCandidate{
		Published:     true,
		LastAttemptAt: cutoff.Add(time.Hour), // after cutoff = recent
	}
	if c.Eligible(cutoff) {
		t.Fatal("recent published row MUST NOT be eligible (still within grace)")
	}
}

func TestPruneReality_HappyPath(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	rid := uuid.New()
	del := NewInMemoryDeleter()
	deadAt := now.Add(-48 * time.Hour)
	del.Add(rid,
		// eligible
		OutboxCandidate{EventID: uuid.New(), Published: true, LastAttemptAt: now.Add(-48 * time.Hour)},
		OutboxCandidate{EventID: uuid.New(), Published: true, LastAttemptAt: now.Add(-25 * time.Hour)},
		// pending — MUST be preserved
		OutboxCandidate{EventID: uuid.New(), Published: false},
		// dead-letter — MUST be preserved
		OutboxCandidate{EventID: uuid.New(), Published: true, LastAttemptAt: now.Add(-72 * time.Hour), DeadLetteredAt: &deadAt},
		// recent — MUST be preserved
		OutboxCandidate{EventID: uuid.New(), Published: true, LastAttemptAt: now.Add(-time.Hour)},
	)

	p, err := New(Config{Deleter: del, Clock: frozenClock{t: now}, Cfg: types.DefaultConfig()})
	if err != nil {
		t.Fatal(err)
	}
	stats, err := p.PruneReality(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Deleted != 2 {
		t.Fatalf("expected Deleted=2, got %d", stats.Deleted)
	}
	if len(del.Rows[rid]) != 3 {
		t.Fatalf("expected 3 rows preserved (pending + dead-letter + recent), got %d", len(del.Rows[rid]))
	}
}

func TestPruneReality_EmptyReality(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	del := NewInMemoryDeleter()
	p, _ := New(Config{Deleter: del, Clock: frozenClock{t: now}, Cfg: types.DefaultConfig()})
	stats, _ := p.PruneReality(context.Background(), uuid.New())
	if stats.Deleted != 0 {
		t.Fatal("expected zero deletes on empty reality")
	}
}

func TestPruneReality_BatchSize(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	rid := uuid.New()
	del := NewInMemoryDeleter()
	// 25 eligible rows; batch size 10 ⇒ 3 batches (10, 10, 5).
	for i := 0; i < 25; i++ {
		del.Add(rid, OutboxCandidate{Published: true, LastAttemptAt: now.Add(-48 * time.Hour)})
	}
	cfg := types.DefaultConfig()
	cfg.OutboxBatchSize = 10
	p, _ := New(Config{Deleter: del, Clock: frozenClock{t: now}, Cfg: cfg})
	stats, _ := p.PruneReality(context.Background(), rid)
	if stats.Deleted != 25 {
		t.Fatalf("expected Deleted=25 across batches, got %d", stats.Deleted)
	}
}

func TestPruneReality_ErrorPropagates(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	p, _ := New(Config{
		Deleter: &FailingDeleter{Err: errors.New("db down")},
		Clock:   frozenClock{t: now},
		Cfg:     types.DefaultConfig(),
	})
	_, err := p.PruneReality(context.Background(), uuid.New())
	if err == nil {
		t.Fatal("expected error to propagate")
	}
}

func TestNew_RejectsNilDeps(t *testing.T) {
	if _, err := New(Config{}); err == nil {
		t.Fatal("expected nil Deleter error")
	}
	if _, err := New(Config{Deleter: NewInMemoryDeleter()}); err == nil {
		t.Fatal("expected nil Clock error")
	}
}

func TestNew_DefaultsApplied(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	p, _ := New(Config{Deleter: NewInMemoryDeleter(), Clock: frozenClock{t: now}})
	if p.cfg.OutboxBatchSize != 10000 {
		t.Fatalf("default batch size: got %d want 10000", p.cfg.OutboxBatchSize)
	}
	if p.cfg.OutboxPublishedGrace != 24*time.Hour {
		t.Fatalf("default grace: got %v want 24h", p.cfg.OutboxPublishedGrace)
	}
}
