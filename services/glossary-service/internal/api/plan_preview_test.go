package api

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/uuid"

	mcp "github.com/loreweave/loreweave_mcp"
)

// D-PLAN-PREVIEW-COUNT-DRIFT — the create_kinds preview must count "already exist"
// against LITERAL book_kind codes (the domain execute_plan inserts into), NOT the
// alias-folded loadKindMap. An alias of an adopted kind (e.g. "faction"→organization)
// is not a book_kind, so create_kinds creates it; the preview must agree ("new"),
// or the card under-counts what the confirm will actually do.
func TestPreviewCreateKinds_CountsLiteralBookKindCodesNotAliases(t *testing.T) {
	s := &Server{}
	op := mcp.Op{
		Type: "create_kinds",
		Params: json.RawMessage(
			`{"kinds":[{"code":"faction","name":"Faction"},` +
				`{"code":"prophecy","name":"Prophecy"},` +
				`{"code":"character","name":"Character"}]}`),
	}
	// Alias-folded map (what loadKindMap returns): "faction" is present as an ALIAS
	// of an adopted kind, and "character" is a real adopted book kind.
	existingKinds := map[string]uuid.UUID{
		"faction":   uuid.New(),
		"character": uuid.New(),
	}
	// Literal book_kind codes (what loadBookKindCodes returns + what create_kinds
	// inserts against): only "character" is a real book kind.
	bookKindCodes := map[string]struct{}{"character": {}}

	row := s.previewPlanOp(context.Background(), uuid.New(), op, existingKinds, bookKindCodes)

	// faction (alias only) + prophecy are NEW; only character already exists.
	if row.Value != "2 new" {
		t.Fatalf("Value = %q, want %q", row.Value, "2 new")
	}
	if row.Note != "1 already exist (skipped)" {
		t.Fatalf("Note = %q, want %q", row.Note, "1 already exist (skipped)")
	}
}

// All-new (empty book) → every kind counts as new, none skipped.
func TestPreviewCreateKinds_AllNewWhenNoBookKinds(t *testing.T) {
	s := &Server{}
	op := mcp.Op{
		Type:   "create_kinds",
		Params: json.RawMessage(`{"kinds":[{"code":"a","name":"A"},{"code":"b","name":"B"}]}`),
	}
	row := s.previewPlanOp(context.Background(), uuid.New(), op,
		map[string]uuid.UUID{}, map[string]struct{}{})
	if row.Value != "2 new" || row.Note != "0 already exist (skipped)" {
		t.Fatalf("got Value=%q Note=%q, want \"2 new\" / \"0 already exist (skipped)\"", row.Value, row.Note)
	}
}
