package api

import (
	"context"
	"net/http"
	"testing"

	"github.com/google/uuid"
)

// glossary_propose_batch (#27/#29/#30) is the DETERMINISTIC plan path: the agent
// supplies the ops EXPLICITLY and we mint ONE execute_plan card — no planner model.
// This proves the round trip: tool mints → confirm runs the whole batch under ONE
// human action → every kind is created. This is the coalesce the single-propose
// loop (which produced N un-confirmable cards) replaces.
func TestProposeBatch_RoundTripToConfirm(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	t.Cleanup(func() {
		pool.Exec(context.Background(),
			`DELETE FROM book_kinds WHERE book_id=$1 AND code IN ('qa_batch_a','qa_batch_b')`, f.bookID)
	})

	// ONE create_kinds op holding TWO kinds + an add_attributes op against the first —
	// proves the deterministic executor coalesces a multi-op batch AND respects tier
	// order (create_kinds tier 1 runs before add_attributes tier 2, so the just-created
	// kind is found).
	ops := []proposeBatchOpIn{
		{Type: "create_kinds", Params: map[string]any{"kinds": []map[string]any{
			{"code": "qa_batch_a", "name": "Alpha", "description": "the alpha kind",
				"attributes": []map[string]any{{"code": "role", "name": "Role", "description": "the narrative role", "field_type": "text"}}},
			{"code": "qa_batch_b", "name": "Beta", "description": "the beta kind",
				"attributes": []map[string]any{{"code": "rank", "name": "Rank", "description": "the power rank", "field_type": "text"}}},
		}}},
		{Type: "add_attributes", Params: map[string]any{
			"kind_code":  "qa_batch_a",
			"attributes": []map[string]any{{"code": "origin", "name": "Origin", "description": "where it came from", "field_type": "text"}},
		}},
	}

	_, out, err := f.srv.toolProposeBatch(ctxWithUser(f.ownerID), nil, proposeBatchToolIn{
		BookID: f.bookID.String(), Ops: ops, Goal: "add the two kinds",
	})
	if err != nil {
		t.Fatalf("propose batch: %v", err)
	}
	if asCard(out).ConfirmToken == "" || asCard(out).Descriptor != descExecutePlan {
		t.Fatalf("want an execute_plan card, got %+v", out)
	}
	if len(asCard(out).PreviewRows) != 2 {
		t.Errorf("want 2 preview rows (one per op), got %d", len(asCard(out).PreviewRows))
	}

	if w := f.confirm(t, asCard(out).ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("confirm batch (1 click → whole plan): want 200, got %d (%s)", w.Code, w.Body.String())
	}
	for _, code := range []string{"qa_batch_a", "qa_batch_b"} {
		var exists bool
		if err := pool.QueryRow(context.Background(),
			`SELECT EXISTS(SELECT 1 FROM book_kinds WHERE book_id=$1 AND code=$2 AND deprecated_at IS NULL)`,
			f.bookID, code).Scan(&exists); err != nil {
			t.Fatalf("check kind %s: %v", code, err)
		}
		if !exists {
			t.Errorf("kind %s was not created by the batch confirm", code)
		}
	}
}

// An unknown op type is rejected at mint (ValidatePlan) with an agent-actionable
// error — never minting a card that the confirm path could not run.
func TestProposeBatch_UnknownOpRejected(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	_, _, err := f.srv.toolProposeBatch(ctxWithUser(f.ownerID), nil, proposeBatchToolIn{
		BookID: f.bookID.String(),
		Ops:    []proposeBatchOpIn{{Type: "frobnicate", Params: map[string]any{}}},
	})
	if err == nil {
		t.Fatal("unknown op type: want a validation error, got nil")
	}
}

// Empty ops is guarded BEFORE the grant check (a cheap input guard), so it needs no
// DB — a zero Server with a caller identity suffices.
func TestProposeBatch_EmptyOpsRejected(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolProposeBatch(ctxWithUser(uuid.New()), nil, proposeBatchToolIn{
		BookID: uuid.New().String(), Ops: nil,
	})
	if err == nil {
		t.Fatal("empty ops: want an error, got nil")
	}
}
