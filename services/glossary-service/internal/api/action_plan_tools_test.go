package api

import (
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// extractJSONObject must pull the JSON object out of the messy reality of model
// output: bare, fenced (with/without a language tag), and prose-wrapped (§15).
func TestExtractJSONObject(t *testing.T) {
	cases := []struct{ name, in, want string }{
		{"plain", `{"ops":[]}`, `{"ops":[]}`},
		{"fenced_json", "```json\n{\"ops\":[]}\n```", `{"ops":[]}`},
		{"fenced_no_lang", "```\n{\"a\":1}\n```", `{"a":1}`},
		{"prose_wrapped", "Here is the plan:\n{\"ops\":[]}\nDone.", `{"ops":[]}`},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := strings.TrimSpace(extractJSONObject(c.in)); got != c.want {
				t.Fatalf("extractJSONObject(%q) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

// parseAndValidatePlan exercises the DB-free path: JSON parse → build Plan → the
// glossary registry's ValidatePlan (slug/name/description gates, id assignment) and
// the "nothing to do" outcome. No pool is touched (ValidatePlan calls only the pure
// IdentityKey/Validate funcs, never a Handler), so a zero Server suffices.
func TestParseAndValidatePlan(t *testing.T) {
	s := &Server{}
	bookID := uuid.New()

	good := `{"ops":[{"type":"create_kinds","params":{"kinds":[{"code":"character","name":"Character","attributes":[{"code":"role","name":"Role","description":"the character's narrative role","field_type":"text"}]}]}}]}`
	plan, err := s.parseAndValidatePlan(bookID, "build", good)
	if err != nil {
		t.Fatalf("valid plan rejected: %v", err)
	}
	if len(plan.Ops) != 1 || plan.Ops[0].ID != "op-1" {
		t.Fatalf("unexpected plan: %+v", plan)
	}

	// Empty ops → nothing-actionable, carrying notes (MED-3).
	_, err = s.parseAndValidatePlan(bookID, "build", `{"ops":[],"notes":["already covered by existing kinds"]}`)
	if !errors.Is(err, errPlanNothingActionable) {
		t.Fatalf("empty plan: want errPlanNothingActionable, got %v", err)
	}

	// Bad slug → a validation error that is NOT nothing-actionable (so repair runs).
	bad := `{"ops":[{"type":"create_kinds","params":{"kinds":[{"code":"Bad Code","name":"X","attributes":[{"code":"a","name":"A","description":"d"}]}]}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "build", bad); err == nil || errors.Is(err, errPlanNothingActionable) {
		t.Fatalf("bad slug: want a validation error, got %v", err)
	}

	// Empty attribute name → rejected (MED-5).
	noName := `{"ops":[{"type":"create_kinds","params":{"kinds":[{"code":"c","name":"C","attributes":[{"code":"a","name":"","description":"d"}]}]}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "build", noName); err == nil {
		t.Fatalf("empty attribute name: want a validation error")
	}

	// Empty kind name → rejected (MED-5).
	noKindName := `{"ops":[{"type":"create_kinds","params":{"kinds":[{"code":"c","name":"","attributes":[{"code":"a","name":"A","description":"d"}]}]}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "build", noKindName); err == nil {
		t.Fatalf("empty kind name: want a validation error")
	}

	// Unknown op type → rejected.
	unknown := `{"ops":[{"type":"frobnicate","params":{}}]}`
	if _, err := s.parseAndValidatePlan(bookID, "build", unknown); err == nil {
		t.Fatalf("unknown op: want a validation error")
	}

	// Non-JSON output → parse error.
	if _, err := s.parseAndValidatePlan(bookID, "build", "I cannot help with that."); err == nil {
		t.Fatalf("non-JSON: want a parse error")
	}
}
