package api

import (
	"encoding/json"
	"regexp"
	"strings"
)

// atxHeadingRe matches a leading Markdown ATX heading line (#, ##, ### ...).
var atxHeadingRe = regexp.MustCompile(`^(#{1,6})\s+(.*\S)\s*$`)

func tiptapHeadingNode(level int, text string) map[string]any {
	if level > 3 { // Tiptap is configured for levels 1-3 (StarterKit)
		level = 3
	}
	return map[string]any{
		"type":    "heading",
		"attrs":   map[string]any{"level": level},
		"_text":   text,
		"content": []map[string]any{{"type": "text", "text": text}},
	}
}

func tiptapParagraphNode(text string) map[string]any {
	return map[string]any{
		"type":    "paragraph",
		"_text":   text,
		"content": []map[string]any{{"type": "text", "text": text}},
	}
}

// markdownToTiptapJSON converts lightweight Markdown into a Tiptap-compatible JSON
// document: ATX headings (#, ##, ###) become heading nodes; blank-line-separated
// blocks become paragraphs (wrapped lines within a block are joined). Every node
// carries the `_text` snapshot the chapter_blocks trigger reads via JSON_TABLE.
// Unrecognized markup degrades to paragraph text — content is never dropped.
func markdownToTiptapJSON(text string) json.RawMessage {
	text = strings.ReplaceAll(text, "\r\n", "\n")
	blocks := strings.Split(text, "\n\n")
	nodes := make([]map[string]any, 0, len(blocks))
	for _, blk := range blocks {
		blk = strings.Trim(blk, "\n")
		if strings.TrimSpace(blk) == "" {
			continue
		}
		lines := strings.Split(blk, "\n")
		i := 0
		// Leading heading lines become heading nodes (handles "### Title" on its own
		// block AND "### Title\nprose..." in one block).
		for i < len(lines) {
			if m := atxHeadingRe.FindStringSubmatch(strings.TrimSpace(lines[i])); m != nil {
				nodes = append(nodes, tiptapHeadingNode(len(m[1]), strings.TrimSpace(m[2])))
				i++
				continue
			}
			break
		}
		if i < len(lines) {
			para := strings.TrimSpace(strings.Join(lines[i:], " "))
			if para != "" {
				nodes = append(nodes, tiptapParagraphNode(para))
			}
		}
	}
	if len(nodes) == 0 {
		nodes = append(nodes, map[string]any{"type": "paragraph", "_text": ""})
	}
	doc := map[string]any{"type": "doc", "content": nodes}
	b, _ := json.Marshal(doc)
	return json.RawMessage(b)
}

// normalizeBodyToTiptap is the UNIVERSAL chapter-content formatter. It turns an
// inbound body into a canonical Tiptap JSON doc so every ingestion path stores real
// blocks (read mode + chapter_blocks + extraction all rely on this):
//   - "json"     → pass-through (already a Tiptap doc)
//   - "markdown" → the raw is a JSON-encoded string; parse via markdownToTiptapJSON
//   - "plain"    → JSON-encoded string; parse via plainTextToTiptapJSON
// Returns the (doc, "json"). On any decode failure it falls back to pass-through so a
// malformed input can never 500 the write.
func normalizeBodyToTiptap(raw json.RawMessage, format string) (json.RawMessage, string) {
	switch format {
	case "markdown":
		var text string
		if err := json.Unmarshal(raw, &text); err == nil {
			return markdownToTiptapJSON(text), "json"
		}
	case "plain":
		var text string
		if err := json.Unmarshal(raw, &text); err == nil {
			return plainTextToTiptapJSON(text), "json"
		}
	}
	return raw, "json"
}

// plainTextToTiptapJSON converts plain text into a Tiptap-compatible JSON document.
// Each paragraph (split by double newlines) becomes a paragraph node with a _text snapshot
// that the chapter_blocks trigger reads via JSON_TABLE.
func plainTextToTiptapJSON(text string) json.RawMessage {
	text = strings.ReplaceAll(text, "\r\n", "\n")
	paragraphs := strings.Split(text, "\n\n")

	nodes := make([]map[string]any, 0, len(paragraphs))
	for _, p := range paragraphs {
		p = strings.TrimRight(p, "\n")
		if p == "" {
			nodes = append(nodes, map[string]any{
				"type":  "paragraph",
				"_text": "",
			})
			continue
		}
		nodes = append(nodes, map[string]any{
			"type":  "paragraph",
			"_text": p,
			"content": []map[string]any{
				{"type": "text", "text": p},
			},
		})
	}

	doc := map[string]any{
		"type":    "doc",
		"content": nodes,
	}
	b, _ := json.Marshal(doc)
	return json.RawMessage(b)
}
