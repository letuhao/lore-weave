package api

import (
	"encoding/json"
	"testing"
)

// scenes_test.go — P2 unit tests for the Tiptap-to-plain-text helper.
//
// Handler-level tests (DB round-trip) deferred to live smoke per the
// memory feedback_mock_only_coverage_hides_crossservice_bugs (pgx mock
// is heavy; live smoke catches the real surface).

func TestTiptapJSONToPlainText_SimpleDocument(t *testing.T) {
	t.Parallel()
	doc := `{
	  "type": "doc",
	  "content": [
	    {"type":"paragraph","content":[{"type":"text","text":"First paragraph."}]},
	    {"type":"paragraph","content":[{"type":"text","text":"Second paragraph."}]}
	  ]
	}`
	out := tiptapJSONToPlainText([]byte(doc))
	want := "First paragraph.\n\nSecond paragraph."
	if out != want {
		t.Errorf("output mismatch:\n got: %q\nwant: %q", out, want)
	}
}

func TestTiptapJSONToPlainText_InlineMarks(t *testing.T) {
	t.Parallel()
	// Inline marks (bold, italic) wrap text nodes; algorithm should
	// concatenate them naturally as one paragraph.
	doc := `{
	  "type":"doc",
	  "content":[
	    {"type":"paragraph","content":[
	      {"type":"text","text":"Hello "},
	      {"type":"text","text":"bold","marks":[{"type":"bold"}]},
	      {"type":"text","text":" world."}
	    ]}
	  ]
	}`
	out := tiptapJSONToPlainText([]byte(doc))
	want := "Hello bold world."
	if out != want {
		t.Errorf("output mismatch:\n got: %q\nwant: %q", out, want)
	}
}

func TestTiptapJSONToPlainText_HardBreakNewline(t *testing.T) {
	t.Parallel()
	doc := `{
	  "type":"doc",
	  "content":[
	    {"type":"paragraph","content":[
	      {"type":"text","text":"Line one"},
	      {"type":"hardBreak"},
	      {"type":"text","text":"Line two"}
	    ]}
	  ]
	}`
	out := tiptapJSONToPlainText([]byte(doc))
	want := "Line one\nLine two"
	if out != want {
		t.Errorf("output mismatch:\n got: %q\nwant: %q", out, want)
	}
}

func TestTiptapJSONToPlainText_MalformedReturnsEmpty(t *testing.T) {
	t.Parallel()
	out := tiptapJSONToPlainText([]byte("not valid json {{{"))
	if out != "" {
		t.Errorf("expected empty string on malformed JSON, got: %q", out)
	}
}

func TestTiptapJSONToPlainText_EmptyDoc(t *testing.T) {
	t.Parallel()
	doc := `{"type":"doc","content":[]}`
	out := tiptapJSONToPlainText([]byte(doc))
	if out != "" {
		t.Errorf("expected empty string on empty doc, got: %q", out)
	}
}

func TestTiptapJSONToPlainText_NestedBlocks(t *testing.T) {
	t.Parallel()
	// Blockquote containing a paragraph — both have content arrays.
	doc := `{
	  "type":"doc",
	  "content":[
	    {"type":"blockquote","content":[
	      {"type":"paragraph","content":[{"type":"text","text":"Quoted text."}]}
	    ]},
	    {"type":"paragraph","content":[{"type":"text","text":"Outer paragraph."}]}
	  ]
	}`
	out := tiptapJSONToPlainText([]byte(doc))
	// Blockquote paragraph + outer paragraph each form a block; "Quoted text." gets walked recursively.
	if !contains(out, "Quoted text.") || !contains(out, "Outer paragraph.") {
		t.Errorf("missing text in output: %q", out)
	}
}

// contains is a simple substring check helper.
func contains(haystack, needle string) bool {
	return jsonStringContains(haystack, needle)
}

func jsonStringContains(haystack, needle string) bool {
	// Use json escape to avoid trickery; plain strings.Contains is fine here.
	_ = json.RawMessage{}
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
