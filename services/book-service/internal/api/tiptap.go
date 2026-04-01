package api

import (
	"encoding/json"
	"strings"
)

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
