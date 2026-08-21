package epubimport

import (
	"archive/zip"
	"bytes"
	"io"
	"strings"

	"golang.org/x/net/html"
)

// ExtractChapter serializes valid HTML for one normalized logical chapter. It
// never slices source bytes: range selection occurs on the parsed DOM and
// retains the containers needed to keep the returned fragment well-formed.
func ExtractChapter(data []byte, node NavigationNode, limits Limits) (string, []Diagnostic, error) {
	limit := limits.Normalize()
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return "", nil, &Error{Code: CodeInvalidArchive, Message: "EPUB ZIP directory is unreadable"}
	}
	ar, err := openArchive(zr, limit)
	if err != nil {
		return "", nil, err
	}
	if len(node.ContentRanges) == 0 {
		return "", nil, &Error{Code: CodeInvalidNavigation, Message: "logical chapter has no content range"}
	}
	var output strings.Builder
	var diagnostics []Diagnostic
	for _, contentRange := range node.ContentRanges {
		file, ok := ar.files[contentRange.Href]
		if !ok {
			return "", diagnostics, &Error{Code: CodeContentUnavailable, Message: "logical chapter content document is unavailable"}
		}
		raw, err := ar.read(file)
		if err != nil {
			return "", diagnostics, err
		}
		fragment, warnings, err := extractDOMRange(raw, contentRange, limit.MaxChapterHTMLSize-int64(output.Len()))
		if err != nil {
			return "", diagnostics, err
		}
		diagnostics = append(diagnostics, warnings...)
		output.WriteString(fragment)
	}
	if strings.TrimSpace(normalizedText(output.String())) == "" {
		return "", diagnostics, &Error{Code: CodeInvalidNavigation, Message: "logical chapter content range is empty"}
	}
	if int64(output.Len()) > limit.MaxChapterHTMLSize {
		return "", diagnostics, archiveLimit("logical chapter HTML exceeds configured limit")
	}
	return output.String(), diagnostics, nil
}

func extractDOMRange(raw []byte, contentRange ContentRange, remaining int64) (string, []Diagnostic, error) {
	if remaining <= 0 {
		return "", nil, archiveLimit("logical chapter HTML exceeds configured limit")
	}
	doc, err := html.Parse(bytes.NewReader(normalizeXHTMLSelfClosingTags(raw)))
	if err != nil {
		return "", nil, &Error{Code: CodeInvalidNavigation, Message: "content document is invalid HTML"}
	}
	body := findNode(doc, func(node *html.Node) bool {
		return node.Type == html.ElementNode && strings.EqualFold(node.Data, "body")
	})
	if body == nil {
		return "", nil, &Error{Code: CodeInvalidNavigation, Message: "content document has no body"}
	}
	start := body
	var diagnostics []Diagnostic
	if contentRange.StartAnchor != "" {
		if anchor := findAnchor(body, contentRange.StartAnchor); anchor != nil {
			start = rangeBoundary(anchor, body)
		} else {
			diagnostics = append(diagnostics, Diagnostic{Code: CodeAnchorMissing, Message: "chapter start anchor is missing"})
		}
	}
	var end *html.Node
	if contentRange.EndAnchor != "" {
		if anchor := findAnchor(body, contentRange.EndAnchor); anchor != nil {
			end = rangeBoundary(anchor, body)
		} else {
			diagnostics = append(diagnostics, Diagnostic{Code: CodeAnchorMissing, Message: "chapter end anchor is missing"})
		}
	}
	positions := make(map[*html.Node]nodePosition)
	var counter int
	indexDOM(body, positions, &counter)
	startPosition := positions[start].start
	endPosition := counter + 1
	if end != nil {
		endPosition = positions[end].start
	}
	if endPosition <= startPosition {
		return "", append(diagnostics, Diagnostic{Code: CodeRangeAmbiguous, Message: "chapter anchors do not define a forward range"}), &Error{Code: CodeInvalidNavigation, Message: "chapter anchors do not define a forward range"}
	}
	fragmentRoot := &html.Node{Type: html.ElementNode, Data: "div"}
	for child := body.FirstChild; child != nil; child = child.NextSibling {
		if clone := cloneDOMRange(child, positions, startPosition, endPosition); clone != nil {
			fragmentRoot.AppendChild(clone)
		}
	}
	var output bytes.Buffer
	for child := fragmentRoot.FirstChild; child != nil; child = child.NextSibling {
		if err := html.Render(&output, child); err != nil {
			return "", diagnostics, &Error{Code: CodeInvalidNavigation, Message: "chapter HTML cannot be serialized"}
		}
		if int64(output.Len()) > remaining {
			return "", diagnostics, archiveLimit("logical chapter HTML exceeds configured limit")
		}
	}
	return output.String(), diagnostics, nil
}

// normalizeXHTMLSelfClosingTags adapts XHTML's XML-style empty non-void
// elements for x/net/html. Without this, a common <title/> makes the HTML
// parser treat the rest of the document as title text and hides the body.
func normalizeXHTMLSelfClosingTags(raw []byte) []byte {
	tokenizer := html.NewTokenizer(bytes.NewReader(raw))
	var output bytes.Buffer
	for {
		tokenType := tokenizer.Next()
		if tokenType == html.ErrorToken {
			if tokenizer.Err() != io.EOF {
				return raw
			}
			return output.Bytes()
		}
		if tokenType != html.SelfClosingTagToken {
			output.Write(tokenizer.Raw())
			continue
		}
		token := tokenizer.Token()
		if isVoidElement(token.Data) {
			output.Write(tokenizer.Raw())
			continue
		}
		opening := strings.TrimSuffix(strings.TrimSpace(string(tokenizer.Raw())), "/>")
		output.WriteString(opening)
		output.WriteString("></")
		output.WriteString(token.Data)
		output.WriteByte('>')
	}
}

type nodePosition struct {
	start int
	end   int
}

func indexDOM(node *html.Node, positions map[*html.Node]nodePosition, counter *int) {
	*counter++
	position := nodePosition{start: *counter}
	for child := node.FirstChild; child != nil; child = child.NextSibling {
		indexDOM(child, positions, counter)
	}
	*counter++
	position.end = *counter
	positions[node] = position
}

func cloneDOMRange(node *html.Node, positions map[*html.Node]nodePosition, start, end int) *html.Node {
	position := positions[node]
	if position.end <= start || position.start >= end {
		return nil
	}
	switch node.Type {
	case html.TextNode:
		return &html.Node{Type: html.TextNode, Data: node.Data}
	case html.ElementNode:
		clone := &html.Node{Type: html.ElementNode, Data: node.Data, Namespace: node.Namespace, Attr: append([]html.Attribute(nil), node.Attr...)}
		for child := node.FirstChild; child != nil; child = child.NextSibling {
			if childClone := cloneDOMRange(child, positions, start, end); childClone != nil {
				clone.AppendChild(childClone)
			}
		}
		if clone.FirstChild == nil && !isVoidElement(clone.Data) {
			return nil
		}
		return clone
	default:
		return nil
	}
}

func findAnchor(root *html.Node, fragment string) *html.Node {
	return findNode(root, func(node *html.Node) bool {
		if node.Type != html.ElementNode {
			return false
		}
		return nodeAttribute(node, "id") == fragment || nodeAttribute(node, "name") == fragment
	})
}

func rangeBoundary(anchor, body *html.Node) *html.Node {
	for current := anchor; current != nil && current != body; current = current.Parent {
		if isBlockElement(current.Data) {
			return current
		}
	}
	return anchor
}

func isBlockElement(name string) bool {
	switch strings.ToLower(name) {
	case "address", "article", "aside", "blockquote", "div", "dl", "fieldset", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "ul":
		return true
	default:
		return false
	}
}

func isVoidElement(name string) bool {
	switch strings.ToLower(name) {
	case "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr":
		return true
	default:
		return false
	}
}

func normalizedText(value string) string {
	doc, err := html.Parse(strings.NewReader(value))
	if err != nil {
		return ""
	}
	return nodeText(doc)
}
