package api

import "testing"

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
