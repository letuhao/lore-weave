package api

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
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
	// review-impl: the chat agent loop DROPS structuredContent on isError, so the
	// message TEXT must carry the actual failure reason and must NOT point at
	// structuredContent the caller never receives.
	msg := isErrorText(t, res)
	if !strings.Contains(msg, "unknown kind") {
		t.Fatalf("isError message must inline the per-item reason, got: %q", msg)
	}
	if strings.Contains(msg, "structuredContent") {
		t.Fatalf("isError message must not reference structuredContent (the caller drops it): %q", msg)
	}
}

// review-impl finding 2: a batch where some items already EXIST and some ERROR
// (nothing created) is still IsError, but the message must not claim "every item
// failed" — it must reflect the real counts (an already-existing item did not fail).
func TestProposeEntities_SkippedPlusError_MessageReflectsCounts(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool) // "character" kind exists
	octx := ctxWithUser(f.ownerID)
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM entity_attribute_values WHERE entity_id IN (SELECT entity_id FROM glossary_entities WHERE book_id=$1)`, f.bookID)
		pool.Exec(context.Background(), `DELETE FROM glossary_entities WHERE book_id=$1`, f.bookID)
	})
	// First create one real entity so a re-propose of it skips_exists.
	if _, _, err := f.srv.toolProposeEntities(octx, nil, proposeEntitiesToolIn{
		BookID: f.bookID.String(),
		Items:  []proposeEntityItemIn{{Kind: "character", Name: "Exists Already"}},
	}); err != nil {
		t.Fatalf("seed: %v", err)
	}
	// Now: one already-exists (skip) + one unknown-kind (error), zero created.
	res, out, err := f.srv.toolProposeEntities(octx, nil, proposeEntitiesToolIn{
		BookID: f.bookID.String(),
		Items: []proposeEntityItemIn{
			{Kind: "character", Name: "Exists Already"},
			{Kind: "not_a_real_kind", Name: "Bad One"},
		},
	})
	if err != nil {
		t.Fatalf("call: %v", err)
	}
	if out.Summary.Created != 0 || out.Summary.Skipped != 1 || out.Summary.Failed != 1 {
		t.Fatalf("want 0 created / 1 skipped / 1 failed, got %+v", out.Summary)
	}
	if res == nil || !res.IsError {
		t.Fatalf("nothing created + a real failure → IsError; got %+v", res)
	}
	msg := isErrorText(t, res)
	if strings.Contains(msg, "every") {
		t.Fatalf("message must not claim every item failed when one already existed: %q", msg)
	}
	if !strings.Contains(msg, "already existed") {
		t.Fatalf("message must acknowledge the already-existing item: %q", msg)
	}
}

// isErrorText extracts the single TextContent from an isError CallToolResult.
func isErrorText(t *testing.T, res *mcp.CallToolResult) string {
	t.Helper()
	if res == nil || len(res.Content) == 0 {
		t.Fatalf("expected an isError result with content, got %+v", res)
	}
	tc, ok := res.Content[0].(*mcp.TextContent)
	if !ok {
		t.Fatalf("expected TextContent, got %T", res.Content[0])
	}
	return tc.Text
}

func TestProposeEntities_EmptyItems_Rejected(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolProposeEntities(ctxWithUser(uuid.New()), nil, proposeEntitiesToolIn{BookID: "x", Items: nil})
	if err == nil {
		t.Fatal("want an error for empty items")
	}
}
