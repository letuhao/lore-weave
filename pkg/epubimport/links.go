package epubimport

import (
	"net/url"
	"path"
	"strings"

	"golang.org/x/net/html"
)

// InternalLink is a normalized EPUB hyperlink intent. OriginalHref is kept so
// the Book Service can rewrite the matching TipTap link mark during finalize;
// TargetHref and TargetFragment are archive-relative and never browser URLs.
type InternalLink struct {
	OriginalHref   string `json:"original_href"`
	TargetHref     string `json:"target_href"`
	TargetFragment string `json:"target_fragment,omitempty"`
}

// CollectInternalLinks finds safe archive-local links in a sanitized chapter
// fragment. External links are deliberately omitted: they remain unchanged in
// the document and must never be rewritten to Book-owned chapter routes.
func CollectInternalLinks(contentHref, rawHTML string) ([]InternalLink, []Diagnostic) {
	contentPath, err := canonicalArchivePath(contentHref)
	if err != nil {
		return nil, []Diagnostic{{Code: CodeInvalidArchivePath, Message: "chapter link base is invalid"}}
	}
	doc, err := html.Parse(strings.NewReader(rawHTML))
	if err != nil {
		return nil, []Diagnostic{{Code: CodeInvalidNavigation, Message: "chapter links cannot be parsed"}}
	}
	links := make([]InternalLink, 0)
	diagnostics := make([]Diagnostic, 0)
	seen := make(map[string]struct{})
	var walk func(*html.Node)
	walk = func(node *html.Node) {
		if node.Type == html.ElementNode && strings.EqualFold(node.Data, "a") {
			for _, attribute := range node.Attr {
				if !strings.EqualFold(attribute.Key, "href") {
					continue
				}
				link, ok := normalizeInternalLink(contentPath, attribute.Val)
				if !ok {
					break
				}
				key := link.OriginalHref + "\x00" + link.TargetHref + "\x00" + link.TargetFragment
				if _, exists := seen[key]; !exists {
					seen[key] = struct{}{}
					links = append(links, link)
				}
				break
			}
		}
		for child := node.FirstChild; child != nil; child = child.NextSibling {
			walk(child)
		}
	}
	walk(doc)
	return links, diagnostics
}

func normalizeInternalLink(contentPath, raw string) (InternalLink, bool) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return InternalLink{}, false
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.IsAbs() || parsed.Host != "" || strings.HasPrefix(value, "//") {
		return InternalLink{}, false
	}
	resolved := contentPath
	if parsed.EscapedPath() != "" {
		decoded, err := url.PathUnescape(parsed.EscapedPath())
		if err != nil || strings.HasPrefix(decoded, "/") || strings.Contains(decoded, "\\") {
			return InternalLink{}, false
		}
		resolved, err = canonicalArchivePath(path.Join(path.Dir(contentPath), decoded))
		if err != nil {
			return InternalLink{}, false
		}
	}
	return InternalLink{OriginalHref: raw, TargetHref: resolved, TargetFragment: parsed.Fragment}, true
}
