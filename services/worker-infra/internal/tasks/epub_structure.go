package tasks

import (
	"archive/zip"
	"bytes"
	"encoding/xml"
	"fmt"
	"path"
	"regexp"
	"strings"
)

type epubChapter struct {
	Title string
	Path  string
	HTML  string
}

type epubContainer struct {
	Rootfiles []struct {
		FullPath string `xml:"full-path,attr"`
	} `xml:"rootfiles>rootfile"`
}

type epubPackage struct {
	Manifest struct {
		Items []struct {
			ID        string `xml:"id,attr"`
			Href      string `xml:"href,attr"`
			MediaType string `xml:"media-type,attr"`
		} `xml:"item"`
	} `xml:"manifest"`
	Spine struct {
		Itemrefs []struct {
			IDRef string `xml:"idref,attr"`
		} `xml:"itemref"`
	} `xml:"spine"`
}

type epubNavMap struct {
	Points []epubNavPoint `xml:"navMap>navPoint"`
}

type epubNavPoint struct {
	Label struct {
		Text string `xml:"text"`
	} `xml:"navLabel"`
	Content struct {
		Src string `xml:"src,attr"`
	} `xml:"content"`
	Children []epubNavPoint `xml:"navPoint"`
}

type epubNavEntry struct {
	Title    string
	Path     string
	Fragment string
}

// extractEPUBChapters preserves the EPUB navigation boundaries. It handles
// both the common one-XHTML-per-chapter layout and EPUBs where several NCX
// entries point at different anchors in the same XHTML document.
func extractEPUBChapters(data []byte) ([]epubChapter, error) {
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, fmt.Errorf("epub zip: %w", err)
	}
	files := make(map[string]*zip.File, len(zr.File))
	for _, f := range zr.File {
		files[path.Clean(f.Name)] = f
	}
	containerFile, ok := files["META-INF/container.xml"]
	if !ok {
		return nil, fmt.Errorf("epub: META-INF/container.xml missing")
	}
	containerBytes, err := readZipFile(containerFile)
	if err != nil {
		return nil, err
	}
	var container epubContainer
	if err := xml.Unmarshal(containerBytes, &container); err != nil || len(container.Rootfiles) == 0 {
		return nil, fmt.Errorf("epub: invalid container.xml")
	}
	opfPath := path.Clean(container.Rootfiles[0].FullPath)
	opfFile, ok := files[opfPath]
	if !ok {
		return nil, fmt.Errorf("epub: package %q missing", opfPath)
	}
	opfBytes, err := readZipFile(opfFile)
	if err != nil {
		return nil, err
	}
	var pkg epubPackage
	if err := xml.Unmarshal(opfBytes, &pkg); err != nil {
		return nil, fmt.Errorf("epub: invalid package: %w", err)
	}
	base := path.Dir(opfPath)
	manifest := make(map[string]string, len(pkg.Manifest.Items))
	for _, item := range pkg.Manifest.Items {
		loHref := strings.ToLower(item.Href)
		if item.MediaType == "application/xhtml+xml" || strings.HasSuffix(loHref, ".xhtml") || strings.HasSuffix(loHref, ".html") {
			manifest[item.ID] = path.Clean(path.Join(base, item.Href))
		}
	}

	var nav []epubNavEntry
	for _, item := range pkg.Manifest.Items {
		if !strings.Contains(strings.ToLower(item.MediaType), "ncx") && !strings.HasSuffix(strings.ToLower(item.Href), ".ncx") {
			continue
		}
		if f, ok := files[path.Clean(path.Join(base, item.Href))]; ok {
			if b, e := readZipFile(f); e == nil {
				var navMap epubNavMap
				if xml.Unmarshal(b, &navMap) == nil {
					for _, p := range navMap.Points {
						collectEPUBNavEntries(&nav, base, p)
					}
				}
			}
		}
	}

	// The NCX is authoritative when it has entries. Grouping by source path
	// lets us split multiple chapter anchors within the same XHTML file.
	if len(nav) > 0 {
		raw := make(map[string]string)
		for _, e := range nav {
			if _, ok := raw[e.Path]; ok {
				continue
			}
			f, ok := files[e.Path]
			if !ok {
				continue
			}
			b, e2 := readZipFile(f)
			if e2 != nil {
				return nil, e2
			}
			raw[e.Path] = epubBodyHTML(b)
		}
		chapters := make([]epubChapter, 0, len(nav))
		for i, e := range nav {
			body, ok := raw[e.Path]
			if !ok || strings.Contains(strings.ToLower(path.Base(e.Path)), "cover") {
				continue
			}
			start := 0
			if e.Fragment != "" {
				start = epubFragmentOffset(body, e.Fragment)
				if start < 0 {
					start = 0
				}
			}
			end := len(body)
			for j := i + 1; j < len(nav); j++ {
				if nav[j].Path != e.Path {
					continue
				}
				if nav[j].Fragment == "" {
					end = len(body)
					break
				}
				next := epubFragmentOffset(body, nav[j].Fragment)
				if next >= 0 && next > start {
					end = next
				}
				break
			}
			if end <= start {
				continue
			}
			html := body[start:end]
			if strings.TrimSpace(stripTagsForSize(html)) == "" {
				continue
			}
			title := strings.TrimSpace(e.Title)
			if title == "" {
				title = fmt.Sprintf("Глава %d", len(chapters)+1)
			}
			chapters = append(chapters, epubChapter{Title: title, Path: e.Path, HTML: html})
		}
		if len(chapters) > 0 {
			return chapters, nil
		}
	}

	// EPUBs without an NCX still retain their spine document boundaries.
	chapters := make([]epubChapter, 0, len(pkg.Spine.Itemrefs))
	for _, ref := range pkg.Spine.Itemrefs {
		xhtmlPath, ok := manifest[ref.IDRef]
		if !ok || strings.Contains(strings.ToLower(path.Base(xhtmlPath)), "cover") {
			continue
		}
		f, ok := files[xhtmlPath]
		if !ok {
			continue
		}
		b, err := readZipFile(f)
		if err != nil {
			return nil, err
		}
		html := epubBodyHTML(b)
		if strings.TrimSpace(stripTagsForSize(html)) == "" {
			continue
		}
		chapters = append(chapters, epubChapter{Path: xhtmlPath, HTML: html})
	}
	if len(chapters) == 0 {
		return nil, fmt.Errorf("epub: no chapter documents found")
	}
	return chapters, nil
}

func collectEPUBNavEntries(dst *[]epubNavEntry, base string, p epubNavPoint) {
	src := strings.TrimSpace(p.Content.Src)
	if src != "" {
		parts := strings.SplitN(src, "#", 2)
		e := epubNavEntry{Path: path.Clean(path.Join(base, parts[0])), Title: strings.TrimSpace(p.Label.Text)}
		if len(parts) == 2 {
			e.Fragment = parts[1]
		}
		*dst = append(*dst, e)
	}
	for _, child := range p.Children {
		collectEPUBNavEntries(dst, base, child)
	}
}

func epubFragmentOffset(body, fragment string) int {
	if fragment == "" {
		return 0
	}
	quoted := regexp.QuoteMeta(fragment)
	for _, expr := range []string{`(?i)\bid\s*=\s*["']` + quoted + `["']`, `(?i)\bname\s*=\s*["']` + quoted + `["']`} {
		if loc := regexp.MustCompile(expr).FindStringIndex(body); loc != nil {
			return loc[0]
		}
	}
	return -1
}

func readZipFile(f *zip.File) ([]byte, error) {
	r, err := f.Open()
	if err != nil {
		return nil, fmt.Errorf("epub open %q: %w", f.Name, err)
	}
	defer r.Close()
	var b bytes.Buffer
	if _, err := b.ReadFrom(r); err != nil {
		return nil, fmt.Errorf("epub read %q: %w", f.Name, err)
	}
	return b.Bytes(), nil
}

func epubBodyHTML(data []byte) string {
	s := string(data)
	lo := strings.ToLower(s)
	start := strings.Index(lo, "<body")
	if start < 0 {
		return s
	}
	gt := strings.Index(s[start:], ">")
	if gt < 0 {
		return s
	}
	start += gt + 1
	endRel := strings.Index(strings.ToLower(s[start:]), "</body>")
	if endRel < 0 {
		return s[start:]
	}
	return s[start : start+endRel]
}

func stripTagsForSize(s string) string {
	var b strings.Builder
	inTag := false
	for _, r := range s {
		switch r {
		case '<':
			inTag = true
		case '>':
			inTag = false
		default:
			if !inTag {
				b.WriteRune(r)
			}
		}
	}
	return b.String()
}
