//go:build integration

// tests/integration/outbox_prune_test.go — L2.K end-to-end coverage.
//
// Cycle 11. Drives the retention-worker outbox_pruner with realistic
// row-mix to enforce:
//
//   1. published + old rows are deleted
//   2. published + dead-letter rows are PRESERVED (SRE evidence)
//   3. pending (published=FALSE) rows are PRESERVED (unpublished events)
//   4. published + recent rows are PRESERVED (within grace window)
//
// This is the integration-test footprint for the D-OUTBOX-PRUNE deferred
// row (055). When the L4 production wiring lands, this test gains an
// integration_live variant that drives real pgx.

package integration

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/retention-worker/pkg/outbox_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

func TestOutboxPrune_MixedRowSet(t *testing.T) {
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	rid := uuid.New()
	deadAt := now.Add(-48 * time.Hour)

	del := outbox_pruner.NewInMemoryDeleter()
	// 100 published-and-old (eligible)
	for i := 0; i < 100; i++ {
		del.Add(rid, outbox_pruner.OutboxCandidate{
			EventID:       uuid.New(),
			Published:     true,
			LastAttemptAt: now.Add(-72 * time.Hour),
		})
	}
	// 10 pending — MUST be preserved
	for i := 0; i < 10; i++ {
		del.Add(rid, outbox_pruner.OutboxCandidate{EventID: uuid.New(), Published: false})
	}
	// 5 dead-letter — MUST be preserved (SRE evidence)
	for i := 0; i < 5; i++ {
		del.Add(rid, outbox_pruner.OutboxCandidate{
			EventID:        uuid.New(),
			Published:      true,
			LastAttemptAt:  now.Add(-100 * time.Hour),
			DeadLetteredAt: &deadAt,
		})
	}
	// 20 recent published — within grace window, MUST be preserved
	for i := 0; i < 20; i++ {
		del.Add(rid, outbox_pruner.OutboxCandidate{
			EventID:       uuid.New(),
			Published:     true,
			LastAttemptAt: now.Add(-time.Hour),
		})
	}

	p, err := outbox_pruner.New(outbox_pruner.Config{
		Deleter: del,
		Clock:   frozenClock{t: now},
		Cfg:     types.DefaultConfig(),
	})
	if err != nil {
		t.Fatal(err)
	}
	stats, err := p.PruneReality(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}

	if stats.Deleted != 100 {
		t.Fatalf("expected 100 deleted, got %d", stats.Deleted)
	}
	preserved := len(del.Rows[rid])
	if preserved != 35 {
		t.Fatalf("expected 35 preserved (10 pending + 5 dead-letter + 20 recent), got %d", preserved)
	}

	// Double-check NO dead-letter row was deleted (invariant scan).
	for _, r := range del.Rows[rid] {
		// All remaining rows should be either pending, dead-letter, or recent.
		if r.Published && r.DeadLetteredAt == nil && r.LastAttemptAt.Before(now.Add(-24*time.Hour)) {
			t.Fatalf("INVARIANT VIOLATED: preserved row %s is eligible (Published=%v LastAttempt=%v DeadLetter=%v)",
				r.EventID, r.Published, r.LastAttemptAt, r.DeadLetteredAt)
		}
	}
}

func TestOutboxPrune_DeadLetterAndPendingPreserved_ZeroDeleted(t *testing.T) {
	// Edge case: a reality with ONLY pending + dead-letter rows should
	// prune zero (regression guard against a future "delete everything"
	// bug).
	now := time.Date(2026, 5, 29, 0, 0, 0, 0, time.UTC)
	rid := uuid.New()
	deadAt := now.Add(-48 * time.Hour)
	del := outbox_pruner.NewInMemoryDeleter()
	del.Add(rid,
		outbox_pruner.OutboxCandidate{EventID: uuid.New(), Published: false},
		outbox_pruner.OutboxCandidate{EventID: uuid.New(), Published: true, LastAttemptAt: now.Add(-100 * time.Hour), DeadLetteredAt: &deadAt},
	)
	p, _ := outbox_pruner.New(outbox_pruner.Config{
		Deleter: del,
		Clock:   frozenClock{t: now},
		Cfg:     types.DefaultConfig(),
	})
	stats, err := p.PruneReality(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Deleted != 0 {
		t.Fatalf("expected 0 deleted, got %d (INVARIANT VIOLATED)", stats.Deleted)
	}
	if len(del.Rows[rid]) != 2 {
		t.Fatalf("expected both rows preserved, got %d", len(del.Rows[rid]))
	}
}
