package api

import (
	"strings"
	"testing"
)

// Pure unit tests for the raw entity-search helpers (no DB). These mirror the
// chapter raw-search tests (book-service buildLexicalHit/computeHighlight) and
// guard the CJK rune-offset correctness + the field-preference + the sort
// whitelist — the logic /review-impl flagged as the drift-prone surface.

func TestEscapeLikePattern_EscapesMetacharacters(t *testing.T) {
	cases := map[string]string{
		"abc":  `%abc%`,
		"100%": `%100\%%`,
		"a_b":  `%a\_b%`,
		`a\b`:  `%a\\b%`,
		"林黛玉":  "%林黛玉%",
	}
	for in, want := range cases {
		if got := escapeLikePattern(in); got != want {
			t.Errorf("escapeLikePattern(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestIndexRunesFold_CaseInsensitiveRuneOffsets(t *testing.T) {
	// ASCII case-fold.
	if got := indexRunesFold([]rune("Hello World"), []rune("world")); got != 6 {
		t.Errorf("ASCII fold: want 6, got %d", got)
	}
	// CJK: offset is in RUNES not bytes — "玉" sits at rune index 2 even though
	// each CJK char is 3 UTF-8 bytes.
	if got := indexRunesFold([]rune("林黛玉传"), []rune("玉")); got != 2 {
		t.Errorf("CJK rune offset: want 2, got %d", got)
	}
	// Not found.
	if got := indexRunesFold([]rune("abc"), []rune("xyz")); got != -1 {
		t.Errorf("not found: want -1, got %d", got)
	}
	// Empty / too-long query.
	if got := indexRunesFold([]rune("ab"), []rune("")); got != -1 {
		t.Errorf("empty query: want -1, got %d", got)
	}
	if got := indexRunesFold([]rune("ab"), []rune("abc")); got != -1 {
		t.Errorf("query longer than text: want -1, got %d", got)
	}
}

func TestComputeEntityHighlight_ExactAndTrigramOnly(t *testing.T) {
	// Exact substring → Matched with rune-offset span.
	hl := computeEntityHighlight("林黛玉", "黛玉", entitySnippetWindow)
	if !hl.Matched {
		t.Fatal("want Matched=true for exact substring")
	}
	if hl.HLStart != 1 || hl.HLEnd != 3 {
		t.Errorf("CJK highlight span: want [1,3], got [%d,%d]", hl.HLStart, hl.HLEnd)
	}
	// No exact substring → leading window, Matched=false, no span.
	hl2 := computeEntityHighlight("Arthur Pendragon", "zzz", 8)
	if hl2.Matched {
		t.Error("want Matched=false for non-substring")
	}
	if len([]rune(hl2.Snippet)) != 8 {
		t.Errorf("leading window: want 8 runes, got %d (%q)", len([]rune(hl2.Snippet)), hl2.Snippet)
	}
}

func TestBuildEntityMatch_FieldPreference(t *testing.T) {
	// Name match wins over an alias match.
	m := buildEntityMatch("Arthur", []string{"King"}, nil, "Art")
	if m.FieldCode != "name" {
		t.Errorf("name preference: want field=name, got %s", m.FieldCode)
	}
	if len(m.Highlights) != 1 || m.Highlights[0][0] != 0 || m.Highlights[0][1] != 3 {
		t.Errorf("name highlight: want [[0,3]], got %v", m.Highlights)
	}

	// No name hit → falls through to the matching alias.
	m2 := buildEntityMatch("Arthur", []string{"Wart", "King"}, nil, "Kin")
	if m2.FieldCode != "alias" || m2.Snippet != "King" {
		t.Errorf("alias fallthrough: want alias/King, got %s/%s", m2.FieldCode, m2.Snippet)
	}

	// No name/alias hit → translation field (display-language name).
	tr := "Hỏa Ma"
	m3 := buildEntityMatch("火魔", []string{}, &tr, "Hỏa")
	if m3.FieldCode != "translation" {
		t.Errorf("translation fallthrough: want translation, got %s", m3.FieldCode)
	}

	// Trigram-only (nothing exact anywhere) → name field, empty highlight span.
	m4 := buildEntityMatch("Arthur", []string{"King"}, nil, "Arthr")
	if m4.FieldCode != "name" || len(m4.Highlights) != 0 {
		t.Errorf("trigram-only: want name with no highlights, got %s/%v", m4.FieldCode, m4.Highlights)
	}
}

func TestEntityOrderBy_Whitelist(t *testing.T) {
	cases := []struct {
		sort string
		want string // substring that must appear
	}{
		{"", "e.updated_at DESC"},
		{"updated_at", "e.updated_at DESC"},
		{"updated_at_asc", "e.updated_at ASC"},
		{"name", "e.cached_name ASC"},
		{"name_desc", "e.cached_name DESC"},
		{"created_at", "e.created_at DESC"},
		{"created_at_asc", "e.created_at ASC"},
		{"kind", "ek.sort_order ASC"},
		{"status", "e.status ASC"},
		{"alive", "e.alive DESC"},
		{"links", "e.cached_chapter_link_count DESC"},
		{"evidence", "e.cached_evidence_count DESC"},
		{"bogus-value", "e.updated_at DESC"}, // unknown → safe default
	}
	for _, c := range cases {
		got := entityOrderBy(c.sort, false, 0, 0, "")
		if !strings.Contains(got, c.want) {
			t.Errorf("entityOrderBy(%q) = %q, want substring %q", c.sort, got, c.want)
		}
	}
	// Injection safety: an arbitrary attacker-controlled key never reaches the
	// clause — it maps to the safe default, never appears verbatim.
	evil := "updated_at; DROP TABLE glossary_entities;--"
	if got := entityOrderBy(evil, false, 0, 0, ""); got != "ORDER BY e.updated_at DESC" {
		t.Errorf("injection: want safe default, got %q", got)
	}
}

func TestEntityOrderBy_RawRelevance(t *testing.T) {
	// Raw mode with bound args → relevance ordering (exact-first, then similarity).
	got := entityOrderBy("", true, 5, 6, "")
	if !strings.Contains(got, "ILIKE $6") || !strings.Contains(got, "similarity(") {
		t.Errorf("raw relevance order missing exact/similarity legs: %q", got)
	}
	if !strings.Contains(got, "$5") {
		t.Errorf("raw relevance order missing query arg $5: %q", got)
	}
	// Explicit "relevance" behaves the same.
	if g2 := entityOrderBy("relevance", true, 5, 6, ""); g2 != got {
		t.Errorf("relevance != default-raw: %q vs %q", g2, got)
	}
	// Raw mode but unbound args (no query) → falls back to default.
	if g3 := entityOrderBy("", true, 0, 0, ""); !strings.Contains(g3, "e.updated_at DESC") {
		t.Errorf("raw-without-query should default: %q", g3)
	}
	// An explicit column sort in raw mode still wins over relevance.
	if g4 := entityOrderBy("name", true, 5, 6, ""); !strings.Contains(g4, "e.cached_name ASC") {
		t.Errorf("explicit sort in raw mode should win: %q", g4)
	}
	// Display-language translation exact-match joins the exact tier.
	if g5 := entityOrderBy("", true, 5, 6, "EXISTS(SELECT 1 FROM t)"); !strings.Contains(g5, "OR EXISTS(SELECT 1 FROM t)) DESC") {
		t.Errorf("translation-exact not ORed into the exact tier: %q", g5)
	}
}
