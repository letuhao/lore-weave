package epubimport

import (
	"strings"
	"testing"
)

// These generated fixtures are deliberately small, redistributable EPUB
// archives. They exercise the invariants that previously regressed when EPUB
// content was flattened or sliced as strings, without storing copyrighted
// book text in the repository.
func TestEPUBCorpusExtractsOneLogicalChapterAcrossContentDocuments(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf":           `<package version="3.0"><manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/><item id="b" href="b.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>`,
		"OPS/a.xhtml":            `<html><body><section id="start"><p>first source segment</p></section></body></html>`,
		"OPS/b.xhtml":            `<html><body><section><p>second source segment</p></section></body></html>`,
	})
	fragment, diagnostics, err := ExtractChapter(data, NavigationNode{ContentRanges: []ContentRange{{Href: "OPS/a.xhtml", StartAnchor: "start"}, {Href: "OPS/b.xhtml"}}}, Limits{})
	if err != nil || len(diagnostics) != 0 {
		t.Fatalf("ExtractChapter() error=%v diagnostics=%#v", err, diagnostics)
	}
	text := normalizedText(fragment)
	if !strings.Contains(text, "first source segment") || !strings.Contains(text, "second source segment") {
		t.Fatalf("multi-document chapter lost source text: %q", text)
	}
}

func TestEPUBCorpusResolvesPercentEncodedCyrillicNavigationPath(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf":           `<package version="3.0"><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="chapter" href="text/глава 1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"OPS/nav.xhtml":          `<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="text/%D0%B3%D0%BB%D0%B0%D0%B2%D0%B0%201.xhtml#начало">Глава</a></li></ol></nav></body></html>`,
		"OPS/text/глава 1.xhtml": `<html><body><section id="начало"><p>cyrillic anchor text</p></section></body></html>`,
	})
	inspection, err := Inspect(data, Limits{})
	if err != nil {
		t.Fatal(err)
	}
	nodes := SelectedNodes(inspection.Structure)
	if len(nodes) != 1 || nodes[0].SourceHref != "OPS/text/глава 1.xhtml" || nodes[0].SourceFragment != "начало" {
		t.Fatalf("normalized navigation = %#v", nodes)
	}
	fragment, _, err := ExtractChapter(data, *nodes[0], Limits{})
	if err != nil || !strings.Contains(fragment, "cyrillic anchor text") {
		t.Fatalf("ExtractChapter() error=%v fragment=%q", err, fragment)
	}
}

func TestEPUBCorpusReportsMissingAnchorWithoutDiscardingContent(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
		"book.opf":               `<package><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"chapter.xhtml":          `<html><body><p>retained fallback content</p></body></html>`,
	})
	fragment, diagnostics, err := ExtractChapter(data, NavigationNode{ContentRanges: []ContentRange{{Href: "chapter.xhtml", StartAnchor: "missing"}}}, Limits{})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(fragment, "retained fallback content") {
		t.Fatalf("missing-anchor fallback lost content: %q", fragment)
	}
	if len(diagnostics) != 1 || diagnostics[0].Code != CodeAnchorMissing {
		t.Fatalf("diagnostics = %#v", diagnostics)
	}
}

func TestEPUBCorpusFindsEPUB3CoverCandidate(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf":           `<package version="3.0"><metadata><title>Fixture</title></metadata><manifest><item id="cover" href="images/cover.png" media-type="image/png" properties="cover-image"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"OPS/chapter.xhtml":      `<html><body><p>fixture</p></body></html>`,
		"OPS/images/cover.png":   string([]byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}),
	})
	inspection, err := Inspect(data, Limits{})
	if err != nil {
		t.Fatal(err)
	}
	if inspection.Cover == nil || inspection.Cover.SourcePath != "OPS/images/cover.png" || inspection.Cover.SourceMethod != "epub3-cover-image" {
		t.Fatalf("cover = %#v", inspection.Cover)
	}
}

func TestEPUBCorpusRejectsMalformedManifestAndCompressionBomb(t *testing.T) {
	t.Run("malformed manifest", func(t *testing.T) {
		data := buildTestEPUB(t, map[string]string{
			"mimetype":               epubMIME,
			"META-INF/container.xml": `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
			"book.opf":               `<package><manifest><item`,
		})
		_, err := Inspect(data, Limits{})
		assertCode(t, err, CodeInvalidOPF)
	})
	t.Run("compression ratio", func(t *testing.T) {
		data := buildTestEPUB(t, map[string]string{
			"mimetype":               epubMIME,
			"META-INF/container.xml": `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
			"book.opf":               `<package><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
			"chapter.xhtml":          `<html><body>` + strings.Repeat("compressible fixture text ", 1024) + `</body></html>`,
		})
		_, err := Inspect(data, Limits{MaxCompressionRatio: 1.1})
		assertCode(t, err, CodeArchiveLimit)
	})
}

func TestEPUBCorpusBoundsNavigationNodeCount(t *testing.T) {
	var entries strings.Builder
	for index := 0; index < 4; index++ {
		entries.WriteString(`<li><a href="chapter.xhtml#start">Repeated chapter</a></li>`)
	}
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf":           `<package version="3.0"><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"OPS/nav.xhtml":          `<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>` + entries.String() + `</ol></nav></body></html>`,
		"OPS/chapter.xhtml":      `<html><body><p id="start">fixture</p></body></html>`,
	})
	_, err := Inspect(data, Limits{MaxNavigationNodes: 3})
	assertCode(t, err, CodeArchiveLimit)
}
