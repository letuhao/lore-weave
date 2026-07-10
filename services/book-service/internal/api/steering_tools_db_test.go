package api

// 28 AN-6 (B1/B3) DB-gated tests for the steering MCP tools. Real Postgres
// because they exercise the upsert-by-name discriminator (UNIQUE(book_id,name)),
// the prior-row snapshot, the DELETE ... RETURNING path, and the shared caps.
// Gated on BOOK_TEST_DATABASE_URL (dbTestServer skips when unset). They drive the
// tool handlers directly with the kit identity ctx (SEC-1), the same way
// scenes_read_db_test.go's TestMCPSceneTools_DB does.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// undoHintTool lifts _meta.undo_hint.tool from a Tier-A result (C-ACTIVITY).
func undoHintTool(t *testing.T, res *mcp.CallToolResult) string {
	t.Helper()
	if res == nil || res.Meta == nil {
		t.Fatal("Tier-A result carries no _meta undo_hint")
	}
	hint, ok := res.Meta["undo_hint"].(map[string]any)
	if !ok {
		t.Fatalf("undo_hint missing/wrong shape: %v", res.Meta)
	}
	tool, _ := hint["tool"].(string)
	return tool
}

// Upsert-by-name: first set CREATES, second set with the same name REPLACES and
// returns the prior row; list reflects one row; delete returns the deleted row;
// a second delete errors (never a silent no-op). Undo hints point the right way.
func TestMCPSteeringTools_UpsertPriorRowAndUndo_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedSteeringBook(t, ctx, pool, owner)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	uctx := identityCtxForTest(t, owner)

	// create
	res, out, err := s.toolBookSteeringSet(uctx, nil, steeringSetIn{
		BookID: bookID.String(), Name: "She never begs",
		Body: "Mai never writes her pleading.", InclusionMode: "always",
	})
	if err != nil {
		t.Fatalf("create set: %v", err)
	}
	if out.Replaced || out.Prior != nil {
		t.Fatalf("first set must be a create (replaced=false, prior=nil): %+v", out)
	}
	if out.Row.Name != "She never begs" || out.Row.InclusionMode != "always" || !out.Row.Enabled {
		t.Fatalf("created row wrong: %+v", out.Row)
	}
	if tool := undoHintTool(t, res); tool != "book_steering_delete" {
		t.Fatalf("create undo_hint tool = %q, want book_steering_delete", tool)
	}

	// replace (full PUT semantics on the same name)
	res2, out2, err := s.toolBookSteeringSet(uctx, nil, steeringSetIn{
		BookID: bookID.String(), Name: "She never begs",
		Body: "Updated: she meets it head-on.", InclusionMode: "manual",
	})
	if err != nil {
		t.Fatalf("replace set: %v", err)
	}
	if !out2.Replaced {
		t.Fatal("second set with the same name must replace")
	}
	if out2.Prior == nil || out2.Prior.Body != "Mai never writes her pleading." || out2.Prior.InclusionMode != "always" {
		t.Fatalf("replace must return the PRIOR row: %+v", out2.Prior)
	}
	if out2.Row.Body != "Updated: she meets it head-on." || out2.Row.InclusionMode != "manual" {
		t.Fatalf("replaced row wrong: %+v", out2.Row)
	}
	if tool := undoHintTool(t, res2); tool != "book_steering_set" {
		t.Fatalf("replace undo_hint tool = %q, want book_steering_set (restore prior)", tool)
	}

	// list — exactly the one upserted row
	_, listOut, err := s.toolBookSteeringList(uctx, nil, steeringListIn{BookID: bookID.String()})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if listOut.Total != 1 || len(listOut.Rules) != 1 || listOut.Rules[0].Name != "She never begs" {
		t.Fatalf("list wrong after upsert: %+v", listOut)
	}

	// delete — returns the deleted (latest) row + a set undo_hint
	res3, delOut, err := s.toolBookSteeringDelete(uctx, nil, steeringDeleteIn{BookID: bookID.String(), Name: "She never begs"})
	if err != nil {
		t.Fatalf("delete: %v", err)
	}
	if delOut.Deleted.Body != "Updated: she meets it head-on." {
		t.Fatalf("delete must return the deleted row: %+v", delOut.Deleted)
	}
	if tool := undoHintTool(t, res3); tool != "book_steering_set" {
		t.Fatalf("delete undo_hint tool = %q, want book_steering_set (restore)", tool)
	}

	// second delete — an unknown name is an explicit error, never a silent no-op
	if _, _, err := s.toolBookSteeringDelete(uctx, nil, steeringDeleteIn{BookID: bookID.String(), Name: "She never begs"}); err == nil {
		t.Fatal("deleting an already-gone rule must error, not silently succeed")
	}

	// and the store is empty
	_, listOut2, _ := s.toolBookSteeringList(uctx, nil, steeringListIn{BookID: bookID.String()})
	if listOut2.Total != 0 {
		t.Fatalf("store not empty after delete: %+v", listOut2)
	}
}

// The set adapter re-enforces the engine's caps + the closed inclusion_mode enum.
func TestMCPSteeringSet_RejectsBadInput_DB(t *testing.T) {
	s, pool := dbTestServer(t)
	ctx := context.Background()
	owner := uuid.New()
	bookID := seedSteeringBook(t, ctx, pool, owner)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM books WHERE id=$1`, bookID) })
	uctx := identityCtxForTest(t, owner)

	// body over the 8000-rune cap → actionable one-liner
	big := strings.Repeat("x", maxSteeringBodyChars+1)
	if _, _, err := s.toolBookSteeringSet(uctx, nil, steeringSetIn{BookID: bookID.String(), Name: "cap", Body: big}); err == nil || !strings.Contains(err.Error(), "8000") {
		t.Fatalf("over-cap body must be rejected with the 8000 one-liner: %v", err)
	}
	// closed-set inclusion_mode enum
	if _, _, err := s.toolBookSteeringSet(uctx, nil, steeringSetIn{BookID: bookID.String(), Name: "enum", Body: "ok", InclusionMode: "whenever"}); err == nil || !strings.Contains(err.Error(), "inclusion_mode") {
		t.Fatalf("bad inclusion_mode must be rejected: %v", err)
	}
	// scene_match requires a match_pattern
	if _, _, err := s.toolBookSteeringSet(uctx, nil, steeringSetIn{BookID: bookID.String(), Name: "sm", Body: "ok", InclusionMode: "scene_match"}); err == nil || !strings.Contains(err.Error(), "match_pattern") {
		t.Fatalf("scene_match without match_pattern must be rejected: %v", err)
	}
	// empty body / name
	if _, _, err := s.toolBookSteeringSet(uctx, nil, steeringSetIn{BookID: bookID.String(), Name: "n", Body: "   "}); err == nil {
		t.Fatal("empty body must be rejected")
	}

	// none of the rejected calls landed a row
	var n int
	_ = pool.QueryRow(ctx, `SELECT COUNT(*) FROM book_steering WHERE book_id=$1`, bookID).Scan(&n)
	if n != 0 {
		t.Fatalf("a rejected set landed a row: %d", n)
	}
}
