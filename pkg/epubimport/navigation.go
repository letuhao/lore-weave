package epubimport

import (
	"encoding/xml"
	"fmt"
	"net/url"
	"path"
	"strings"

	"golang.org/x/net/html"
)

type ncxDocument struct {
	Points []ncxNavPoint `xml:"navMap>navPoint"`
}

type ncxNavPoint struct {
	PlayOrder string `xml:"playOrder,attr"`
	Label     struct {
		Text string `xml:"text"`
	} `xml:"navLabel"`
	Content struct {
		Src string `xml:"src,attr"`
	} `xml:"content"`
	Children []ncxNavPoint `xml:"navPoint"`
}

func (a *archive) navigation(sourceSHA string) ([]*NavigationNode, NavigationSource, []Diagnostic, error) {
	for _, item := range a.pkg.Manifest.Items {
		if !isNavigationDocument(item) {
			continue
		}
		itemPath, err := a.resolve(item.Href)
		if err != nil {
			return nil, "", nil, err
		}
		file, ok := a.files[itemPath]
		if !ok {
			return nil, "", nil, &Error{Code: CodeInvalidNavigation, Message: "EPUB navigation document is missing"}
		}
		data, err := a.read(file)
		if err != nil {
			return nil, "", nil, err
		}
		structure, warnings, err := a.parseEPUB3Nav(sourceSHA, path.Dir(itemPath), data)
		if err != nil {
			return nil, "", nil, err
		}
		if len(structure) > 0 {
			a.assignRanges(structure)
			return structure, NavigationEPUB3Nav, warnings, nil
		}
	}

	manifest := a.manifestByID()
	if a.pkg.Spine.TOC != "" {
		if item, ok := manifest[a.pkg.Spine.TOC]; ok {
			structure, warnings, err := a.parseNCXItem(sourceSHA, item)
			if err != nil {
				return nil, "", nil, err
			}
			if len(structure) > 0 {
				a.assignRanges(structure)
				return structure, NavigationEPUB2NCX, warnings, nil
			}
		}
	}
	for _, item := range a.pkg.Manifest.Items {
		if !isNCX(item) {
			continue
		}
		structure, warnings, err := a.parseNCXItem(sourceSHA, item)
		if err != nil {
			continue
		}
		if len(structure) > 0 {
			a.assignRanges(structure)
			return structure, NavigationEPUB2NCX, warnings, nil
		}
	}

	structure, warnings, err := a.spineFallback(sourceSHA)
	if err != nil {
		return nil, "", nil, err
	}
	return structure, NavigationSpine, append([]Diagnostic{{Code: CodeNavigationMissing, Message: "navigation document missing; OPF spine fallback used"}}, warnings...), nil
}

func (a *archive) parseEPUB3Nav(sourceSHA, base string, data []byte) ([]*NavigationNode, []Diagnostic, error) {
	doc, err := html.Parse(strings.NewReader(string(data)))
	if err != nil {
		return nil, nil, &Error{Code: CodeInvalidNavigation, Message: "EPUB navigation document is invalid HTML"}
	}
	nav := findNode(doc, func(node *html.Node) bool {
		return node.Type == html.ElementNode && strings.EqualFold(node.Data, "nav") && strings.EqualFold(nodeAttribute(node, "epub:type"), "toc")
	})
	if nav == nil {
		return nil, nil, nil
	}
	ol := firstDescendant(nav, "ol")
	if ol == nil {
		return nil, nil, &Error{Code: CodeInvalidNavigation, Message: "EPUB table of contents has no ordered list"}
	}
	state := navigationState{archive: a, sourceSHA: sourceSHA, max: a.limit.MaxNavigationNodes}
	structure, err := state.parseHTMLList(ol, base, "", 0)
	if err != nil {
		return nil, nil, err
	}
	return structure, state.warnings, nil
}

func (a *archive) parseNCXItem(sourceSHA string, item opfManifestItem) ([]*NavigationNode, []Diagnostic, error) {
	itemPath, err := a.resolve(item.Href)
	if err != nil {
		return nil, nil, err
	}
	file, ok := a.files[itemPath]
	if !ok {
		return nil, nil, &Error{Code: CodeInvalidNavigation, Message: "NCX navigation document is missing"}
	}
	data, err := a.read(file)
	if err != nil {
		return nil, nil, err
	}
	var ncx ncxDocument
	if err := xml.Unmarshal(data, &ncx); err != nil {
		return nil, nil, &Error{Code: CodeInvalidNavigation, Message: "NCX navigation document is invalid XML"}
	}
	state := navigationState{archive: a, sourceSHA: sourceSHA, max: a.limit.MaxNavigationNodes}
	structure := make([]*NavigationNode, 0, len(ncx.Points))
	for _, point := range ncx.Points {
		node, err := state.parseNCXPoint(point, path.Dir(itemPath), "", 0)
		if err != nil {
			return nil, nil, err
		}
		structure = append(structure, node)
	}
	return structure, state.warnings, nil
}

type navigationState struct {
	archive   *archive
	sourceSHA string
	max       int
	ordinal   int
	seen      map[string]int
	warnings  []Diagnostic
}

func (s *navigationState) nextNode(title, rawHref, base, parent string, depth int) (*NavigationNode, error) {
	s.ordinal++
	if s.ordinal > s.max {
		return nil, archiveLimit("navigation node count exceeds configured limit")
	}
	if s.seen == nil {
		s.seen = make(map[string]int)
	}
	node := &NavigationNode{
		Ordinal:         s.ordinal - 1,
		Depth:           depth,
		ParentSourceKey: parent,
		Role:            roleFor(title, rawHref),
		Title:           strings.TrimSpace(title),
		Linear:          true,
	}
	if node.Title == "" {
		node.Title = fmt.Sprintf("Chapter %d", node.Ordinal+1)
		node.Warnings = append(node.Warnings, Diagnostic{Code: CodeRangeAmbiguous, Message: "navigation node has no title"})
	}
	parts := splitHref(rawHref)
	if parts.path == "" {
		node.Warnings = append(node.Warnings, Diagnostic{Code: CodeRangeAmbiguous, Message: "navigation node has no content target"})
		return node, nil
	}
	resolved, err := s.archive.resolveFrom(base, parts.path)
	if err != nil {
		return nil, err
	}
	if _, ok := s.archive.files[resolved]; !ok {
		node.Warnings = append(node.Warnings, Diagnostic{Code: CodeContentUnavailable, Message: "navigation target is missing from archive"})
	}
	node.SourceHref = resolved
	node.SourceFragment = parts.fragment
	baseKey := "sha256:" + s.sourceSHA + ":" + resolved
	if parts.fragment != "" {
		baseKey += "#" + parts.fragment
	}
	s.seen[baseKey]++
	node.SourceKey = baseKey
	if s.seen[baseKey] > 1 {
		node.SourceKey = fmt.Sprintf("%s@%d", baseKey, s.seen[baseKey])
		node.Warnings = append(node.Warnings, Diagnostic{Code: CodeRangeAmbiguous, Message: "multiple navigation nodes target the same source range"})
	}
	return node, nil
}

func (s *navigationState) parseHTMLList(ol *html.Node, base, parent string, depth int) ([]*NavigationNode, error) {
	result := make([]*NavigationNode, 0)
	for child := ol.FirstChild; child != nil; child = child.NextSibling {
		if child.Type != html.ElementNode || !strings.EqualFold(child.Data, "li") {
			continue
		}
		anchor := firstDescendant(child, "a")
		var title, href string
		if anchor != nil {
			title = strings.TrimSpace(nodeText(anchor))
			href = nodeAttribute(anchor, "href")
		}
		node, err := s.nextNode(title, href, base, parent, depth)
		if err != nil {
			return nil, err
		}
		if nested := firstChildElement(child, "ol"); nested != nil {
			node.Children, err = s.parseHTMLList(nested, base, node.SourceKey, depth+1)
			if err != nil {
				return nil, err
			}
		}
		node.Selected = len(node.Children) == 0 && node.SourceHref != ""
		result = append(result, node)
	}
	return result, nil
}

func (s *navigationState) parseNCXPoint(point ncxNavPoint, base, parent string, depth int) (*NavigationNode, error) {
	node, err := s.nextNode(point.Label.Text, point.Content.Src, base, parent, depth)
	if err != nil {
		return nil, err
	}
	for _, child := range point.Children {
		parsed, err := s.parseNCXPoint(child, base, node.SourceKey, depth+1)
		if err != nil {
			return nil, err
		}
		node.Children = append(node.Children, parsed)
	}
	node.Selected = len(node.Children) == 0 && node.SourceHref != ""
	return node, nil
}

func (a *archive) spineFallback(sourceSHA string) ([]*NavigationNode, []Diagnostic, error) {
	manifest := a.manifestByID()
	structure := make([]*NavigationNode, 0, len(a.pkg.Spine.Itemrefs))
	for ordinal, ref := range a.pkg.Spine.Itemrefs {
		item, ok := manifest[ref.IDRef]
		if !ok || !isContentDocument(item) {
			continue
		}
		itemPath, err := a.resolve(item.Href)
		if err != nil {
			return nil, nil, err
		}
		title := a.contentTitle(itemPath)
		linear := !strings.EqualFold(strings.TrimSpace(ref.Linear), "no")
		node := &NavigationNode{
			SourceKey:  "sha256:" + sourceSHA + ":" + itemPath,
			SourceHref: itemPath,
			Ordinal:    ordinal,
			Role:       roleFor(title, itemPath),
			Title:      title,
			Linear:     linear,
			Selected:   linear,
			ContentRanges: []ContentRange{{
				Href: itemPath,
			}},
		}
		if !linear {
			node.Warnings = append(node.Warnings, Diagnostic{Code: CodeRangeAmbiguous, Message: "non-linear spine item is not selected by default"})
		}
		structure = append(structure, node)
		if len(structure) > a.limit.MaxNavigationNodes {
			return nil, nil, archiveLimit("navigation node count exceeds configured limit")
		}
	}
	if len(structure) == 0 {
		return nil, nil, &Error{Code: CodeInvalidNavigation, Message: "EPUB has no usable content documents"}
	}
	return structure, nil, nil
}

func (a *archive) contentTitle(itemPath string) string {
	file, ok := a.files[itemPath]
	if !ok {
		return fallbackTitle(itemPath)
	}
	data, err := a.read(file)
	if err != nil {
		return fallbackTitle(itemPath)
	}
	doc, err := html.Parse(strings.NewReader(string(data)))
	if err != nil {
		return fallbackTitle(itemPath)
	}
	for _, tag := range []string{"h1", "h2", "title"} {
		if node := firstDescendant(doc, tag); node != nil {
			if title := strings.TrimSpace(nodeText(node)); title != "" {
				return title
			}
		}
	}
	return fallbackTitle(itemPath)
}

func fallbackTitle(itemPath string) string {
	name := strings.TrimSuffix(path.Base(itemPath), path.Ext(itemPath))
	if name == "" {
		return "Chapter"
	}
	return name
}

func (a *archive) assignRanges(structure []*NavigationNode) {
	selected := flattenSelected(structure)
	for index, node := range selected {
		contentRange := ContentRange{Href: node.SourceHref, StartAnchor: node.SourceFragment}
		for next := index + 1; next < len(selected); next++ {
			if selected[next].SourceHref == node.SourceHref {
				contentRange.EndAnchor = selected[next].SourceFragment
				break
			}
		}
		node.ContentRanges = []ContentRange{contentRange}
	}
}

func flattenSelected(nodes []*NavigationNode) []*NavigationNode {
	var result []*NavigationNode
	var walk func([]*NavigationNode)
	walk = func(current []*NavigationNode) {
		for _, node := range current {
			if node.Selected {
				result = append(result, node)
			}
			walk(node.Children)
		}
	}
	walk(nodes)
	return result
}

// SelectedNodes returns selected logical chapters in source navigation order.
// It is intentionally exported so worker-infra does not recreate traversal or
// accidentally turn hierarchy nodes into chapters.
func SelectedNodes(nodes []*NavigationNode) []*NavigationNode {
	return flattenSelected(nodes)
}

func (a *archive) resolveFrom(base, href string) (string, error) {
	decoded, err := decodeReferencePath(href)
	if err != nil {
		return "", err
	}
	return canonicalArchivePath(path.Join(base, decoded))
}

func decodeReferencePath(raw string) (string, error) {
	parts := splitHref(raw)
	if parts.path == "" {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB reference path is empty"}
	}
	decoded, err := url.PathUnescape(parts.path)
	if err != nil || strings.HasPrefix(decoded, "/") || strings.Contains(decoded, "\\") {
		return "", &Error{Code: CodeInvalidArchivePath, Message: "EPUB reference path is unsafe"}
	}
	return decoded, nil
}

func roleFor(title, href string) Role {
	value := strings.ToLower(title + " " + href)
	switch {
	case strings.Contains(value, "frontmatter"), strings.Contains(value, "front-matter"):
		return RoleFrontmatter
	case strings.Contains(value, "backmatter"), strings.Contains(value, "back-matter"):
		return RoleBackmatter
	case strings.Contains(value, "appendix"):
		return RoleAppendix
	case strings.Contains(value, "volume"):
		return RoleVolume
	case strings.Contains(value, "part"):
		return RolePart
	case strings.Contains(value, "section"):
		return RoleSection
	default:
		return RoleChapter
	}
}

func findNode(root *html.Node, predicate func(*html.Node) bool) *html.Node {
	if predicate(root) {
		return root
	}
	for child := root.FirstChild; child != nil; child = child.NextSibling {
		if found := findNode(child, predicate); found != nil {
			return found
		}
	}
	return nil
}

func firstDescendant(root *html.Node, tag string) *html.Node {
	for child := root.FirstChild; child != nil; child = child.NextSibling {
		if child.Type == html.ElementNode && strings.EqualFold(child.Data, tag) {
			return child
		}
		if found := firstDescendant(child, tag); found != nil {
			return found
		}
	}
	return nil
}

func firstChildElement(root *html.Node, tag string) *html.Node {
	for child := root.FirstChild; child != nil; child = child.NextSibling {
		if child.Type == html.ElementNode && strings.EqualFold(child.Data, tag) {
			return child
		}
	}
	return nil
}

func nodeAttribute(node *html.Node, name string) string {
	for _, attribute := range node.Attr {
		qualified := attribute.Namespace + ":" + attribute.Key
		if strings.EqualFold(attribute.Key, name) || strings.EqualFold(qualified, name) {
			return strings.TrimSpace(attribute.Val)
		}
	}
	return ""
}

func nodeText(root *html.Node) string {
	var builder strings.Builder
	var walk func(*html.Node)
	walk = func(node *html.Node) {
		if node.Type == html.TextNode {
			builder.WriteString(node.Data)
		}
		for child := node.FirstChild; child != nil; child = child.NextSibling {
			walk(child)
		}
	}
	walk(root)
	return strings.Join(strings.Fields(builder.String()), " ")
}
