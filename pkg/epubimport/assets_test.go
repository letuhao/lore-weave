package epubimport

import (
	"fmt"
	"strings"
	"testing"
)

func TestResolveAndRewriteAssetsStoresValidatedLocalImagesOnce(t *testing.T) {
	png := append([]byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}, []byte("fixture")...)
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>`,
		"OPS/book.opf": `<package version="3.0"><manifest>
<item id="chapter" href="text/chapter.xhtml" media-type="application/xhtml+xml"/>
<item id="image" href="images/cover.png" media-type="image/png"/>
</manifest><spine><itemref idref="chapter"/></spine></package>`,
		"OPS/text/chapter.xhtml": `<html><body><p>chapter</p></body></html>`,
		"OPS/images/cover.png":   string(png),
	})
	var stored []ResolvedAsset
	result, diagnostics, err := ResolveAndRewriteAssets(data, "OPS/text/chapter.xhtml", `<img src="../images/cover.png" srcset="../images/cover.png 1x"><object type="image/png" data="../images/cover.png"></object>`, Limits{}, func(asset ResolvedAsset) (string, error) {
		stored = append(stored, asset)
		return fmt.Sprintf("/media/books/%s", asset.SHA256), nil
	})
	if err != nil {
		t.Fatalf("ResolveAndRewriteAssets() error = %v", err)
	}
	if len(diagnostics) != 0 {
		t.Fatalf("diagnostics = %#v, want none", diagnostics)
	}
	if len(stored) != 1 {
		t.Fatalf("stored = %#v, want a single deduplicated image", stored)
	}
	if stored[0].SourcePath != "OPS/images/cover.png" || stored[0].MediaType != "image/png" || stored[0].SHA256 == "" {
		t.Fatalf("stored asset = %#v", stored[0])
	}
	if strings.Count(result, "/media/books/"+stored[0].SHA256) != 3 || strings.Contains(result, "<object") {
		t.Fatalf("rewritten HTML = %q", result)
	}
}

func TestResolveAndRewriteAssetsDropsExternalMissingAndInvalidImages(t *testing.T) {
	data := buildTestEPUB(t, map[string]string{
		"mimetype":                epubMIME,
		"META-INF/container.xml":  `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
		"book.opf":                `<package><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"chapter.xhtml":           `<html><body><p>chapter</p></body></html>`,
		"images/not-an-image.png": "not an image",
	})
	called := false
	result, diagnostics, err := ResolveAndRewriteAssets(data, "chapter.xhtml", `<img src="https://tracker.example/pixel.png"><img src="missing.png"><img src="images/not-an-image.png">`, Limits{}, func(asset ResolvedAsset) (string, error) {
		called = true
		return "/media/should-not-exist", nil
	})
	if err != nil {
		t.Fatalf("ResolveAndRewriteAssets() error = %v", err)
	}
	if called {
		t.Fatal("resolver was called for an unsafe or invalid image")
	}
	if strings.Contains(result, "tracker.example") || strings.Contains(result, "missing.png") || strings.Contains(result, "not-an-image") {
		t.Fatalf("unsafe image reference remains: %q", result)
	}
	if len(diagnostics) != 3 {
		t.Fatalf("diagnostics = %#v, want three typed warnings", diagnostics)
	}
}

func TestResolveAndRewriteAssetsDecodesDataURI(t *testing.T) {
	pngData := "iVBORw0KGgo="
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
		"book.opf":               `<package><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"chapter.xhtml":          `<html><body><p>chapter</p></body></html>`,
	})
	var stored ResolvedAsset
	result, _, err := ResolveAndRewriteAssets(data, "chapter.xhtml", `<img src="data:image/png;base64,`+pngData+`">`, Limits{}, func(asset ResolvedAsset) (string, error) {
		stored = asset
		return "/media/data-image", nil
	})
	if err != nil {
		t.Fatalf("ResolveAndRewriteAssets() error = %v", err)
	}
	if stored.SourcePath == "" || !strings.HasPrefix(stored.SourcePath, "data:") || stored.MediaType != "image/png" {
		t.Fatalf("stored data URI asset = %#v", stored)
	}
	if !strings.Contains(result, `src="/media/data-image"`) {
		t.Fatalf("data URI was not rewritten: %q", result)
	}
}

func TestExtractCoverValidatesCandidateBytes(t *testing.T) {
	png := []byte{0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'}
	data := buildTestEPUB(t, map[string]string{
		"mimetype":               epubMIME,
		"META-INF/container.xml": `<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>`,
		"book.opf":               `<package><manifest><item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>`,
		"chapter.xhtml":          `<html><body><p>fixture</p></body></html>`,
		"cover.png":              string(png),
	})
	cover, err := ExtractCover(data, CoverCandidate{SourcePath: "cover.png", MediaType: "image/png"}, Limits{})
	if err != nil {
		t.Fatal(err)
	}
	if cover.MediaType != "image/png" || cover.SHA256 == "" || string(cover.Data) != string(png) {
		t.Fatalf("cover = %#v", cover)
	}
}
