package epubimport

import (
	"bytes"
	"net/url"
	"strings"

	"golang.org/x/net/html"
)

// SanitizeHTML removes executable and externally fetched EPUB markup while
// retaining the semantic elements accepted by the deterministic converter.
// It returns a fragment, never a complete document.
func SanitizeHTML(raw string) (string, []Diagnostic, error) {
	doc, err := html.Parse(strings.NewReader(raw))
	if err != nil {
		return "", nil, &Error{Code: CodeInvalidNavigation, Message: "chapter HTML is invalid"}
	}
	body := findNode(doc, func(node *html.Node) bool {
		return node.Type == html.ElementNode && strings.EqualFold(node.Data, "body")
	})
	if body == nil {
		body = doc
	}
	var diagnostics []Diagnostic
	sanitizeChildren(body, &diagnostics)
	var output bytes.Buffer
	for child := body.FirstChild; child != nil; child = child.NextSibling {
		if err := html.Render(&output, child); err != nil {
			return "", diagnostics, &Error{Code: CodeInvalidNavigation, Message: "chapter HTML cannot be serialized"}
		}
	}
	return output.String(), diagnostics, nil
}

func sanitizeChildren(parent *html.Node, diagnostics *[]Diagnostic) {
	for child := parent.FirstChild; child != nil; {
		next := child.NextSibling
		if child.Type == html.CommentNode {
			parent.RemoveChild(child)
			child = next
			continue
		}
		if child.Type != html.ElementNode {
			child = next
			continue
		}
		if blockedElement(child.Data) {
			parent.RemoveChild(child)
			*diagnostics = append(*diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "unsafe EPUB element removed"})
			child = next
			continue
		}
		child.Attr = sanitizeAttributes(child, child.Attr, diagnostics)
		sanitizeChildren(child, diagnostics)
		child = next
	}
}

func blockedElement(name string) bool {
	switch strings.ToLower(name) {
	case "script", "style", "base", "form", "iframe", "frame", "frameset", "embed", "object", "applet", "meta", "link":
		return true
	default:
		return false
	}
}

func sanitizeAttributes(node *html.Node, attributes []html.Attribute, diagnostics *[]Diagnostic) []html.Attribute {
	result := make([]html.Attribute, 0, len(attributes))
	for _, attribute := range attributes {
		key := strings.ToLower(attribute.Key)
		if strings.HasPrefix(key, "on") || key == "style" || key == "srcdoc" {
			*diagnostics = append(*diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "unsafe EPUB attribute removed"})
			continue
		}
		switch key {
		case "href", "xlink:href":
			if !safeLinkURL(attribute.Val) {
				*diagnostics = append(*diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "unsafe EPUB link removed"})
				continue
			}
		case "src":
			if !safeResourceURL(attribute.Val, strings.EqualFold(node.Data, "img")) {
				*diagnostics = append(*diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "unsafe EPUB resource removed"})
				continue
			}
		case "srcset":
			value := sanitizeSrcset(attribute.Val)
			if value == "" {
				*diagnostics = append(*diagnostics, Diagnostic{Code: CodeUnsupportedResource, Message: "unsafe EPUB srcset removed"})
				continue
			}
			attribute.Val = value
		}
		result = append(result, attribute)
	}
	return result
}

func safeLinkURL(raw string) bool {
	value := strings.TrimSpace(raw)
	if value == "" || strings.HasPrefix(value, "#") {
		return true
	}
	parsed, err := url.Parse(value)
	if err != nil {
		return false
	}
	switch strings.ToLower(parsed.Scheme) {
	case "", "http", "https", "mailto":
		return true
	default:
		return false
	}
}

func safeResourceURL(raw string, image bool) bool {
	value := strings.TrimSpace(raw)
	if value == "" {
		return false
	}
	if strings.HasPrefix(strings.ToLower(value), "data:") {
		return image && strings.HasPrefix(strings.ToLower(value), "data:image/")
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.IsAbs() || strings.HasPrefix(value, "//") {
		return false
	}
	// Resolved EPUB assets are served through the platform media route. This is
	// the only absolute-path resource allowed by the import profile; all other
	// absolute references could escape the Book-owned asset boundary.
	if strings.HasPrefix(parsed.Path, "/media/") {
		return image && parsed.RawQuery == "" && parsed.Fragment == ""
	}
	return !strings.HasPrefix(parsed.Path, "/") && !strings.Contains(parsed.Path, "\\")
}

func sanitizeSrcset(raw string) string {
	parts := strings.Split(raw, ",")
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		fields := strings.Fields(strings.TrimSpace(part))
		if len(fields) == 0 || !safeResourceURL(fields[0], true) {
			continue
		}
		result = append(result, strings.Join(fields, " "))
	}
	return strings.Join(result, ", ")
}
