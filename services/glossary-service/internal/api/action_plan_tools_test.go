package api

import (
	"errors"
	"reflect"
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

// TOOLV2 LOOP #77 — the planner's notes are an LLM's free text, and they used to be the whole
// user-facing explanation. Two measured calls asking to set every kind's colour and icon were
// refused with "These changes must be performed via the ontology GUI." The first half of that
// claim (the planner has no such op) is true; the second is false, and provably so —
// glossary_book_patch with level="kind" takes color and icon and applies them immediately.
func TestTheNothingToPlanMessageNamesWhatThePlannerCanDo(t *testing.T) {
	s := &Server{}
	got := s.planVocabularyHint("The current ontology planner does not support 'color' or 'icon'")

	// The model's own explanation survives — it says WHY nothing was planned.
	if !strings.Contains(got, "does not support 'color' or 'icon'") {
		t.Fatalf("the planner's note must be kept: %q", got)
	}
	// ...but it no longer gets the last word about what the SYSTEM can do.
	if !strings.Contains(got, "glossary_book_patch") {
		t.Errorf("the refusal must name the tool that DOES edit a single field: %q", got)
	}
	if !strings.Contains(got, "color and icon") {
		t.Errorf("the exact capability the model despaired of must be named: %q", got)
	}
	// The vocabulary is ENUMERATED from the registry, not re-typed — so it stays true when an
	// op is added. Every op the registry declares must appear.
	for op := range (&Server{}).planRegistry() {
		if !strings.Contains(got, op) {
			t.Errorf("op %q is in the registry but missing from the hint: %q", op, got)
		}
	}
}

// The guard that matters, and the one the first version of this file lacked: the hint has to
// reach the ERROR the caller receives. A test that calls planVocabularyHint directly proves the
// helper and not its wiring — it stayed green when the call site was reverted to the bare note.
func TestTheNothingToPlanERROR_CarriesTheVocabulary(t *testing.T) {
	s := &Server{}
	bookID := uuid.New()
	_, err := s.parseAndValidatePlan(bookID, "recolour every kind",
		`{"ops":[],"notes":["The current ontology planner does not support 'color' or 'icon'. These changes must be performed via the ontology GUI."]}`)
	if !errors.Is(err, errPlanNothingActionable) {
		t.Fatalf("want errPlanNothingActionable, got %v", err)
	}
	got := err.Error()
	if !strings.Contains(got, "glossary_book_patch") {
		t.Fatalf("the refusal the CALLER sees must name the tool that does it — an LLM's "+
			"claim that a GUI is required cannot be the last word: %q", got)
	}
	if !strings.Contains(got, "create_kinds") {
		t.Errorf("the planner's own op vocabulary must reach the caller: %q", got)
	}
	if !strings.Contains(got, "ontology GUI") {
		t.Errorf("the planner's note must survive — it explains WHY nothing was planned: %q", got)
	}
}

func TestTheHintIsSortedSoTheSameRefusalReadsTheSameTwice(t *testing.T) {
	s := &Server{}
	if a, b := s.planVocabularyHint("x"), s.planVocabularyHint("x"); a != b {
		t.Fatalf("map iteration leaked into the message:\n%q\n%q", a, b)
	}
}

// TOOLV2 LOOP #82 — a model sent type="edit_kind" to glossary_propose_batch (4 calls, 3
// sessions, the last on 2026-07-29). The enum rejection lists the nine valid op types, which
// says what the model cannot do and leaves it to guess where the capability went. It is
// glossary_book_patch, and the op-type schema now says so BEFORE the call is composed.
func TestTheOpTypeSchemaNamesTheToolThatEditsAnExistingRow(t *testing.T) {
	f, ok := reflect.TypeOf(proposeBatchOpIn{}).FieldByName("Type")
	if !ok {
		t.Fatal("proposeBatchOpIn has no Type field")
	}
	desc := f.Tag.Get("jsonschema")

	// Every op the registry declares must still be listed — the pointer must not replace the
	// vocabulary, only follow it.
	for op := range (&Server{}).planRegistry() {
		if !strings.Contains(desc, op) {
			t.Errorf("op %q is in the registry but missing from the schema description", op)
		}
	}
	if !strings.Contains(desc, "glossary_book_patch") {
		t.Errorf("the schema must name where a single-field edit actually lives: %q", desc)
	}
	if !strings.Contains(desc, "edit_kind") {
		t.Errorf("the op the model actually invented must be named as absent: %q", desc)
	}
}
