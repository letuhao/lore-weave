package api

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

// ── glossary_propose_entities (§3.3 resolved 2026-07-06) ──────────────────────

func TestProposeEntities_BatchCreate_MixedNewAndExisting(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // pre-adopted — "character" kind exists
	octx := ctxWithUser(f.ownerID)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, f.bookID)
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})

	_, out, err := f.srv.toolProposeEntities(octx, nil, proposeEntitiesToolIn{
		BookID: f.bookID.String(),
		Items: []proposeEntityItemIn{
			{Kind: "character", Name: "Nezha"},
			{Kind: "character", Name: "Ao Bing"},
		},
	})
	if err != nil {
		t.Fatalf("batch propose: %v", err)
	}
	if out.Summary.Created != 2 || out.Summary.Failed != 0 {
		t.Fatalf("want 2 created, got %+v (results=%+v)", out.Summary, out.Results)
	}
	for _, r := range out.Results {
		if r.Status != "created" || r.EntityID == "" {
			t.Errorf("bad result: %+v", r)
		}
	}

	// Re-propose the SAME batch → both dedup as skipped_exists, not duplicated.
	_, out2, err := f.srv.toolProposeEntities(octx, nil, proposeEntitiesToolIn{
		BookID: f.bookID.String(),
		Items: []proposeEntityItemIn{
			{Kind: "character", Name: "Nezha"},
			{Kind: "character", Name: "Ao Bing"},
		},
	})
	if err != nil {
		t.Fatalf("re-propose: %v", err)
	}
	if out2.Summary.Skipped != 2 || out2.Summary.Created != 0 {
		t.Fatalf("want 2 skipped_exists, got %+v", out2.Summary)
	}
}

func TestProposeEntities_UnknownKind_PerItemErrorNotWholeBatchFailure(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, f.bookID)
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})

	res, out, err := f.srv.toolProposeEntities(octx, nil, proposeEntitiesToolIn{
		BookID: f.bookID.String(),
		Items: []proposeEntityItemIn{
			{Kind: "character", Name: "Real One"},
			{Kind: "not_a_real_kind", Name: "Bad One"},
		},
	})
	if err != nil {
		t.Fatalf("call should succeed with a per-item error, not a whole-batch rejection: %v", err)
	}
	if out.Summary.Created != 1 || out.Summary.Failed != 1 {
		t.Fatalf("want 1 created + 1 per-item failure, got %+v (results=%+v)", out.Summary, out.Results)
	}
	// A PARTIAL success (something was created) must NOT flip the envelope to
	// IsError — the created entity is real; the per-item error is in Results.
	if res != nil && res.IsError {
		t.Fatalf("partial success (1 created) must stay ok, not IsError: %+v", res)
	}
}

// The silent-success bug (S01): every item names a kind that doesn't exist, so
// NOTHING is created — yet the tool returned envelope ok:true with a hidden
// Failed count. A mid-tier agent reads "success", never learns it must adopt
// kinds first, and loops. The envelope MUST report IsError when the batch
// created nothing AND at least one item genuinely errored.
func TestProposeEntities_AllFailed_MarksIsError(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	octx := ctxWithUser(f.ownerID)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, f.bookID)
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})

	res, out, err := f.srv.toolProposeEntities(octx, nil, proposeEntitiesToolIn{
		BookID: f.bookID.String(),
		Items: []proposeEntityItemIn{
			{Kind: "not_a_real_kind", Name: "Bad One"},
			{Kind: "also_fake", Name: "Bad Two"},
		},
	})
	if err != nil {
		t.Fatalf("still a per-item batch (no whole-batch Go error): %v", err)
	}
	if out.Summary.Created != 0 || out.Summary.Failed != 2 {
		t.Fatalf("want 0 created + 2 failed, got %+v", out.Summary)
	}
	if res == nil || !res.IsError {
		t.Fatalf("nothing created + items failed → envelope MUST be IsError; got res=%+v", res)
	}
	// Per-item detail survives ALONGSIDE IsError — the agent needs to see WHICH
	// kinds were unknown to self-correct (the SDK marshals out into structuredContent).
	if len(out.Results) != 2 || out.Results[0].Error == "" {
		t.Fatalf("per-item errors must survive alongside IsError: %+v", out.Results)
	}
}

func TestProposeEntities_EmptyItems_Rejected(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolProposeEntities(ctxWithUser(uuid.New()), nil, proposeEntitiesToolIn{BookID: "x", Items: nil})
	if err == nil {
		t.Fatal("want an error for empty items")
	}
}
