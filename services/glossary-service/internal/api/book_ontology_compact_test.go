package api

import (
	"encoding/json"
	"strings"
	"testing"
)

func sp(s string) *string { return &s }

// A realistic-ish ontology: one kind with several heavy attributes (long auto_fill_prompt +
// description — the actual bloat), so the compact projection has something material to cut.
func heavyOntology() *bookOntologyResp {
	longPrompt := sp(strings.Repeat("Given the surrounding chapter context, infer the value for this attribute and explain your reasoning in detail. ", 12))
	longDesc := sp(strings.Repeat("A richly documented attribute description that a reader does not need in order to patch it. ", 8))
	attrs := make([]bookAttrResp, 0, 20)
	for i := 0; i < 20; i++ {
		attrs = append(attrs, bookAttrResp{
			AttrID:         "attr-id-" + string(rune('a'+i)),
			KindID:         "kind-1",
			GenreID:        "genre-1",
			Code:           "attr_" + string(rune('a'+i)),
			Name:           "Attribute " + string(rune('A'+i)),
			Description:    longDesc,
			FieldType:      "text",
			IsRequired:     i%2 == 0,
			Options:        []string{"one", "two", "three", "four", "five"},
			AutoFillPrompt: longPrompt,
			BaseVersion:    "2026-07-14T00:00:0" + string(rune('0'+(i%10))) + "Z",
		})
	}
	return &bookOntologyResp{
		BookID: "book-1",
		Genres: []bookGenreResp{{GenreID: "genre-1", Code: "universal", Name: "Universal", BaseVersion: "2026-07-14T00:00:00Z"}},
		Kinds:  []bookKindResp{{BookKindID: "kind-1", Code: "character", Name: "Character", Description: longDesc, BaseVersion: "2026-07-14T00:00:01Z"}},
		Attributes: attrs,
	}
}

// The whole point: the compact projection must be MATERIALLY smaller. If a future edit re-inlines
// the heavy fields, this reds instead of silently shipping the 117KB bloat again.
func TestCompactOntology_IsMateriallySmaller(t *testing.T) {
	ont := heavyOntology()
	fullJSON, _ := json.Marshal(ont)
	compactJSON, _ := json.Marshal(compactBookOntologyOf(ont))
	if len(compactJSON) >= len(fullJSON) {
		t.Fatalf("compact (%d) must be smaller than full (%d)", len(compactJSON), len(fullJSON))
	}
	// The heavy fields are the bloat; require a real cut, not a rounding difference.
	if len(compactJSON)*2 > len(fullJSON) {
		t.Fatalf("compact (%d) should be <50%% of full (%d) — the auto_fill_prompt/description/"+
			"options bloat was not actually dropped", len(compactJSON), len(fullJSON))
	}
	// And the heavy fields must be gone from the wire entirely.
	s := string(compactJSON)
	for _, banned := range []string{"auto_fill_prompt", "translation_hint", "options", "merge_strategy", "attr_id"} {
		if strings.Contains(s, banned) {
			t.Errorf("compact ontology still carries %q — that is the bloat this fix removes", banned)
		}
	}
}

// The CARE the debt row demanded: patch-ability survives. Every row keeps its base_version and its
// code identifiers, so a read→glossary_book_patch flow works without a re-read.
func TestCompactOntology_PreservesPatchIdentityAndBaseVersion(t *testing.T) {
	c := compactBookOntologyOf(heavyOntology())

	if len(c.Genres) != 1 || c.Genres[0].BaseVersion == "" || c.Genres[0].Code != "universal" {
		t.Fatalf("genre lost its code/base_version: %+v", c.Genres)
	}
	if len(c.Kinds) != 1 {
		t.Fatalf("want 1 kind, got %d", len(c.Kinds))
	}
	k := c.Kinds[0]
	if k.Code != "character" || k.BaseVersion == "" {
		t.Fatalf("kind lost code/base_version: %+v", k)
	}
	if k.AttributeCount != 20 {
		t.Fatalf("attribute_count = %d, want 20 (the count/summary replacing inlined defs)", k.AttributeCount)
	}
	if len(c.Attributes) != 20 {
		t.Fatalf("want 20 compact attributes (patch needs each one's base_version), got %d", len(c.Attributes))
	}
	for _, a := range c.Attributes {
		if a.BaseVersion == "" {
			t.Fatalf("attribute %q lost its base_version — glossary_book_patch(level=attribute) is now un-completable", a.Code)
		}
		if a.KindCode != "character" {
			t.Fatalf("attribute %q lost its kind_code (resolved from kind_id) — patch cannot target it: %+v", a.Code, a)
		}
		if a.GenreCode != "universal" {
			t.Fatalf("attribute %q lost its genre_code: %+v", a.Code, a)
		}
	}
}

func TestCompactOntology_NilIsNil(t *testing.T) {
	if compactBookOntologyOf(nil) != nil {
		t.Fatal("nil ontology must project to nil")
	}
}
