package api

import (
	"encoding/json"
	"testing"
)

func decodeTiptapDoc(t *testing.T, raw json.RawMessage) []map[string]any {
	t.Helper()
	var doc struct {
		Type    string           `json:"type"`
		Content []map[string]any `json:"content"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("invalid doc json: %v", err)
	}
	if doc.Type != "doc" {
		t.Fatalf("root type = %q, want doc", doc.Type)
	}
	return doc.Content
}

func TestMarkdownToTiptapJSON_HeadingsAndParagraphs(t *testing.T) {
	nodes := decodeTiptapDoc(t, markdownToTiptapJSON("### Sự ghẻ lạnh\n\nĐoạn một.\n\nĐoạn hai."))
	if len(nodes) != 3 {
		t.Fatalf("want 3 nodes, got %d", len(nodes))
	}
	if nodes[0]["type"] != "heading" {
		t.Errorf("node0 type = %v, want heading", nodes[0]["type"])
	}
	if lvl := nodes[0]["attrs"].(map[string]any)["level"].(float64); lvl != 3 {
		t.Errorf("node0 level = %v, want 3", lvl)
	}
	if nodes[0]["_text"] != "Sự ghẻ lạnh" {
		t.Errorf("node0 _text = %v", nodes[0]["_text"])
	}
	if nodes[1]["type"] != "paragraph" || nodes[2]["type"] != "paragraph" {
		t.Errorf("nodes 1,2 should be paragraphs: %v %v", nodes[1]["type"], nodes[2]["type"])
	}
}

func TestMarkdownToTiptapJSON_ClampAndProseInSameBlock(t *testing.T) {
	// level clamp (##### -> 3) + heading directly followed by prose in one block.
	nodes := decodeTiptapDoc(t, markdownToTiptapJSON("##### Deep\nProse right after."))
	if len(nodes) != 2 {
		t.Fatalf("want 2 nodes, got %d", len(nodes))
	}
	if lvl := nodes[0]["attrs"].(map[string]any)["level"].(float64); lvl != 3 {
		t.Errorf("level clamp failed: got %v, want 3", lvl)
	}
	if nodes[1]["type"] != "paragraph" || nodes[1]["_text"] != "Prose right after." {
		t.Errorf("prose paragraph wrong: %v", nodes[1])
	}
}

func TestMarkdownToTiptapJSON_PlainJoinAndEmpty(t *testing.T) {
	nodes := decodeTiptapDoc(t, markdownToTiptapJSON("Just a line.\nWrapped."))
	if len(nodes) != 1 || nodes[0]["type"] != "paragraph" || nodes[0]["_text"] != "Just a line. Wrapped." {
		t.Errorf("plain join wrong: %v", nodes)
	}
	empty := decodeTiptapDoc(t, markdownToTiptapJSON(""))
	if len(empty) != 1 || empty[0]["type"] != "paragraph" {
		t.Errorf("empty should be 1 paragraph, got %v", empty)
	}
}

func TestNormalizeBodyToTiptap(t *testing.T) {
	rawMd, _ := json.Marshal("## Title\n\nBody.")
	doc, format := normalizeBodyToTiptap(rawMd, "markdown")
	if format != "json" {
		t.Fatalf("format = %q, want json", format)
	}
	if decodeTiptapDoc(t, doc)[0]["type"] != "heading" {
		t.Errorf("markdown was not parsed into blocks")
	}

	// json body is passed through verbatim.
	docIn := json.RawMessage(`{"type":"doc","content":[]}`)
	out, f2 := normalizeBodyToTiptap(docIn, "json")
	if f2 != "json" || string(out) != string(docIn) {
		t.Errorf("json passthrough failed: %s", out)
	}
}
