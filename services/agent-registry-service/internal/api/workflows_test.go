package api

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

func okStep() workflowStepIn {
	return workflowStepIn{ID: "search", Tool: "glossary_search", Gate: "none"}
}

func baseWorkflow() *workflowInput {
	return &workflowInput{
		Slug:        "seed-lore",
		Title:       "Seed lore",
		Description: "Extract entities from a doc and propose them.",
		Surfaces:    []string{"chat"},
		Inputs:      map[string]string{"book_id": "required", "doc": "optional"},
		Steps:       []workflowStepIn{okStep()},
		Tier:        "user",
	}
}

func TestValidateWorkflow_HappyPath(t *testing.T) {
	if msg, ok := validateWorkflow(baseWorkflow()); !ok {
		t.Fatalf("expected valid, got: %s", msg)
	}
}

func TestValidateWorkflow_Rejects(t *testing.T) {
	cases := []struct {
		name  string
		mut   func(*workflowInput)
		wants string
	}{
		{"bad slug", func(w *workflowInput) { w.Slug = "Bad Slug" }, "slug must be"},
		{"empty description", func(w *workflowInput) { w.Description = "  " }, "description is required"},
		{"bad surface", func(w *workflowInput) { w.Surfaces = []string{"nope"} }, "invalid surface"},
		{"bad input req", func(w *workflowInput) { w.Inputs = map[string]string{"x": "maybe"} }, "must be 'required' or 'optional'"},
		{"no steps", func(w *workflowInput) { w.Steps = nil }, "at least one step"},
		{"dup step id", func(w *workflowInput) {
			w.Steps = []workflowStepIn{okStep(), okStep()}
		}, "duplicate step id"},
		{"empty tool", func(w *workflowInput) {
			w.Steps = []workflowStepIn{{ID: "s1", Tool: "", Gate: "none"}}
		}, "tool is required"},
		{"bad gate", func(w *workflowInput) {
			w.Steps = []workflowStepIn{{ID: "s1", Tool: "t", Gate: "maybe"}}
		}, "gate must be"},
		{"bad step id", func(w *workflowInput) {
			w.Steps = []workflowStepIn{{ID: "Bad ID", Tool: "t", Gate: "none"}}
		}, "id must be"},
		{"repeat undeclared input", func(w *workflowInput) {
			w.Steps = []workflowStepIn{{ID: "s1", Tool: "t", Gate: "none", Repeat: "per_item:ghost"}}
		}, "undeclared input"},
		{"repeat malformed", func(w *workflowInput) {
			w.Steps = []workflowStepIn{{ID: "s1", Tool: "t", Gate: "none", Repeat: "loop"}}
		}, "repeat must be"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			wf := baseWorkflow()
			c.mut(wf)
			msg, ok := validateWorkflow(wf)
			if ok {
				t.Fatalf("expected rejection for %q, got valid", c.name)
			}
			if !strings.Contains(msg, c.wants) {
				t.Fatalf("msg %q does not contain %q", msg, c.wants)
			}
		})
	}
}

func TestValidateWorkflow_RepeatPerItemValid(t *testing.T) {
	wf := baseWorkflow()
	wf.Steps = []workflowStepIn{{ID: "propose", Tool: "glossary_propose_entities", Gate: "approval", Repeat: "per_item:doc"}}
	if msg, ok := validateWorkflow(wf); !ok {
		t.Fatalf("per_item over a declared input should be valid, got: %s", msg)
	}
}

// normalize maps the MCP input to the internal shape: empty title defaults to slug;
// no book_id ⇒ user-tier; a book_id ⇒ book-tier STRUCTURALLY (the cross-tenant grant
// check is enforced separately in toolProposeWorkflow, which has the ctx).
func TestProposeWorkflowIn_Normalize(t *testing.T) {
	in := proposeWorkflowIn{
		Slug: "my-flow", Description: "does a thing",
		Steps: []workflowStepIn{okStep()},
	}
	wf, msg := in.normalize()
	if msg != "" {
		t.Fatalf("expected ok, got: %s", msg)
	}
	if wf.Title != "my-flow" {
		t.Fatalf("empty title should default to slug, got %q", wf.Title)
	}
	if wf.Tier != "user" || wf.BookID != nil {
		t.Fatalf("no book_id ⇒ user-tier, got tier=%q bookID=%v", wf.Tier, wf.BookID)
	}

	in.BookID = "019ef2cf-4317-7edb-8f33-d3b2c5845d0c"
	wf, msg = in.normalize()
	if msg != "" || wf.Tier != "book" || wf.BookID == nil {
		t.Fatalf("valid book_id ⇒ book-tier (structural), got tier=%q bookID=%v msg=%q", wf.Tier, wf.BookID, msg)
	}

	in.BookID = "not-a-uuid"
	if _, msg := in.normalize(); msg != "invalid book_id" {
		t.Fatalf("bad book_id should fail validation, got %q", msg)
	}
}

// stepsToJSON defaults an empty gate to "none" so the runner reads a canonical shape.
// bookGrantOK fails CLOSED when no grant client is wired — a book-tier write must never
// slip through unauthorized just because grant resolution is unavailable.
func TestBookGrantOK_FailsClosedWithoutGrantClient(t *testing.T) {
	s := &Server{} // grants == nil
	ok, why := s.bookGrantOK(context.Background(), uuid.New(), uuid.New(), grantclient.GrantEdit)
	if ok {
		t.Fatal("must fail closed when grants is nil")
	}
	if why == "" {
		t.Fatal("should return a reason")
	}
	// and a nil book id is rejected too
	if ok, _ := s.bookGrantOK(context.Background(), uuid.Nil, uuid.New(), grantclient.GrantView); ok {
		t.Fatal("nil book id must not pass")
	}
}

func TestStepsToJSON_DefaultsGate(t *testing.T) {
	b := stepsToJSON([]workflowStepIn{{ID: "s1", Tool: "t"}})
	if !strings.Contains(string(b), `"gate":"none"`) {
		t.Fatalf("empty gate should default to none, got %s", b)
	}
}

// ── Track C Phase 2 — done_when (the rail driver's artifact predicate) ───────

func TestDoneWhen_Valid(t *testing.T) {
	for _, expr := range []string{
		"cast > 0", "categories >= 1", "plan>0", "  prose  >  0  ",
		"connections > 3", "chapters >= 10",
		// drain predicates (entity-triage): done when the pile shrinks to empty
		"suggestions < 1", "suggestions <= 0", "suggestions == 0", "cast < 5",
	} {
		w := baseWorkflow()
		w.Steps[0].DoneWhen = expr
		if msg, ok := validateWorkflow(w); !ok {
			t.Fatalf("expected %q to be a valid done_when, got: %s", expr, msg)
		}
	}
}

func TestDoneWhen_RejectsAnythingOutsideTheClosedGrammar(t *testing.T) {
	// An unparseable predicate can never mark a step done, so the agent would redo that
	// step forever while the author got a cheerful 200. Reject it at the write.
	for _, expr := range []string{
		"entities > 0",         // not a known key (the key is `cast`)
		"cast",                 // no operator
		"cast > ",              // no threshold
		"cast != 5",            // unsupported operator (!= is not in the closed set)
		"cast > 0; DROP TABLE", // not an eval surface, and never will be
		"len(cast) > 0",
	} {
		w := baseWorkflow()
		w.Steps[0].DoneWhen = expr
		if msg, ok := validateWorkflow(w); ok {
			t.Fatalf("expected %q to be REJECTED, but it validated (msg=%q)", expr, msg)
		}
	}
}

// The drop-on-serialize trap: `steps` round-trips through json.Unmarshal into
// []workflowStepIn, so a field that is not declared on the struct is SILENTLY dropped on
// the way out to chat-service. done_when would then be authored, stored, and invisible —
// the rail driver would never see it and would silently fall back to the call log. This
// test fails if anyone removes the struct field.
func TestDoneWhen_SurvivesTheStepsRoundTrip(t *testing.T) {
	raw := []byte(`[{"id":"save-cast","tool":"glossary_propose_entities","gate":"none","done_when":"cast > 0"}]`)
	var steps []workflowStepIn
	if err := json.Unmarshal(raw, &steps); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if len(steps) != 1 || steps[0].DoneWhen != "cast > 0" {
		t.Fatalf("done_when was DROPPED by the steps round-trip: %+v", steps)
	}
	// Re-serialize and decode again. (Assert on the DECODED value, not the raw bytes:
	// encoding/json HTML-escapes ">" to >, which is transparent to any JSON parser —
	// a byte-level assertion here would fail for a reason that has nothing to do with the
	// field surviving.)
	out, err := json.Marshal(steps)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var back []workflowStepIn
	if err := json.Unmarshal(out, &back); err != nil {
		t.Fatalf("re-unmarshal: %v", err)
	}
	if len(back) != 1 || back[0].DoneWhen != "cast > 0" {
		t.Fatalf("done_when did not survive re-serialization: %s", out)
	}
}
