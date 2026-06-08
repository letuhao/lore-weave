package api

import (
	"testing"

	"github.com/google/uuid"
)

func TestValidateSearchQuery(t *testing.T) {
	t.Parallel()
	if _, msg := validateSearchQuery(""); msg == "" {
		t.Fatal("empty query must be rejected")
	}
	if _, msg := validateSearchQuery("   \t "); msg == "" {
		t.Fatal("whitespace-only query must be rejected")
	}
	if q, msg := validateSearchQuery("  乾坤圈 "); msg != "" || q != "乾坤圈" {
		t.Fatalf("expected trimmed q=乾坤圈, msg='', got q=%q msg=%q", q, msg)
	}
	long := make([]rune, maxSearchQueryRunes+1)
	for i := range long {
		long[i] = 'a'
	}
	if _, msg := validateSearchQuery(string(long)); msg == "" {
		t.Fatal("over-length query must be rejected")
	}
	// exactly at the cap is allowed
	atCap := make([]rune, maxSearchQueryRunes)
	for i := range atCap {
		atCap[i] = 'a'
	}
	if _, msg := validateSearchQuery(string(atCap)); msg != "" {
		t.Fatalf("query at the cap must be allowed, got msg=%q", msg)
	}
}

func TestValidateSurface(t *testing.T) {
	t.Parallel()
	// "" + "draft" normalise to "draft"; canon/all pass through.
	for in, want := range map[string]string{"": "draft", "draft": "draft", "canon": "canon", "all": "all"} {
		got, msg := validateSurface(in)
		if msg != "" || got != want {
			t.Fatalf("surface %q -> (%q,%q), want (%q,\"\")", in, got, msg, want)
		}
	}
	for _, bad := range []string{"drafts", "DRAFT", "garbage", "publish"} {
		if _, msg := validateSurface(bad); msg == "" {
			t.Fatalf("surface %q should be rejected", bad)
		}
	}
}

func TestBuildLexicalHit(t *testing.T) {
	t.Parallel()
	cid := uuid.New()
	title := "第5章 龙象般若"
	// exact substring → boosted score + relevance 1.0 + a highlight span
	hit := buildLexicalHit(cid, &title, nil, 5, 2, "他修炼龙象般若掌", 0.4, "龙象般若", "draft")
	if hit["surface"] != "draft" || hit["matchType"] != "lexical" {
		t.Fatalf("surface/matchType wrong: %v / %v", hit["surface"], hit["matchType"])
	}
	if hit["score"].(float64) != 1.4 {
		t.Fatalf("exact score = %v, want 1.4 (1+sim)", hit["score"])
	}
	if hit["relevance"].(float64) != 1.0 {
		t.Fatalf("exact relevance = %v, want 1.0", hit["relevance"])
	}
	if len(hit["highlights"].([][]int)) != 1 {
		t.Fatalf("exact match should emit one highlight span, got %v", hit["highlights"])
	}

	// trigram-only (no exact substring) → score=relevance=sim, no highlight
	miss := buildLexicalHit(cid, &title, nil, 5, 2, "完全不相关的文字", 0.31, "龙象般若", "canon")
	if miss["surface"] != "canon" {
		t.Fatalf("surface should pass through: got %v", miss["surface"])
	}
	if miss["score"].(float64) != 0.31 || miss["relevance"].(float64) != 0.31 {
		t.Fatalf("non-exact score/relevance = %v/%v, want 0.31", miss["score"], miss["relevance"])
	}
	if len(miss["highlights"].([][]int)) != 0 {
		t.Fatalf("non-exact match should emit no highlight, got %v", miss["highlights"])
	}
}

func TestValidateGranularity(t *testing.T) {
	t.Parallel()
	// "" and "chapter" both normalise to the chapter default (navigate).
	for in, want := range map[string]string{"": "chapter", "chapter": "chapter", "block": "block"} {
		got, msg := validateGranularity(in)
		if msg != "" || got != want {
			t.Fatalf("granularity %q -> (%q,%q), want (%q,\"\")", in, got, msg, want)
		}
	}
	for _, bad := range []string{"Chapter", "blocks", "garbage", "page"} {
		if _, msg := validateGranularity(bad); msg == "" {
			t.Fatalf("granularity %q should be rejected", bad)
		}
	}
}

func TestEscapeLikePattern(t *testing.T) {
	t.Parallel()
	cases := map[string]string{
		"乾坤圈":  "%乾坤圈%",
		"100%": `%100\%%`,
		"a_b":  `%a\_b%`,
		`a\b`:  `%a\\b%`,
	}
	for in, want := range cases {
		if got := escapeLikePattern(in); got != want {
			t.Fatalf("escapeLikePattern(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestIndexRunesFold(t *testing.T) {
	t.Parallel()
	idx := func(text, q string) int { return indexRunesFold([]rune(text), []rune(q)) }

	if got := idx("话说乾坤圈是哪吒的法宝", "乾坤圈"); got != 2 {
		t.Fatalf("CJK match rune index = %d, want 2", got)
	}
	if got := idx("The Sword of Truth", "sword"); got != 4 {
		t.Fatalf("case-insensitive ASCII match = %d, want 4", got)
	}
	if got := idx("hello world", "zzz"); got != -1 {
		t.Fatalf("no-match should be -1, got %d", got)
	}
	if got := idx("ab", "abc"); got != -1 {
		t.Fatalf("query longer than text should be -1, got %d", got)
	}
	if got := idx("anything", ""); got != -1 {
		t.Fatalf("empty query should be -1, got %d", got)
	}
	// first of multiple occurrences
	if got := idx("xKEYyKEYz", "KEY"); got != 1 {
		t.Fatalf("first occurrence = %d, want 1", got)
	}
}

func TestComputeHighlight(t *testing.T) {
	t.Parallel()

	// CJK exact match: rune offsets must be exact (ADJ-4).
	hl := computeHighlight("话说乾坤圈是哪吒的法宝", "乾坤圈", searchSnippetWindow)
	if !hl.Matched {
		t.Fatal("expected CJK match")
	}
	if hl.BlockStart != 2 || hl.BlockEnd != 5 {
		t.Fatalf("CJK block offsets = [%d,%d], want [2,5]", hl.BlockStart, hl.BlockEnd)
	}
	// short text < window ⇒ whole text is the snippet, in-snippet == block offsets.
	if hl.Snippet != "话说乾坤圈是哪吒的法宝" || hl.HLStart != 2 || hl.HLEnd != 5 {
		t.Fatalf("CJK snippet/offsets wrong: snippet=%q hl=[%d,%d]", hl.Snippet, hl.HLStart, hl.HLEnd)
	}

	// Windowing + clamping: match in the middle of a long text.
	text := ""
	for i := 0; i < 50; i++ {
		text += "a"
	}
	text += "KEY"
	for i := 0; i < 50; i++ {
		text += "b"
	}
	hl = computeHighlight(text, "KEY", 10) // ctx=5 each side
	if !hl.Matched {
		t.Fatal("expected match in long text")
	}
	if hl.Snippet != "aaaaaKEYbbbbb" {
		t.Fatalf("windowed snippet = %q, want aaaaaKEYbbbbb", hl.Snippet)
	}
	if hl.HLStart != 5 || hl.HLEnd != 8 {
		t.Fatalf("in-snippet offsets = [%d,%d], want [5,8]", hl.HLStart, hl.HLEnd)
	}
	if hl.BlockStart != 50 || hl.BlockEnd != 53 {
		t.Fatalf("in-block offsets = [%d,%d], want [50,53]", hl.BlockStart, hl.BlockEnd)
	}

	// No exact substring ⇒ leading window, no highlight.
	hl = computeHighlight("hello world", "zzz", searchSnippetWindow)
	if hl.Matched || hl.HLStart != 0 || hl.HLEnd != 0 {
		t.Fatalf("no-match should not highlight, got matched=%v hl=[%d,%d]", hl.Matched, hl.HLStart, hl.HLEnd)
	}
	if hl.Snippet != "hello world" {
		t.Fatalf("no-match snippet = %q, want full leading window", hl.Snippet)
	}

	// Match at start: winStart clamps to 0.
	hl = computeHighlight("KEYtail", "key", searchSnippetWindow)
	if !hl.Matched || hl.HLStart != 0 || hl.HLEnd != 3 || hl.BlockStart != 0 {
		t.Fatalf("start-match offsets wrong: matched=%v hl=[%d,%d] blockStart=%d", hl.Matched, hl.HLStart, hl.HLEnd, hl.BlockStart)
	}
}
