package tasks

import (
	"encoding/base64"
	"encoding/xml"
	"fmt"
	"html"
	"log/slog"
	"strings"
)

const (
	fb2Namespace          = "http://www.gribuser.ru/xml/fictionbook/2.0"
	maxFB2Depth           = 64
	maxFB2DecodedImages   = 40 << 20
	maxFB2SingleImageSize = 10 << 20
)

type fb2Node struct {
	Name     xml.Name
	Attrs    []xml.Attr
	Children []*fb2Node
	Content  []fb2Content
	Text     strings.Builder
}

type fb2Content struct {
	Text  string
	Child *fb2Node
}

type fb2Binary struct {
	ContentType string
	Data        []byte
}

// fb2Document is the bounded structural representation needed by the importer.
// It deliberately retains only the main reading body and the metadata supplied by
// the FictionBook document; raw manuscripts must never be copied into logs.
type fb2Document struct {
	HTML     string
	Title    string
	Language string
	Summary  string
	Genres   []string
	Metadata map[string]any
	Cover    *fb2Binary
	Sections int
	Images   int
}

// extractFB2Document parses FictionBook 2.0/2.1/2.2-compatible XML. FB2 2.2
// retained the 2.0 namespace, so namespace validation is a compatibility guard
// rather than a file-name/version heuristic. The vendored XSD documents the full
// contract; this runtime parser intentionally supports the safe import subset.
func extractFB2Document(data []byte) (*fb2Document, error) {
	slog.Debug("fb2: parsing source", "source_bytes", len(data))
	root, err := parseFB2Tree(data)
	if err != nil {
		return nil, err
	}
	if root.Name.Local != "FictionBook" || root.Name.Space != fb2Namespace {
		return nil, fmt.Errorf("fb2: expected FictionBook root in %q namespace", fb2Namespace)
	}

	description := directChild(root, "description")
	titleInfo := directChild(description, "title-info")
	if titleInfo == nil {
		return nil, fmt.Errorf("fb2: missing description/title-info")
	}
	title := normalizedNodeText(directChild(titleInfo, "book-title"))
	if title == "" {
		return nil, fmt.Errorf("fb2: missing description/title-info/book-title")
	}
	language := normalizedNodeText(directChild(titleInfo, "lang"))
	summary := renderFB2Children(directChild(titleInfo, "annotation"), nil)
	genres := directChildTexts(titleInfo, "genre")

	binaries, err := fb2Binaries(root)
	if err != nil {
		return nil, err
	}
	cover, coverID := fb2Cover(titleInfo, binaries)
	body := mainFB2Body(root)
	if body == nil {
		return nil, fmt.Errorf("fb2: no main body with sections")
	}
	sections := directChildren(body, "section")
	if len(sections) == 0 {
		return nil, fmt.Errorf("fb2: main body has no sections")
	}

	var out strings.Builder
	out.WriteString("<html><head><title>")
	out.WriteString(html.EscapeString(title))
	out.WriteString("</title></head><body>")
	imageRefs := make(map[string]struct{})
	sectionCount := 0
	for _, section := range sections {
		level := 2 // top-level leaf sections are chapters in the implicit part.
		if len(directChildren(section, "section")) > 0 {
			level = 1 // a prose-free container is a source part with child chapters.
		}
		renderFB2Section(&out, section, level, imageRefs, &sectionCount)
	}
	out.WriteString("</body></html>")
	if out.Len() == 0 {
		return nil, fmt.Errorf("fb2: no importable content")
	}

	metadata := map[string]any{
		"title_info": map[string]any{
			"title": title, "language": language, "genres": genres,
			"authors": fb2People(titleInfo, "author"), "translators": fb2People(titleInfo, "translator"),
			"keywords":        normalizedNodeText(directChild(titleInfo, "keywords")),
			"source_language": normalizedNodeText(directChild(titleInfo, "src-lang")),
			"fields":          fb2MetadataEntries(titleInfo),
		},
		"document_info":   fb2MetadataEntries(directChild(description, "document-info")),
		"publish_info":    fb2MetadataEntries(directChild(description, "publish-info")),
		"custom_info":     fb2NodeMetadataEntries(directChildren(description, "custom-info")),
		"cover_binary_id": coverID,
	}
	slog.Info("fb2: parsed structure", "sections", sectionCount, "images", len(imageRefs), "has_cover", cover != nil)
	return &fb2Document{HTML: materializeFB2Images(out.String(), binaries), Title: title, Language: language, Summary: stripTags(summary), Genres: genres, Metadata: metadata, Cover: cover, Sections: sectionCount, Images: len(imageRefs)}, nil
}

func materializeFB2Images(markup string, binaries map[string]fb2Binary) string {
	for id, binary := range binaries {
		needle := "fb2://" + html.EscapeString(id)
		replacement := "data:" + binary.ContentType + ";base64," + base64.StdEncoding.EncodeToString(binary.Data)
		markup = strings.ReplaceAll(markup, needle, replacement)
	}
	return markup
}

func parseFB2Tree(data []byte) (*fb2Node, error) {
	dec := xml.NewDecoder(strings.NewReader(string(data)))
	var root *fb2Node
	stack := make([]*fb2Node, 0, 16)
	for {
		tok, err := dec.Token()
		if err != nil {
			if err.Error() == "EOF" {
				break
			}
			return nil, fmt.Errorf("fb2: parse XML: %w", err)
		}
		switch v := tok.(type) {
		case xml.Directive:
			if strings.Contains(strings.ToUpper(string(v)), "DOCTYPE") {
				return nil, fmt.Errorf("fb2: DTD declarations are not supported")
			}
		case xml.StartElement:
			if len(stack) >= maxFB2Depth {
				return nil, fmt.Errorf("fb2: XML nesting exceeds %d", maxFB2Depth)
			}
			n := &fb2Node{Name: v.Name, Attrs: v.Attr}
			if len(stack) == 0 {
				if root != nil {
					return nil, fmt.Errorf("fb2: multiple root elements")
				}
				root = n
			} else {
				stack[len(stack)-1].Children = append(stack[len(stack)-1].Children, n)
				stack[len(stack)-1].Content = append(stack[len(stack)-1].Content, fb2Content{Child: n})
			}
			stack = append(stack, n)
		case xml.CharData:
			if len(stack) > 0 {
				stack[len(stack)-1].Text.Write([]byte(v))
				stack[len(stack)-1].Content = append(stack[len(stack)-1].Content, fb2Content{Text: string(v)})
			}
		case xml.EndElement:
			if len(stack) == 0 || stack[len(stack)-1].Name != v.Name {
				return nil, fmt.Errorf("fb2: invalid XML element boundary")
			}
			stack = stack[:len(stack)-1]
		}
	}
	if root == nil || len(stack) != 0 {
		return nil, fmt.Errorf("fb2: incomplete XML document")
	}
	return root, nil
}

func directChild(n *fb2Node, local string) *fb2Node {
	if n == nil {
		return nil
	}
	for _, child := range n.Children {
		if child.Name.Local == local {
			return child
		}
	}
	return nil
}

func directChildren(n *fb2Node, local string) []*fb2Node {
	if n == nil {
		return nil
	}
	var result []*fb2Node
	for _, child := range n.Children {
		if child.Name.Local == local {
			result = append(result, child)
		}
	}
	return result
}

func directChildTexts(n *fb2Node, local string) []string {
	var values []string
	for _, child := range directChildren(n, local) {
		if text := normalizedNodeText(child); text != "" {
			values = append(values, text)
		}
	}
	return values
}

func normalizedNodeText(n *fb2Node) string {
	if n == nil {
		return ""
	}
	var out strings.Builder
	var walk func(*fb2Node)
	walk = func(current *fb2Node) {
		for _, item := range current.Content {
			out.WriteString(item.Text)
			if item.Child != nil {
				walk(item.Child)
			}
		}
	}
	walk(n)
	return strings.Join(strings.Fields(out.String()), " ")
}

func attr(n *fb2Node, local string) string {
	if n == nil {
		return ""
	}
	for _, a := range n.Attrs {
		if a.Name.Local == local {
			return strings.TrimSpace(a.Value)
		}
	}
	return ""
}

func fb2Binaries(root *fb2Node) (map[string]fb2Binary, error) {
	result := make(map[string]fb2Binary)
	total := 0
	for _, binary := range directChildren(root, "binary") {
		id, contentType := attr(binary, "id"), strings.ToLower(attr(binary, "content-type"))
		if id == "" || !strings.HasPrefix(contentType, "image/") {
			continue
		}
		decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(binary.Text.String()))
		if err != nil {
			return nil, fmt.Errorf("fb2: decode binary %q: %w", id, err)
		}
		if len(decoded) > maxFB2SingleImageSize || total+len(decoded) > maxFB2DecodedImages {
			return nil, fmt.Errorf("fb2: embedded image limit exceeded")
		}
		total += len(decoded)
		result[id] = fb2Binary{ContentType: contentType, Data: decoded}
	}
	return result, nil
}

func mainFB2Body(root *fb2Node) *fb2Node {
	bodies := directChildren(root, "body")
	for _, body := range bodies {
		if attr(body, "name") == "" {
			return body
		}
	}
	if len(bodies) > 0 {
		return bodies[0]
	}
	return nil
}

func fb2Cover(titleInfo *fb2Node, binaries map[string]fb2Binary) (*fb2Binary, string) {
	coverPage := directChild(titleInfo, "coverpage")
	image := directChild(coverPage, "image")
	id := strings.TrimPrefix(attr(image, "href"), "#")
	if binary, ok := binaries[id]; ok {
		copy := binary
		return &copy, id
	}
	return nil, ""
}

func fb2People(parent *fb2Node, local string) []map[string]string {
	people := []map[string]string{}
	for _, person := range directChildren(parent, local) {
		entry := map[string]string{}
		for _, key := range []string{"first-name", "middle-name", "last-name", "nickname", "email", "home-page"} {
			if value := normalizedNodeText(directChild(person, key)); value != "" {
				entry[key] = value
			}
		}
		if len(entry) > 0 {
			people = append(people, entry)
		}
	}
	return people
}

func fb2MetadataEntries(block *fb2Node) []map[string]any {
	if block == nil {
		return []map[string]any{}
	}
	return fb2NodeMetadataEntries(block.Children)
}

func fb2NodeMetadataEntries(nodes []*fb2Node) []map[string]any {
	metadata := make([]map[string]any, 0, len(nodes))
	for _, child := range nodes {
		entry := map[string]any{"name": child.Name.Local}
		if text := normalizedNodeText(child); text != "" {
			entry["value"] = text
		}
		if len(child.Attrs) > 0 {
			attrs := make(map[string]string, len(child.Attrs))
			for _, attr := range child.Attrs {
				attrs[attr.Name.Local] = attr.Value
			}
			entry["attributes"] = attrs
		}
		metadata = append(metadata, entry)
	}
	return metadata
}

func renderFB2Section(out *strings.Builder, section *fb2Node, level int, imageRefs map[string]struct{}, count *int) {
	*count++
	title := normalizedNodeText(directChild(section, "title"))
	children := directChildren(section, "section")
	if title != "" {
		fmt.Fprintf(out, "<h%d>%s</h%d>", min(level, 6), html.EscapeString(title), min(level, 6))
	}
	if len(children) > 0 {
		for _, child := range children {
			renderFB2Section(out, child, level+1, imageRefs, count)
		}
		return
	}
	out.WriteString(renderFB2Children(section, imageRefs))
}

func renderFB2Children(n *fb2Node, imageRefs map[string]struct{}) string {
	if n == nil {
		return ""
	}
	var out strings.Builder
	for _, child := range n.Children {
		switch child.Name.Local {
		case "title", "section", "annotation":
			continue
		case "p", "subtitle", "v":
			out.WriteString("<p>")
			out.WriteString(renderFB2Inline(child, imageRefs))
			out.WriteString("</p>")
		case "empty-line":
			out.WriteString("<br/>")
		case "cite", "epigraph":
			out.WriteString("<blockquote>")
			out.WriteString(renderFB2Children(child, imageRefs))
			out.WriteString("</blockquote>")
		case "poem":
			out.WriteString("<blockquote>")
			out.WriteString(renderFB2Children(child, imageRefs))
			out.WriteString("</blockquote>")
		case "image":
			out.WriteString(renderFB2Image(child, imageRefs))
		case "table":
			out.WriteString("<table>")
			out.WriteString(renderFB2Table(child, imageRefs))
			out.WriteString("</table>")
		}
	}
	return out.String()
}

func renderFB2Inline(n *fb2Node, imageRefs map[string]struct{}) string {
	if n == nil {
		return ""
	}
	var out strings.Builder
	for _, item := range n.Content {
		out.WriteString(html.EscapeString(item.Text))
		child := item.Child
		if child == nil {
			continue
		}
		value := renderFB2Inline(child, imageRefs)
		switch child.Name.Local {
		case "strong":
			out.WriteString("<strong>" + value + "</strong>")
		case "emphasis":
			out.WriteString("<em>" + value + "</em>")
		case "strikethrough":
			out.WriteString("<s>" + value + "</s>")
		case "sub":
			out.WriteString("<sub>" + value + "</sub>")
		case "sup":
			out.WriteString("<sup>" + value + "</sup>")
		case "code":
			out.WriteString("<code>" + value + "</code>")
		case "a":
			href := attr(child, "href")
			if strings.HasPrefix(href, "https://") || strings.HasPrefix(href, "http://") {
				out.WriteString("<a href=\"" + html.EscapeString(href) + "\">" + value + "</a>")
			} else {
				out.WriteString(value)
			}
		case "image":
			out.WriteString(renderFB2Image(child, imageRefs))
		default:
			out.WriteString(value)
		}
	}
	return out.String()
}

func renderFB2Image(n *fb2Node, imageRefs map[string]struct{}) string {
	id := strings.TrimPrefix(attr(n, "href"), "#")
	if id == "" {
		return ""
	}
	if imageRefs != nil {
		imageRefs[id] = struct{}{}
	}
	return "<img src=\"fb2://" + html.EscapeString(id) + "\" alt=\"" + html.EscapeString(attr(n, "alt")) + "\"/>"
}

func renderFB2Table(n *fb2Node, imageRefs map[string]struct{}) string {
	var out strings.Builder
	for _, row := range directChildren(n, "tr") {
		out.WriteString("<tr>")
		for _, cell := range row.Children {
			if cell.Name.Local == "td" || cell.Name.Local == "th" {
				out.WriteString("<" + cell.Name.Local + ">")
				out.WriteString(renderFB2Inline(cell, imageRefs))
				out.WriteString("</" + cell.Name.Local + ">")
			}
		}
		out.WriteString("</tr>")
	}
	return out.String()
}

func min(value, cap int) int {
	if value > cap {
		return cap
	}
	return value
}
