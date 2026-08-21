package api

import (
	"strings"
	"testing"
)

// TOOLV2 LOOP #318 — a tool whose description said "Reversible" while the reverse did not exist.
//
// world_move_book was right about everything it guards: the target world must be owned (uniform
// "world not found", and a transient query failure is kept distinct so it cannot masquerade as a
// missing world and provoke a duplicate create), a hidden bible book can never be re-homed, and a
// diary is refused because a world is shareable and moving a diary into one is a back-door share.
//
// The word "Reversible" was the defect. Measured live, every form of the reverse was rejected:
//
//	world_id: null      → type … has type "null", want "string"
//	world_id omitted    → required: missing properties: ["world_id"]
//	world_id: ""        → world_id must be a UUID
//	clear_world: true   → unexpected additional properties ["clear_world"]
//
// and the move returned no _meta, so the book's previous world was not reported either. A book
// moved into a world could never be returned to standalone through the agent surface at all. REST
// has had the capability the whole time — removeBookFromWorld sets world_id=NULL — so this was a
// hole in the agent surface specifically, not a missing product feature.
//
// It also made world_delete's refusal unfollowable from the other side: that message tells the
// agent to "move them out (world_move_book to another world)", and moving to another world only
// relocates the problem.
func TestMoveBookCanTakeABookBackOut(t *testing.T) {
	fn := moveBookBody(t)
	if !strings.Contains(fn, "if in.WorldID == \"\" && !in.ClearWorld {") {
		t.Fatal("there is no clear path — a book moved into a world cannot be made standalone " +
			"again, so the tool's own \"Reversible\" claim is false")
	}
	if !strings.Contains(fn, "var target any") || !strings.Contains(fn, "if !in.ClearWorld {") {
		t.Error("the target world_id is no longer nullable, so clearing cannot write NULL")
	}
	// Both at once asks for opposite things; silently preferring one would move a book the caller
	// believed it was detaching.
	if !strings.Contains(fn, "in.WorldID != \"\" && in.ClearWorld") {
		t.Error("passing world_id AND clear_world together is not refused — one would silently win")
	}
}

// The undo must express BOTH shapes. A book that was standalone before cannot be restored by
// replaying a world_id, and omitting it would leave the book where this call just put it — which
// is precisely why clear_world had to exist.
func TestTheMoveUndoClearsWhenTheBookWasStandalone(t *testing.T) {
	fn := moveBookBody(t)
	if !strings.Contains(fn, `undoResult("world_move_book"`) {
		t.Fatal("a move emits no undo hint, so the book's previous world is lost")
	}
	if !strings.Contains(fn, "if priorWorld != nil {") || !strings.Contains(fn, `undoArgs["clear_world"] = true`) {
		t.Fatal("a book that belonged to NO world does not replay clear_world=true — the undo " +
			"would leave it in the world this call moved it into")
	}
	if !strings.Contains(fn, `undoArgs["world_id"] = priorWorld.String()`) {
		t.Error("a book that came from another world does not replay it, so the undo detaches it " +
			"instead of moving it back")
	}
}

// The prior world must come from the UPDATE itself, alias-qualified — books is joined twice.
func TestThePriorWorldComesFromTheSameStatement(t *testing.T) {
	fn := moveBookBody(t)
	if !strings.Contains(fn, "FROM books old") || !strings.Contains(fn, "RETURNING old.world_id") {
		t.Fatal("the prior world_id is not returned by the update statement")
	}
	if !strings.Contains(fn, "b.id=old.id AND b.id=$2 AND b.owner_user_id=$3") {
		t.Error("the self-join or the owner scope changed shape")
	}
	for _, bare := range []string{"WHERE id=$2", "AND is_bible=false AND kind<>"} {
		if strings.Contains(fn, bare) {
			t.Errorf("an unqualified column reference (%q) survived — with books joined twice "+
				"Postgres rejects the statement as ambiguous, and no Go test can see it", bare)
		}
	}
}

// The guards that make this tool safe must survive the rewrite. Losing any of them turns a
// grouping tool into a sharing hole.
func TestTheMoveGuardsSurvive(t *testing.T) {
	fn := moveBookBody(t)
	for _, want := range []struct{ frag, why string }{
		{"b.is_bible=false", "a hidden world bible could be re-homed, breaking the single-bible invariant"},
		{"b.kind<>'diary'", "a diary could be moved into a shareable world — a back-door share"},
		{"b.lifecycle_state!='purge_pending'", "a book queued for purge could be moved"},
		{"errNoSuchWorld", "a foreign world would be distinguishable from a missing one"},
		{`errors.New("failed to resolve world")`, "a transient DB error would masquerade as a missing world"},
		{`errors.New("book not found or not movable")`, "the uniform refusal is gone"},
	} {
		if !strings.Contains(fn, want.frag) {
			t.Errorf("lost %q: %s", want.frag, want.why)
		}
	}
}

// The description is what the model reads. It must describe the reverse now that it exists.
func TestTheMoveDescriptionDocumentsTheReverse(t *testing.T) {
	src := mustReadFile(t, "mcp_worlds.go")
	i := strings.Index(src, `addTool(srv, "world_move_book",`)
	if i < 0 {
		t.Fatal("world_move_book is not registered")
	}
	desc := src[i:]
	if j := strings.Index(desc, "lwmcp.NewToolMeta"); j > 0 {
		desc = desc[:j]
	}
	if !strings.Contains(desc, "clear_world=true") {
		t.Error("the description does not mention clear_world, so an agent has no way to learn " +
			"the reverse exists")
	}
}

func moveBookBody(t *testing.T) string {
	t.Helper()
	src := mustReadFile(t, "mcp_worlds.go")
	i := strings.Index(src, "func (s *Server) toolWorldMoveBook")
	if i < 0 {
		t.Fatal("toolWorldMoveBook is gone")
	}
	fn := src[i:]
	if j := strings.Index(fn, "\nfunc "); j > 0 {
		fn = fn[:j]
	}
	return fn
}
