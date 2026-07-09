package api

import (
	"strings"
	"testing"
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

// normalize maps the MCP input to the internal shape: empty title defaults to slug,
// and an agent-proposed workflow is ALWAYS user-tier (no cross-tenant book-tier vector).
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
	// Tenancy: an agent proposal is ALWAYS user-tier (private to the proposer) —
	// book-tier is cross-tenant and grant-gated, never reachable from the MCP arg.
	if wf.Tier != "user" || wf.BookID != nil {
		t.Fatalf("agent proposal must be user-tier with no book_id, got tier=%q bookID=%v", wf.Tier, wf.BookID)
	}
}

// stepsToJSON defaults an empty gate to "none" so the runner reads a canonical shape.
func TestStepsToJSON_DefaultsGate(t *testing.T) {
	b := stepsToJSON([]workflowStepIn{{ID: "s1", Tool: "t"}})
	if !strings.Contains(string(b), `"gate":"none"`) {
		t.Fatalf("empty gate should default to none, got %s", b)
	}
}
