package tasks

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestHtmlToTiptapJSON_EmptyInput(t *testing.T) {
	result := htmlToTiptapJSON("")
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}
	if doc["type"] != "doc" {
		t.Errorf("expected doc type, got %v", doc["type"])
	}
}

func TestHtmlToTiptapJSON_Paragraph(t *testing.T) {
	result := htmlToTiptapJSON("<p>Hello world</p>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	if len(content) != 1 {
		t.Fatalf("expected 1 node, got %d", len(content))
	}
	node := content[0].(map[string]any)
	if node["type"] != "paragraph" {
		t.Errorf("expected paragraph, got %v", node["type"])
	}
	if node["_text"] != "Hello world" {
		t.Errorf("expected 'Hello world', got %v", node["_text"])
	}
}

func TestHtmlToTiptapJSON_Headings(t *testing.T) {
	html := "<h1>Title</h1><h2>Subtitle</h2><h3>Section</h3>"
	result := htmlToTiptapJSON(html)
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	if len(content) != 3 {
		t.Fatalf("expected 3 nodes, got %d", len(content))
	}

	tests := []struct {
		level int
		text  string
	}{
		{1, "Title"},
		{2, "Subtitle"},
		{3, "Section"},
	}
	for i, tt := range tests {
		node := content[i].(map[string]any)
		if node["type"] != "heading" {
			t.Errorf("node %d: expected heading, got %v", i, node["type"])
		}
		attrs := node["attrs"].(map[string]any)
		if int(attrs["level"].(float64)) != tt.level {
			t.Errorf("node %d: expected level %d, got %v", i, tt.level, attrs["level"])
		}
		if node["_text"] != tt.text {
			t.Errorf("node %d: expected text %q, got %v", i, tt.text, node["_text"])
		}
	}
}

func TestHtmlToTiptapJSON_Bold(t *testing.T) {
	result := htmlToTiptapJSON("<p><strong>bold</strong> text</p>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	node := content[0].(map[string]any)
	inlines := node["content"].([]any)

	if len(inlines) != 2 {
		t.Fatalf("expected 2 inline nodes, got %d", len(inlines))
	}

	bold := inlines[0].(map[string]any)
	if bold["text"] != "bold" {
		t.Errorf("expected 'bold', got %v", bold["text"])
	}
	marks := bold["marks"].([]any)
	mark := marks[0].(map[string]any)
	if mark["type"] != "bold" {
		t.Errorf("expected bold mark, got %v", mark["type"])
	}
}

func TestHtmlToTiptapJSON_Italic(t *testing.T) {
	result := htmlToTiptapJSON("<p><em>italic</em></p>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	node := content[0].(map[string]any)
	inlines := node["content"].([]any)
	em := inlines[0].(map[string]any)
	marks := em["marks"].([]any)
	mark := marks[0].(map[string]any)
	if mark["type"] != "italic" {
		t.Errorf("expected italic mark, got %v", mark["type"])
	}
}

func TestHtmlToTiptapJSON_Link(t *testing.T) {
	result := htmlToTiptapJSON(`<p><a href="https://example.com">link</a></p>`)
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	node := content[0].(map[string]any)
	inlines := node["content"].([]any)
	link := inlines[0].(map[string]any)
	marks := link["marks"].([]any)
	mark := marks[0].(map[string]any)
	if mark["type"] != "link" {
		t.Errorf("expected link mark, got %v", mark["type"])
	}
	attrs := mark["attrs"].(map[string]any)
	if attrs["href"] != "https://example.com" {
		t.Errorf("expected href, got %v", attrs["href"])
	}
}

func TestHtmlToTiptapJSON_BulletList(t *testing.T) {
	result := htmlToTiptapJSON("<ul><li>one</li><li>two</li></ul>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	if len(content) != 1 {
		t.Fatalf("expected 1 node, got %d", len(content))
	}
	list := content[0].(map[string]any)
	if list["type"] != "bulletList" {
		t.Errorf("expected bulletList, got %v", list["type"])
	}
	items := list["content"].([]any)
	if len(items) != 2 {
		t.Errorf("expected 2 list items, got %d", len(items))
	}
}

func TestHtmlToTiptapJSON_OrderedList(t *testing.T) {
	result := htmlToTiptapJSON("<ol><li>first</li><li>second</li></ol>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	list := content[0].(map[string]any)
	if list["type"] != "orderedList" {
		t.Errorf("expected orderedList, got %v", list["type"])
	}
}

func TestHtmlToTiptapJSON_Blockquote(t *testing.T) {
	result := htmlToTiptapJSON("<blockquote><p>quoted text</p></blockquote>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	bq := content[0].(map[string]any)
	if bq["type"] != "blockquote" {
		t.Errorf("expected blockquote, got %v", bq["type"])
	}
	inner := bq["content"].([]any)
	if len(inner) != 1 {
		t.Errorf("expected 1 inner node, got %d", len(inner))
	}
}

func TestHtmlToTiptapJSON_Table(t *testing.T) {
	html := "<table><tr><th>Header</th></tr><tr><td>Cell</td></tr></table>"
	result := htmlToTiptapJSON(html)
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	table := content[0].(map[string]any)
	if table["type"] != "table" {
		t.Errorf("expected table, got %v", table["type"])
	}
	rows := table["content"].([]any)
	if len(rows) != 2 {
		t.Errorf("expected 2 rows, got %d", len(rows))
	}
}

func TestHtmlToTiptapJSON_Image(t *testing.T) {
	result := htmlToTiptapJSON(`<figure><img src="test.png" alt="test image"/></figure>`)
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	img := content[0].(map[string]any)
	if img["type"] != "image" {
		t.Errorf("expected image, got %v", img["type"])
	}
	attrs := img["attrs"].(map[string]any)
	if attrs["src"] != "test.png" {
		t.Errorf("expected src=test.png, got %v", attrs["src"])
	}
}

func TestHtmlToTiptapJSON_CodeBlock(t *testing.T) {
	result := htmlToTiptapJSON("<pre><code>func main() {}</code></pre>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	code := content[0].(map[string]any)
	if code["type"] != "codeBlock" {
		t.Errorf("expected codeBlock, got %v", code["type"])
	}
}

func TestHtmlToTiptapJSON_HorizontalRule(t *testing.T) {
	result := htmlToTiptapJSON("<p>before</p><hr/><p>after</p>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	if len(content) != 3 {
		t.Fatalf("expected 3 nodes, got %d", len(content))
	}
	hr := content[1].(map[string]any)
	if hr["type"] != "horizontalRule" {
		t.Errorf("expected horizontalRule, got %v", hr["type"])
	}
}

func TestHtmlToTiptapJSON_HTMLEntities(t *testing.T) {
	result := htmlToTiptapJSON("<p>A &amp; B &lt; C &gt; D</p>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	node := content[0].(map[string]any)
	if node["_text"] != "A & B < C > D" {
		t.Errorf("expected decoded entities, got %v", node["_text"])
	}
}

func TestHtmlToTiptapJSON_DivUnwrap(t *testing.T) {
	result := htmlToTiptapJSON("<div><p>inside div</p></div>")
	var doc map[string]any
	json.Unmarshal(result, &doc)

	content := doc["content"].([]any)
	if len(content) != 1 {
		t.Fatalf("expected 1 node, got %d", len(content))
	}
	node := content[0].(map[string]any)
	if node["type"] != "paragraph" {
		t.Errorf("expected paragraph (div unwrapped), got %v", node["type"])
	}
}

func TestSplitChapters_Docx_SingleChapter(t *testing.T) {
	chapters := splitChapters("<h1>My Chapter</h1><p>content</p>", "docx")
	if len(chapters) != 1 {
		t.Fatalf("expected 1 chapter for docx, got %d", len(chapters))
	}
	if chapters[0].Title != "My Chapter" {
		t.Errorf("expected title 'My Chapter', got %q", chapters[0].Title)
	}
}

func TestSplitChapters_Epub_MultipleChapters(t *testing.T) {
	html := "<h1>Chapter 1</h1><p>content 1</p><h1>Chapter 2</h1><p>content 2</p><h1>Chapter 3</h1><p>content 3</p>"
	chapters := splitChapters(html, "epub")
	if len(chapters) != 3 {
		t.Fatalf("expected 3 chapters for epub, got %d", len(chapters))
	}
	if chapters[0].Title != "Chapter 1" {
		t.Errorf("expected 'Chapter 1', got %q", chapters[0].Title)
	}
	if chapters[2].Title != "Chapter 3" {
		t.Errorf("expected 'Chapter 3', got %q", chapters[2].Title)
	}
}

func TestSplitChapters_Epub_WithPreamble(t *testing.T) {
	html := "<p>preamble</p><h1>Chapter 1</h1><p>content</p>"
	chapters := splitChapters(html, "epub")
	if len(chapters) != 2 {
		t.Fatalf("expected 2 chapters (preamble + 1), got %d", len(chapters))
	}
	if chapters[0].Title != "Preamble" {
		t.Errorf("expected 'Preamble', got %q", chapters[0].Title)
	}
}

func TestSplitChapters_Epub_NoHeadings(t *testing.T) {
	html := "<p>just some text</p><p>more text</p>"
	chapters := splitChapters(html, "epub")
	if len(chapters) != 1 {
		t.Fatalf("expected 1 chapter when no headings, got %d", len(chapters))
	}
}

func TestHtmlToTiptapJSON_ComplexPandocOutput(t *testing.T) {
	// Simulate typical pandoc output from a docx
	html := `<h1 id="chapter-1">Chapter 1</h1>
<p>This is a <strong>bold</strong> and <em>italic</em> paragraph.</p>
<ul>
<li>Item one</li>
<li>Item two</li>
</ul>
<blockquote>
<p>A famous quote.</p>
</blockquote>
<p>Final paragraph with a <a href="https://example.com">link</a>.</p>`

	result := htmlToTiptapJSON(html)
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}

	content := doc["content"].([]any)
	if len(content) < 5 {
		t.Fatalf("expected at least 5 nodes, got %d", len(content))
	}

	// Verify node types in order
	expected := []string{"heading", "paragraph", "bulletList", "blockquote", "paragraph"}
	for i, exp := range expected {
		node := content[i].(map[string]any)
		if node["type"] != exp {
			t.Errorf("node %d: expected %s, got %v", i, exp, node["type"])
		}
	}
}

func TestHtmlToTiptapJSON_NestedMarks(t *testing.T) {
	// Pandoc produces nested marks like <em><strong>text</strong></em>
	html := `<p><em><strong>Important Notice:</strong></em> Normal text.</p>`

	result := htmlToTiptapJSON(html)
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}

	content := doc["content"].([]any)
	if len(content) != 1 {
		t.Fatalf("expected 1 node, got %d", len(content))
	}

	p := content[0].(map[string]any)
	inlines := p["content"].([]any)
	if len(inlines) < 2 {
		t.Fatalf("expected at least 2 inline nodes, got %d", len(inlines))
	}

	// First inline: "Important Notice:" with both italic and bold
	first := inlines[0].(map[string]any)
	if first["text"] != "Important Notice:" {
		t.Errorf("expected 'Important Notice:', got %v", first["text"])
	}
	marks := first["marks"].([]any)
	if len(marks) != 2 {
		t.Fatalf("expected 2 marks (italic+bold), got %d", len(marks))
	}
	markTypes := make(map[string]bool)
	for _, m := range marks {
		markTypes[m.(map[string]any)["type"].(string)] = true
	}
	if !markTypes["italic"] || !markTypes["bold"] {
		t.Errorf("expected italic+bold marks, got %v", marks)
	}

	// Second inline: " Normal text." with no marks
	second := inlines[1].(map[string]any)
	if second["text"] != " Normal text." {
		t.Errorf("expected ' Normal text.', got %v", second["text"])
	}
	if second["marks"] != nil {
		t.Errorf("expected no marks on normal text, got %v", second["marks"])
	}
}

func TestHtmlToTiptapJSON_DeeplyNestedMarks(t *testing.T) {
	// <strong>bold <em>bold+italic</em> bold</strong>
	html := `<p><strong>bold <em>both</em> bold</strong></p>`

	result := htmlToTiptapJSON(html)
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}

	p := doc["content"].([]any)[0].(map[string]any)
	inlines := p["content"].([]any)
	if len(inlines) != 3 {
		t.Fatalf("expected 3 inline nodes, got %d", len(inlines))
	}

	// "bold " — bold only
	n0 := inlines[0].(map[string]any)
	if n0["text"] != "bold " {
		t.Errorf("node 0: expected 'bold ', got %v", n0["text"])
	}
	m0 := n0["marks"].([]any)
	if len(m0) != 1 || m0[0].(map[string]any)["type"] != "bold" {
		t.Errorf("node 0: expected [bold], got %v", m0)
	}

	// "both" — bold + italic
	n1 := inlines[1].(map[string]any)
	if n1["text"] != "both" {
		t.Errorf("node 1: expected 'both', got %v", n1["text"])
	}
	m1 := n1["marks"].([]any)
	if len(m1) != 2 {
		t.Errorf("node 1: expected 2 marks, got %d", len(m1))
	}

	// " bold" — bold only
	n2 := inlines[2].(map[string]any)
	if n2["text"] != " bold" {
		t.Errorf("node 2: expected ' bold', got %v", n2["text"])
	}
	m2 := n2["marks"].([]any)
	if len(m2) != 1 || m2[0].(map[string]any)["type"] != "bold" {
		t.Errorf("node 2: expected [bold], got %v", m2)
	}
}

func TestHtmlToTiptapJSON_SpanUnwrap_NoTextLoss(t *testing.T) {
	// Pandoc adds <span id="..."> for epub anchors — text must not be lost
	html := `<p><span id="chapter1.xhtml"></span></p><h1>Title</h1><p>Content here.</p>`

	result := htmlToTiptapJSON(html)
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}

	content := doc["content"].([]any)
	// Should have: empty paragraph (from span), heading, paragraph
	foundHeading := false
	foundContent := false
	for _, n := range content {
		node := n.(map[string]any)
		if node["type"] == "heading" {
			foundHeading = true
			if node["_text"] != "Title" {
				t.Errorf("heading text: expected 'Title', got %v", node["_text"])
			}
		}
		if node["type"] == "paragraph" && node["_text"] == "Content here." {
			foundContent = true
		}
	}
	if !foundHeading {
		t.Error("heading node not found — text lost!")
	}
	if !foundContent {
		t.Error("content paragraph not found — text lost!")
	}
}

func TestHtmlToTiptapJSON_StandaloneHTML(t *testing.T) {
	// Pandoc --standalone output: DOCTYPE, html, head with style, body with content
	html := `<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8" />
  <title>Test</title>
  <style>body { color: red; }</style>
</head>
<body>
<p>Real content here.</p>
<p><img src="data:image/png;base64,abc123" /></p>
</body>
</html>`

	result := htmlToTiptapJSON(html)
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}

	content := doc["content"].([]any)
	// Should have paragraph + image, NO style/title/meta junk
	foundContent := false
	foundImage := false
	for _, n := range content {
		node := n.(map[string]any)
		if node["type"] == "paragraph" && node["_text"] == "Real content here." {
			foundContent = true
		}
		if node["type"] == "image" {
			foundImage = true
		}
		// Must NOT have CSS rules as text content
		if node["type"] == "paragraph" {
			text, _ := node["_text"].(string)
			if strings.Contains(text, "color: red") || strings.Contains(text, "body {") {
				t.Error("CSS style leaked into content as paragraph text!")
			}
		}
	}
	if !foundContent {
		t.Error("real content paragraph not found")
	}
	if !foundImage {
		t.Error("image node not found")
	}
}

func TestHtmlToTiptapJSON_BoldItalicLink(t *testing.T) {
	// <a href="..."><strong>bold link</strong></a>
	html := `<p><a href="http://example.com"><strong>click here</strong></a></p>`

	result := htmlToTiptapJSON(html)
	var doc map[string]any
	if err := json.Unmarshal(result, &doc); err != nil {
		t.Fatal(err)
	}

	p := doc["content"].([]any)[0].(map[string]any)
	inlines := p["content"].([]any)
	if len(inlines) != 1 {
		t.Fatalf("expected 1 inline node, got %d", len(inlines))
	}

	n := inlines[0].(map[string]any)
	if n["text"] != "click here" {
		t.Errorf("expected 'click here', got %v", n["text"])
	}
	marks := n["marks"].([]any)
	if len(marks) != 2 {
		t.Fatalf("expected 2 marks (link+bold), got %d", len(marks))
	}
	markTypes := make(map[string]bool)
	for _, m := range marks {
		markTypes[m.(map[string]any)["type"].(string)] = true
	}
	if !markTypes["link"] || !markTypes["bold"] {
		t.Errorf("expected link+bold marks, got %v", marks)
	}
}
