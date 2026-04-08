package tasks

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
)

// Chapter represents a split chapter from an imported document.
type Chapter struct {
	Title    string
	Filename string
	Content  string // HTML content for this chapter
}

// splitChapters splits pandoc HTML output into chapters.
// For epub: splits on <h1> boundaries.
// For docx: returns a single chapter.
func splitChapters(html string, format string) []Chapter {
	if format == "docx" {
		title := extractFirstHeading(html)
		if title == "" {
			title = "Imported Chapter"
		}
		return []Chapter{{
			Title:    title,
			Filename: "import.docx",
			Content:  html,
		}}
	}

	// For epub: split on <h1> tags
	sections := splitOnH1(html)
	if len(sections) == 0 {
		// No h1 found — try h2
		sections = splitOnTag(html, "h2")
	}
	if len(sections) == 0 {
		// No headings at all — single chapter
		return []Chapter{{
			Title:    "Imported Chapter",
			Filename: "import.epub",
			Content:  html,
		}}
	}

	chapters := make([]Chapter, 0, len(sections))
	for i, sec := range sections {
		title := sec.Title
		if title == "" {
			title = fmt.Sprintf("Chapter %d", i+1)
		}
		chapters = append(chapters, Chapter{
			Title:    title,
			Filename: fmt.Sprintf("import-ch%03d.epub", i+1),
			Content:  sec.HTML,
		})
	}
	return chapters
}

type section struct {
	Title string
	HTML  string
}

var h1Re = regexp.MustCompile(`(?i)<h1[^>]*>(.*?)</h1>`)
var h2Re = regexp.MustCompile(`(?i)<h2[^>]*>(.*?)</h2>`)

func splitOnH1(html string) []section {
	return splitOnTag(html, "h1")
}

func splitOnTag(html string, tag string) []section {
	var re *regexp.Regexp
	if tag == "h1" {
		re = h1Re
	} else {
		re = h2Re
	}

	locs := re.FindAllStringIndex(html, -1)
	if len(locs) == 0 {
		return nil
	}

	matches := re.FindAllStringSubmatch(html, -1)
	sections := make([]section, 0, len(locs))

	for i, loc := range locs {
		start := loc[0]
		var end int
		if i+1 < len(locs) {
			end = locs[i+1][0]
		} else {
			end = len(html)
		}
		content := strings.TrimSpace(html[start:end])
		if content == "" {
			continue
		}
		title := stripTags(matches[i][1])
		sections = append(sections, section{Title: title, HTML: content})
	}

	// If there's content before the first heading, prepend it
	if locs[0][0] > 0 {
		preamble := strings.TrimSpace(html[:locs[0][0]])
		if preamble != "" {
			sections = append([]section{{Title: "Preamble", HTML: preamble}}, sections...)
		}
	}

	return sections
}

func extractFirstHeading(html string) string {
	m := h1Re.FindStringSubmatch(html)
	if m != nil {
		return stripTags(m[1])
	}
	m = h2Re.FindStringSubmatch(html)
	if m != nil {
		return stripTags(m[1])
	}
	return ""
}

var tagStripRe = regexp.MustCompile(`<[^>]+>`)

func stripTags(s string) string {
	return decodeHTMLEntities(strings.TrimSpace(tagStripRe.ReplaceAllString(s, "")))
}

// htmlToTiptapJSON converts HTML to a Tiptap-compatible JSON document.
func htmlToTiptapJSON(html string) json.RawMessage {
	nodes := parseHTMLToNodes(html)
	if len(nodes) == 0 {
		nodes = []any{map[string]any{"type": "paragraph", "_text": ""}}
	}

	doc := map[string]any{
		"type":    "doc",
		"content": nodes,
	}
	data, _ := json.Marshal(doc)
	return data
}

// parseHTMLToNodes converts HTML string to Tiptap node array.
// This is a lightweight parser that handles common elements from pandoc output.
func parseHTMLToNodes(html string) []any {
	var nodes []any
	html = strings.TrimSpace(html)
	if html == "" {
		return nodes
	}

	// Strip <!DOCTYPE ...> declaration if present
	if idx := strings.Index(strings.ToLower(html), "<!doctype"); idx != -1 {
		end := strings.Index(html[idx:], ">")
		if end != -1 {
			html = html[:idx] + html[idx+end+1:]
		}
	}

	// Process block-level elements
	pos := 0
	for pos < len(html) {
		// Skip whitespace between elements
		for pos < len(html) && (html[pos] == ' ' || html[pos] == '\n' || html[pos] == '\r' || html[pos] == '\t') {
			pos++
		}
		if pos >= len(html) {
			break
		}

		// Skip HTML comments (<!-- ... -->)
		if strings.HasPrefix(html[pos:], "<!--") {
			end := strings.Index(html[pos:], "-->")
			if end == -1 {
				break
			}
			pos = pos + end + 3
			continue
		}

		if html[pos] != '<' {
			// Text outside tags — wrap in paragraph
			end := strings.Index(html[pos:], "<")
			if end == -1 {
				end = len(html)
			} else {
				end = pos + end
			}
			text := strings.TrimSpace(html[pos:end])
			if text != "" {
				nodes = append(nodes, makeParagraph(text))
			}
			pos = end
			continue
		}

		// Find the tag name
		tagEnd := strings.IndexAny(html[pos+1:], " >")
		if tagEnd == -1 {
			break
		}
		tagName := strings.ToLower(html[pos+1 : pos+1+tagEnd])

		// Handle self-closing and special cases
		switch {
		case tagName == "hr" || tagName == "hr/":
			nodes = append(nodes, map[string]any{"type": "horizontalRule"})
			closeIdx := strings.Index(html[pos:], ">")
			if closeIdx == -1 {
				pos = len(html)
			} else {
				pos = pos + closeIdx + 1
			}

		case tagName == "br" || tagName == "br/":
			closeIdx := strings.Index(html[pos:], ">")
			if closeIdx == -1 {
				pos = len(html)
			} else {
				pos = pos + closeIdx + 1
			}

		case strings.HasPrefix(tagName, "h") && len(tagName) == 2 && tagName[1] >= '1' && tagName[1] <= '6':
			level := int(tagName[1] - '0')
			inner, end := extractElement(html, pos, tagName)
			text := stripTags(inner)
			inlineContent := parseInlineContent(inner)
			node := map[string]any{
				"type":  "heading",
				"attrs": map[string]any{"level": level},
				"_text": text,
			}
			if len(inlineContent) > 0 {
				node["content"] = inlineContent
			}
			nodes = append(nodes, node)
			pos = end

		case tagName == "p":
			inner, end := extractElement(html, pos, "p")
			// Check if paragraph contains only an <img> — promote to block image
			trimmedInner := strings.TrimSpace(inner)
			if strings.Contains(trimmedInner, "<img") && strings.TrimSpace(stripTags(trimmedInner)) == "" {
				imgNode := extractImgFromTag(trimmedInner[strings.Index(trimmedInner, "<img"):])
				if imgNode != nil {
					nodes = append(nodes, imgNode)
					pos = end
					break
				}
			}
			text := stripTags(inner)
			inlineContent := parseInlineContent(inner)
			node := map[string]any{
				"type":  "paragraph",
				"_text": text,
			}
			if len(inlineContent) > 0 {
				node["content"] = inlineContent
			}
			nodes = append(nodes, node)
			pos = end

		case tagName == "blockquote":
			inner, end := extractElement(html, pos, "blockquote")
			innerNodes := parseHTMLToNodes(inner)
			if len(innerNodes) == 0 {
				innerNodes = []any{map[string]any{"type": "paragraph", "_text": stripTags(inner)}}
			}
			nodes = append(nodes, map[string]any{
				"type":    "blockquote",
				"_text":   stripTags(inner),
				"content": innerNodes,
			})
			pos = end

		case tagName == "ul":
			inner, end := extractElement(html, pos, "ul")
			items := parseListItems(inner)
			nodes = append(nodes, map[string]any{
				"type":    "bulletList",
				"_text":   stripTags(inner),
				"content": items,
			})
			pos = end

		case tagName == "ol":
			inner, end := extractElement(html, pos, "ol")
			items := parseListItems(inner)
			nodes = append(nodes, map[string]any{
				"type":    "orderedList",
				"_text":   stripTags(inner),
				"content": items,
			})
			pos = end

		case tagName == "pre":
			inner, end := extractElement(html, pos, "pre")
			// Extract code content
			code := stripTags(inner)
			code = strings.ReplaceAll(code, "&lt;", "<")
			code = strings.ReplaceAll(code, "&gt;", ">")
			code = strings.ReplaceAll(code, "&amp;", "&")
			nodes = append(nodes, map[string]any{
				"type":  "codeBlock",
				"_text": code,
				"content": []any{
					map[string]any{"type": "text", "text": code},
				},
			})
			pos = end

		case tagName == "table":
			inner, end := extractElement(html, pos, "table")
			tableNode := parseTable(inner)
			nodes = append(nodes, tableNode)
			pos = end

		case tagName == "figure":
			inner, end := extractElement(html, pos, "figure")
			// Extract img from figure
			imgNode := extractImgNode(inner)
			if imgNode != nil {
				nodes = append(nodes, imgNode)
			}
			pos = end

		case tagName == "img":
			imgNode := extractImgFromTag(html[pos:])
			if imgNode != nil {
				nodes = append(nodes, imgNode)
			}
			closeIdx := strings.Index(html[pos:], ">")
			if closeIdx == -1 {
				pos = len(html)
			} else {
				pos = pos + closeIdx + 1
			}

		case tagName == "head" || tagName == "style" || tagName == "script" || tagName == "title" || tagName == "link":
			// Skip metadata elements entirely — no content to extract
			_, end := extractElement(html, pos, tagName)
			pos = end

		case tagName == "div" || tagName == "section" || tagName == "article" || tagName == "main" || tagName == "body" || tagName == "html":
			// Unwrap container elements — parse their inner content
			inner, end := extractElement(html, pos, tagName)
			innerNodes := parseHTMLToNodes(inner)
			nodes = append(nodes, innerNodes...)
			pos = end

		default:
			// Unknown block element or inline at top level — wrap in paragraph
			if isVoidElement(tagName) {
				closeIdx := strings.Index(html[pos:], ">")
				if closeIdx == -1 {
					pos = len(html)
				} else {
					pos = pos + closeIdx + 1
				}
			} else {
				inner, end := extractElement(html, pos, tagName)
				text := stripTags(inner)
				if text != "" {
					nodes = append(nodes, makeParagraph(text))
				}
				pos = end
			}
		}
	}

	return nodes
}

func makeParagraph(text string) map[string]any {
	return map[string]any{
		"type":  "paragraph",
		"_text": text,
		"content": []any{
			map[string]any{"type": "text", "text": text},
		},
	}
}

// extractElement extracts inner HTML and returns the position after the closing tag.
func extractElement(html string, start int, tagName string) (inner string, endPos int) {
	// Find the end of the opening tag
	openEnd := strings.Index(html[start:], ">")
	if openEnd == -1 {
		return "", len(html)
	}
	openEnd = start + openEnd + 1

	// Find matching closing tag (handle nesting)
	closeTag := "</" + tagName + ">"
	openTag := "<" + tagName
	depth := 1
	pos := openEnd

	for depth > 0 && pos < len(html) {
		nextClose := strings.Index(strings.ToLower(html[pos:]), closeTag)
		nextOpen := strings.Index(strings.ToLower(html[pos:]), openTag)

		if nextClose == -1 {
			// No closing tag found — take everything
			return html[openEnd:], len(html)
		}

		if nextOpen != -1 && nextOpen < nextClose {
			// Found another opening tag before close
			depth++
			pos = pos + nextOpen + len(openTag)
		} else {
			depth--
			if depth == 0 {
				inner = html[openEnd : pos+nextClose]
				endPos = pos + nextClose + len(closeTag)
				return inner, endPos
			}
			pos = pos + nextClose + len(closeTag)
		}
	}

	return html[openEnd:], len(html)
}

// parseInlineContent converts inline HTML to Tiptap text nodes with marks.
func parseInlineContent(html string) []any {
	return parseInlineWithMarks(html, nil)
}

// markTypeForTag maps HTML inline tags to Tiptap mark types.
func markTypeForTag(tag string) string {
	switch tag {
	case "strong", "b":
		return "bold"
	case "em", "i":
		return "italic"
	case "u":
		return "underline"
	case "s", "del", "strike":
		return "strike"
	case "code":
		return "code"
	case "sup":
		return "superscript"
	case "sub":
		return "subscript"
	default:
		return ""
	}
}

// parseInlineWithMarks recursively parses inline HTML, accumulating marks from parent elements.
// This correctly handles nested marks like <em><strong>text</strong></em> → [italic, bold].
func parseInlineWithMarks(html string, parentMarks []any) []any {
	html = strings.TrimSpace(html)
	if html == "" {
		return nil
	}

	var result []any
	pos := 0

	for pos < len(html) {
		if html[pos] != '<' {
			// Plain text
			end := strings.Index(html[pos:], "<")
			if end == -1 {
				end = len(html)
			} else {
				end = pos + end
			}
			text := decodeHTMLEntities(html[pos:end])
			if text != "" {
				node := map[string]any{"type": "text", "text": text}
				if len(parentMarks) > 0 {
					node["marks"] = copyMarks(parentMarks)
				}
				result = append(result, node)
			}
			pos = end
			continue
		}

		// Check for closing tag
		if strings.HasPrefix(html[pos:], "</") {
			closeEnd := strings.Index(html[pos:], ">")
			if closeEnd == -1 {
				pos = len(html)
			} else {
				pos = pos + closeEnd + 1
			}
			continue
		}

		// Find tag name
		tagEnd := strings.IndexAny(html[pos+1:], " >")
		if tagEnd == -1 {
			break
		}
		tagName := strings.ToLower(html[pos+1 : pos+1+tagEnd])

		// Check if this is a mark-producing tag
		if markType := markTypeForTag(tagName); markType != "" {
			inner, end := extractElement(html, pos, tagName)
			newMark := map[string]any{"type": markType}
			childMarks := append(copyMarks(parentMarks), newMark)
			// Recurse into inner content with accumulated marks
			innerNodes := parseInlineWithMarks(inner, childMarks)
			result = append(result, innerNodes...)
			pos = end
			continue
		}

		switch tagName {
		case "a":
			href := extractAttr(html[pos:], "href")
			inner, end := extractElement(html, pos, "a")
			linkMark := map[string]any{
				"type":  "link",
				"attrs": map[string]any{"href": href},
			}
			childMarks := append(copyMarks(parentMarks), linkMark)
			innerNodes := parseInlineWithMarks(inner, childMarks)
			result = append(result, innerNodes...)
			pos = end

		case "br", "br/":
			result = append(result, map[string]any{"type": "hardBreak"})
			closeIdx := strings.Index(html[pos:], ">")
			if closeIdx == -1 {
				pos = len(html)
			} else {
				pos = pos + closeIdx + 1
			}

		case "span":
			// Unwrap spans — pass through parent marks
			inner, end := extractElement(html, pos, "span")
			innerNodes := parseInlineWithMarks(inner, parentMarks)
			result = append(result, innerNodes...)
			pos = end

		default:
			// Unknown inline element — preserve text with parent marks
			if isVoidElement(tagName) {
				closeIdx := strings.Index(html[pos:], ">")
				if closeIdx == -1 {
					pos = len(html)
				} else {
					pos = pos + closeIdx + 1
				}
			} else {
				inner, end := extractElement(html, pos, tagName)
				// Recurse to preserve any nested marks/text
				innerNodes := parseInlineWithMarks(inner, parentMarks)
				result = append(result, innerNodes...)
				pos = end
			}
		}
	}

	return result
}

// copyMarks creates a shallow copy of a marks slice to avoid mutation.
func copyMarks(marks []any) []any {
	if len(marks) == 0 {
		return nil
	}
	cp := make([]any, len(marks))
	copy(cp, marks)
	return cp
}

// parseListItems parses <li> elements from inner HTML of ul/ol.
func parseListItems(html string) []any {
	var items []any
	pos := 0

	for {
		liStart := strings.Index(strings.ToLower(html[pos:]), "<li")
		if liStart == -1 {
			break
		}
		liStart += pos
		inner, end := extractElement(html, liStart, "li")

		// Check if inner contains sub-lists
		innerNodes := parseHTMLToNodes(inner)
		if len(innerNodes) == 0 {
			text := stripTags(inner)
			innerNodes = []any{makeParagraph(text)}
		}

		items = append(items, map[string]any{
			"type":    "listItem",
			"content": innerNodes,
		})
		pos = end
	}

	return items
}

// parseTable converts HTML table to Tiptap table node.
func parseTable(html string) map[string]any {
	var rows []any

	// Process thead and tbody, or direct tr
	rowHTML := html
	pos := 0
	for {
		trStart := strings.Index(strings.ToLower(rowHTML[pos:]), "<tr")
		if trStart == -1 {
			break
		}
		trStart += pos
		inner, end := extractElement(rowHTML, trStart, "tr")

		cells := parseTableCells(inner)
		rows = append(rows, map[string]any{
			"type":    "tableRow",
			"content": cells,
		})
		pos = end
	}

	return map[string]any{
		"type":    "table",
		"_text":   stripTags(html),
		"content": rows,
	}
}

func parseTableCells(html string) []any {
	var cells []any
	pos := 0
	for {
		// Find td or th
		tdIdx := strings.Index(strings.ToLower(html[pos:]), "<td")
		thIdx := strings.Index(strings.ToLower(html[pos:]), "<th")

		var cellTag string
		var cellStart int

		if tdIdx == -1 && thIdx == -1 {
			break
		} else if tdIdx == -1 {
			cellTag = "th"
			cellStart = pos + thIdx
		} else if thIdx == -1 {
			cellTag = "td"
			cellStart = pos + tdIdx
		} else if tdIdx < thIdx {
			cellTag = "td"
			cellStart = pos + tdIdx
		} else {
			cellTag = "th"
			cellStart = pos + thIdx
		}

		inner, end := extractElement(html, cellStart, cellTag)
		cellType := "tableCell"
		if cellTag == "th" {
			cellType = "tableHeader"
		}

		cellContent := parseHTMLToNodes(inner)
		if len(cellContent) == 0 {
			text := stripTags(inner)
			cellContent = []any{makeParagraph(text)}
		}

		cells = append(cells, map[string]any{
			"type":    cellType,
			"content": cellContent,
		})
		pos = end
	}
	return cells
}

func extractImgNode(html string) map[string]any {
	src := extractAttr(html, "src")
	if src == "" {
		return nil
	}
	alt := extractAttr(html, "alt")
	return map[string]any{
		"type": "image",
		"attrs": map[string]any{
			"src": src,
			"alt": alt,
		},
	}
}

func extractImgFromTag(html string) map[string]any {
	return extractImgNode(html)
}

func extractAttr(html string, attr string) string {
	// Look for attr="value" or attr='value'
	search := attr + `="`
	idx := strings.Index(strings.ToLower(html), strings.ToLower(search))
	if idx != -1 {
		start := idx + len(search)
		end := strings.Index(html[start:], `"`)
		if end != -1 {
			return html[start : start+end]
		}
	}
	// Try single quotes
	search = attr + `='`
	idx = strings.Index(strings.ToLower(html), strings.ToLower(search))
	if idx != -1 {
		start := idx + len(search)
		end := strings.Index(html[start:], `'`)
		if end != -1 {
			return html[start : start+end]
		}
	}
	return ""
}

func decodeHTMLEntities(s string) string {
	s = strings.ReplaceAll(s, "&amp;", "&")
	s = strings.ReplaceAll(s, "&lt;", "<")
	s = strings.ReplaceAll(s, "&gt;", ">")
	s = strings.ReplaceAll(s, "&quot;", `"`)
	s = strings.ReplaceAll(s, "&#39;", "'")
	s = strings.ReplaceAll(s, "&apos;", "'")
	s = strings.ReplaceAll(s, "&nbsp;", " ")
	s = strings.ReplaceAll(s, "&#160;", " ")
	return s
}

func isVoidElement(tag string) bool {
	switch tag {
	case "br", "hr", "img", "input", "meta", "link", "col", "area", "base", "embed", "source", "track", "wbr":
		return true
	}
	return false
}
