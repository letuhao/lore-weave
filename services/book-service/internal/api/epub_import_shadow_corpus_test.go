package api

import (
	"archive/zip"
	"bytes"
	"testing"

	"github.com/loreweave/epubimport"
)

// TestEPUBShadowCorpusComparison exercises the same inspection path used by the
// shadow endpoint against representative EPUB 3, EPUB 2, and spine-only shapes.
// It deliberately keeps the expected legacy projection explicit: one chapter
// per linear content document, while V2 counts selected navigation leaves.
func TestEPUBShadowCorpusComparison(t *testing.T) {
	tests := []struct {
		name       string
		files      map[string]string
		legacy     int
		v2         int
		navigation epubimport.NavigationSource
		fallback   bool
	}{
		{
			name: "epub3 nested navigation",
			files: map[string]string{
				"OPS/book.opf":   `<package version="3.0"><metadata><title>Nested</title></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="body" href="body.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="body"/></spine></package>`,
				"OPS/nav.xhtml":  `<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="body.xhtml#part">Part</a><ol><li><a href="body.xhtml#one">One</a></li><li><a href="body.xhtml#two">Two</a></li></ol></li></ol></nav></body></html>`,
				"OPS/body.xhtml": `<html><body><div id="part"><h1>Part</h1></div><div id="one"><h2>One</h2><p>one</p></div><div id="two"><h2>Two</h2><p>two</p></div></body></html>`,
			},
			legacy: 1, v2: 2, navigation: epubimport.NavigationEPUB3Nav,
		},
		{
			name: "epub2 ncx",
			files: map[string]string{
				"OPS/book.opf":  `<package version="2.0"><metadata><title>NCX</title></metadata><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine toc="ncx"><itemref idref="one"/><itemref idref="two"/></spine></package>`,
				"OPS/toc.ncx":   `<ncx><navMap><navPoint><navLabel><text>One</text></navLabel><content src="one.xhtml"/></navPoint><navPoint><navLabel><text>Two</text></navLabel><content src="two.xhtml"/></navPoint></navMap></ncx>`,
				"OPS/one.xhtml": `<html><body><h1>One</h1><p>one</p></body></html>`,
				"OPS/two.xhtml": `<html><body><h1>Two</h1><p>two</p></body></html>`,
			},
			legacy: 2, v2: 2, navigation: epubimport.NavigationEPUB2NCX,
		},
		{
			name: "spine fallback",
			files: map[string]string{
				"OPS/book.opf":  `<package version="2.0"><metadata><title>Spine</title></metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two" linear="no"/></spine></package>`,
				"OPS/one.xhtml": `<html><head><title>One</title></head><body><p>one</p></body></html>`,
				"OPS/two.xhtml": `<html><body><p>two</p></body></html>`,
			},
			legacy: 1, v2: 1, navigation: epubimport.NavigationSpine, fallback: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			inspection, err := epubimport.Inspect(buildShadowCorpusEPUB(t, tc.files), epubimport.Limits{})
			if err != nil {
				t.Fatalf("Inspect() error = %v", err)
			}
			if inspection.NavigationSource != tc.navigation {
				t.Fatalf("navigation source = %q, want %q", inspection.NavigationSource, tc.navigation)
			}
			comparison := buildEPUBShadowComparison(*inspection)
			if comparison.LegacyChapterCount != tc.legacy || comparison.V2ChapterCount != tc.v2 || comparison.Delta != tc.v2-tc.legacy {
				t.Fatalf("comparison = %+v, want legacy=%d v2=%d", comparison, tc.legacy, tc.v2)
			}
			if tc.fallback != containsShadowDifference(comparison.Differences, "navigation_fallback_used") {
				t.Fatalf("fallback difference = %#v, fallback=%v", comparison.Differences, tc.fallback)
			}
		})
	}
}

func containsShadowDifference(differences []string, want string) bool {
	for _, difference := range differences {
		if difference == want {
			return true
		}
	}
	return false
}

func buildShadowCorpusEPUB(t *testing.T, files map[string]string) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	entries := map[string]string{
		"mimetype":               "application/epub+zip",
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
	}
	for name, content := range files {
		entries[name] = content
	}
	for name, content := range entries {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write([]byte(content)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}
