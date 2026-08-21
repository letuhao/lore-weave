package epubimport

import (
	"archive/zip"
	"bytes"
	"strings"
	"testing"
)

func TestInspectPrefersEPUB3NavigationAndPreservesNestedLeaves(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf": `<package version="3.0"><metadata><title>Test Book</title><creator>Author</creator><language>en</language></metadata><manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="one" href="chapter.xhtml" media-type="application/xhtml+xml"/>
</manifest><spine toc="ncx"><itemref idref="one"/></spine></package>`,
		"OPS/nav.xhtml": `<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>
<li><a href="chapter.xhtml#part">Part I</a><ol>
<li><a href="chapter.xhtml#one">One</a></li><li><a href="chapter.xhtml#two">Two</a></li>
</ol></li></ol></nav></body></html>`,
		"OPS/toc.ncx":       `<ncx><navMap><navPoint><navLabel><text>Legacy</text></navLabel><content src="chapter.xhtml#one"/></navPoint></navMap></ncx>`,
		"OPS/chapter.xhtml": `<html><head><title>Fallback</title></head><body><div id="part"><h1>Part I</h1></div><div id="one"><h2>One</h2><p>first text</p><h2>Not a chapter boundary</h2></div><div id="two"><h2>Two</h2><p>second text</p></div></body></html>`,
	})

	inspection, err := Inspect(data, Limits{})
	if err != nil {
		t.Fatalf("Inspect() error = %v", err)
	}
	if inspection.NavigationSource != NavigationEPUB3Nav {
		t.Fatalf("navigation source = %q, want %q", inspection.NavigationSource, NavigationEPUB3Nav)
	}
	if inspection.Metadata.Title != "Test Book" || inspection.Metadata.Language != "en" {
		t.Fatalf("metadata = %#v", inspection.Metadata)
	}
	if len(inspection.Structure) != 1 || len(inspection.Structure[0].Children) != 2 {
		t.Fatalf("unexpected hierarchy: %#v", inspection.Structure)
	}
	parent := inspection.Structure[0]
	if parent.Selected {
		t.Fatal("navigation parent must remain hierarchy, not a default chapter")
	}
	first := parent.Children[0]
	second := parent.Children[1]
	if !first.Selected || !second.Selected {
		t.Fatal("leaf navigation nodes must be selected")
	}
	if first.ContentRanges[0].StartAnchor != "one" || first.ContentRanges[0].EndAnchor != "two" {
		t.Fatalf("first range = %#v", first.ContentRanges)
	}

	fragment, diagnostics, err := ExtractChapter(data, *first, Limits{})
	if err != nil {
		t.Fatalf("ExtractChapter() error = %v; diagnostics = %#v", err, diagnostics)
	}
	if !strings.Contains(fragment, "first text") || !strings.Contains(fragment, "Not a chapter boundary") {
		t.Fatalf("fragment lost selected chapter content: %q", fragment)
	}
	if strings.Contains(fragment, "second text") {
		t.Fatalf("fragment duplicated adjacent chapter content: %q", fragment)
	}
}

func TestExtractChapterHandlesXHTMLSelfClosingTitle(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf": `<package version="2.0"><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine toc="ncx"><itemref idref="chapter"/></spine></package>`,
		"OPS/toc.ncx":  `<ncx><navMap><navPoint><navLabel><text>Chapter</text></navLabel><content src="chapter.xhtml#chapter"/></navPoint></navMap></ncx>`,
		"OPS/chapter.xhtml": `<html xmlns="http://www.w3.org/1999/xhtml"><head><title/></head><body><span id="chapter"><div><p>chapter text</p></div></span></body></html>`,
	})
	inspection, err := Inspect(data, Limits{})
	if err != nil {
		t.Fatal(err)
	}
	fragment, _, err := ExtractChapter(data, *inspection.Structure[0], Limits{})
	if err != nil {
		t.Fatalf("ExtractChapter() error = %v", err)
	}
	if !strings.Contains(fragment, "chapter text") {
		t.Fatalf("fragment = %q, want chapter text", fragment)
	}
}

func TestInspectUsesNCXThenSpineFallback(t *testing.T) {
	baseFiles := map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/one.xhtml":          `<html><head><title>One title</title></head><body><p>One</p></body></html>`,
		"OPS/two.xhtml":          `<html><body><h1>Two heading</h1><p>Two</p></body></html>`,
	}
	t.Run("NCX", func(t *testing.T) {
		files := cloneFiles(baseFiles)
		files["OPS/book.opf"] = `<package version="2.0"><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine toc="ncx"><itemref idref="one"/><itemref idref="two"/></spine></package>`
		files["OPS/toc.ncx"] = `<ncx><navMap><navPoint><navLabel><text>First</text></navLabel><content src="one.xhtml"/></navPoint><navPoint><navLabel><text>Second</text></navLabel><content src="two.xhtml"/></navPoint></navMap></ncx>`
		inspection, err := Inspect(buildTestEPUB(t, files), Limits{})
		if err != nil {
			t.Fatal(err)
		}
		if inspection.NavigationSource != NavigationEPUB2NCX || inspection.Structure[0].Title != "First" {
			t.Fatalf("inspection = %#v", inspection)
		}
	})
	t.Run("spine", func(t *testing.T) {
		files := cloneFiles(baseFiles)
		files["OPS/book.opf"] = `<package version="2.0"><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two" linear="no"/></spine></package>`
		inspection, err := Inspect(buildTestEPUB(t, files), Limits{})
		if err != nil {
			t.Fatal(err)
		}
		if inspection.NavigationSource != NavigationSpine || inspection.Structure[0].Title != "One title" {
			t.Fatalf("inspection = %#v", inspection)
		}
		if inspection.Structure[1].Selected || inspection.Structure[1].Linear {
			t.Fatalf("non-linear spine item must be preserved but not selected: %#v", inspection.Structure[1])
		}
	})
}

func TestInspectRejectsUnsafeAndEncryptedArchives(t *testing.T) {
	t.Run("path traversal", func(t *testing.T) {
		_, err := Inspect(buildTestEPUB(t, map[string]string{"../escape.xhtml": "unsafe"}), Limits{})
		assertCode(t, err, CodeInvalidArchivePath)
	})
	t.Run("encryption", func(t *testing.T) {
		_, err := Inspect(buildTestEPUB(t, map[string]string{
			"mimetype":                epubMIME,
			"META-INF/container.xml":  `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
			"META-INF/encryption.xml": `<encryption/>`,
			"book.opf":                `<package><manifest/></package>`,
		}), Limits{})
		assertCode(t, err, CodeDRMUnsupported)
	})
	t.Run("entry limit", func(t *testing.T) {
		_, err := Inspect(buildTestEPUB(t, map[string]string{"mimetype": epubMIME, "META-INF/container.xml": "x"}), Limits{MaxZipEntries: 1})
		assertCode(t, err, CodeArchiveLimit)
	})
}

func TestLimitsFromEnvKeepsDefaultsForInvalidValues(t *testing.T) {
	values := map[string]string{
		"EPUB_IMPORT_MAX_ZIP_ENTRIES":       "7",
		"EPUB_IMPORT_MAX_COMPRESSION_RATIO": "25.5",
		"EPUB_IMPORT_MAX_CHAPTER_HTML_SIZE": "invalid",
		"EPUB_IMPORT_MAX_UNCOMPRESSED_SIZE": "-1",
	}
	limits := LimitsFromEnv(func(key string) string { return values[key] })
	if limits.MaxZipEntries != 7 || limits.MaxCompressionRatio != 25.5 {
		t.Fatalf("limits = %#v", limits)
	}
	if limits.MaxChapterHTMLSize != DefaultLimits().MaxChapterHTMLSize {
		t.Fatalf("invalid value disabled chapter size limit: %#v", limits)
	}
	if limits.MaxUncompressedSize != DefaultLimits().MaxUncompressedSize {
		t.Fatalf("negative value changed uncompressed limit: %#v", limits)
	}
}

func assertCode(t *testing.T, err error, want ErrorCode) {
	t.Helper()
	if err == nil {
		t.Fatalf("error = nil, want %q", want)
	}
	got, ok := err.(*Error)
	if !ok || got.Code != want {
		t.Fatalf("error = %#v, want code %q", err, want)
	}
}

func cloneFiles(source map[string]string) map[string]string {
	result := make(map[string]string, len(source))
	for name, body := range source {
		result[name] = body
	}
	return result
}

func buildTestEPUB(t *testing.T, files map[string]string) []byte {
	t.Helper()
	var output bytes.Buffer
	writer := zip.NewWriter(&output)
	for name, body := range files {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatalf("create ZIP entry %q: %v", name, err)
		}
		if _, err := entry.Write([]byte(body)); err != nil {
			t.Fatalf("write ZIP entry %q: %v", name, err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatalf("close ZIP: %v", err)
	}
	return output.Bytes()
}
