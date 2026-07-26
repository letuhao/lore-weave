package api

import "testing"

// W0 soak (live-caught): the tolerance-shim `changes` items must ADMIT the extra
// fields weak models tack on (old_value, field_label, …). The struct infers
// additionalProperties:false, so without relaxItemsAdditionalProps the whole
// patch call is schema-REJECTED before normalizeBookPatchDiff can run — gemma
// sent changes:[{target,new_value,old_value,field_label}] and every patch died.
func TestBookPatchSchema_ChangesItemsAdmitExtraFields(t *testing.T) {
	schema := relaxAdditionalProps(
		closedSetSchemaFor[bookPatchToolIn](map[string][]any{
			"level": enumLevels, "field_type": enumFieldTypes,
		}),
		"changes[]",
	)
	resolved, err := schema.Resolve(nil)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	args := map[string]any{
		"book_id": "019eeb09-a4aa-7acf-9281-e812d7975a6c",
		"level":   "kind",
		"code":    "faction",
		"changes": []any{map[string]any{
			"target": "name", "new_value": "Group",
			"old_value": "Faction", "field_label": "Name", // the extras that used to fail
		}},
	}
	if err := resolved.Validate(args); err != nil {
		t.Fatalf("changes with extra fields must validate (tolerance shim), got: %v", err)
	}
}

// propose_batch (100%-error in the W0 baseline): weak models add a stray `type`
// at the ROOT and extras on op items. The op-type ENUM must stay strict while
// unknown extras are admitted.
func TestProposeBatchSchema_AdmitsRootAndOpExtras_KeepsTypeEnum(t *testing.T) {
	schema := relaxAdditionalProps(
		closedSetSchemaFor[proposeBatchToolIn](map[string][]any{
			"ops[].type": {"adopt_genres", "create_kinds", "add_attributes", "edit_attribute",
				"delete_genre", "delete_kind", "delete_attribute", "merge_candidate", "dismiss_candidate"},
		}),
		"", "ops[]",
	)
	resolved, err := schema.Resolve(nil)
	if err != nil {
		t.Fatalf("resolve: %v", err)
	}
	// A root `type` + an op-item extra `note` must now validate.
	ok := map[string]any{
		"book_id": "019eeb09-a4aa-7acf-9281-e812d7975a6c",
		"type":    "batch", // stray root extra weak models emit
		"ops": []any{map[string]any{
			"type": "create_kinds", "params": map[string]any{"kinds": []any{}},
			"note": "an extra field", // op-item extra
		}},
	}
	if err := resolved.Validate(ok); err != nil {
		t.Fatalf("root+op extras must validate, got: %v", err)
	}
	// But a BAD op type must still be rejected (the enum stays strict).
	bad := map[string]any{
		"book_id": "019eeb09-a4aa-7acf-9281-e812d7975a6c",
		"ops":     []any{map[string]any{"type": "not_a_real_op", "params": map[string]any{}}},
	}
	if err := resolved.Validate(bad); err == nil {
		t.Fatalf("an off-enum op type must still be rejected")
	}
}

// F3a — glossary_book_patch tolerates the entity-edit diff shape weaker models
// emit ({changes:[{target/field_label, new_value}]}) instead of flat fields.
// normalizeBookPatchDiff folds it onto the flat fields (nil-only) and drops the
// base_version (the diff shape means the version was never read).

func strp(s string) *string { return &s }

func TestNormalizeBookPatchDiff_MapsDescriptionAndDropsBaseVersion(t *testing.T) {
	in := bookPatchToolIn{
		Level: "attribute", Code: "appearance", KindCode: "character", GenreCode: "universal",
		BaseVersion: "2025-02-11T14:30:00Z", // hallucinated — must be dropped
		Changes: []bookPatchChange{
			{Target: "short_description", NewValue: strp("The character's physical appearance.")},
		},
	}
	n := normalizeBookPatchDiff(&in)
	if n != 1 {
		t.Fatalf("mapped = %d, want 1", n)
	}
	if in.Description == nil || *in.Description != "The character's physical appearance." {
		t.Fatalf("description not mapped from the diff: %v", in.Description)
	}
	if in.BaseVersion != "" {
		t.Fatalf("base_version should be cleared on a diff-shape patch, got %q", in.BaseVersion)
	}
}

func TestNormalizeBookPatchDiff_FlatFieldWins(t *testing.T) {
	// An explicit flat field is never overwritten by a diff entry for the same field.
	in := bookPatchToolIn{
		Level: "attribute", Code: "appearance",
		Description: strp("flat wins"),
		Changes:     []bookPatchChange{{FieldLabel: "Description", NewValue: strp("diff loses")}},
	}
	normalizeBookPatchDiff(&in)
	if in.Description == nil || *in.Description != "flat wins" {
		t.Fatalf("flat field must win over the diff, got %v", in.Description)
	}
}

func TestNormalizeBookPatchDiff_FieldLabelAndNameAndFieldType(t *testing.T) {
	in := bookPatchToolIn{
		Level: "attribute", Code: "x",
		Changes: []bookPatchChange{
			{FieldLabel: "Name", NewValue: strp("Appearance")},
			{Target: "field_type", Value: strp("textarea")},
			{Field: "auto_fill_prompt", NewValue: strp("Pull the look from the text.")},
		},
	}
	n := normalizeBookPatchDiff(&in)
	if n != 3 {
		t.Fatalf("mapped = %d, want 3", n)
	}
	if in.Name == nil || *in.Name != "Appearance" {
		t.Fatalf("name not mapped: %v", in.Name)
	}
	if in.FieldType == nil || *in.FieldType != "textarea" {
		t.Fatalf("field_type not mapped: %v", in.FieldType)
	}
	if in.AutoFillPrompt == nil || *in.AutoFillPrompt != "Pull the look from the text." {
		t.Fatalf("auto_fill_prompt not mapped: %v", in.AutoFillPrompt)
	}
}

func TestNormalizeBookPatchDiff_NoChangesIsNoop(t *testing.T) {
	in := bookPatchToolIn{Level: "attribute", Code: "x", Description: strp("d"), BaseVersion: "v1"}
	n := normalizeBookPatchDiff(&in)
	if n != 0 {
		t.Fatalf("mapped = %d, want 0", n)
	}
	if in.BaseVersion != "v1" {
		t.Fatalf("base_version must be preserved when no diff was consumed, got %q", in.BaseVersion)
	}
}
