package epubimport

import (
	"strings"
	"testing"
)

func TestSanitizeHTMLRetainsSemanticContentAndRemovesExecutableMarkup(t *testing.T) {
	result, diagnostics, err := SanitizeHTML(`<p onclick="steal()"><strong>Safe</strong> <a href="#note">note</a></p><script>alert(1)</script><img src="../images/cover.png" onerror="boom()"><iframe src="https://evil.example"></iframe>`)
	if err != nil {
		t.Fatalf("SanitizeHTML() error = %v", err)
	}
	for _, forbidden := range []string{"script", "onclick", "onerror", "iframe"} {
		if strings.Contains(strings.ToLower(result), forbidden) {
			t.Fatalf("sanitized output contains %q: %q", forbidden, result)
		}
	}
	if !strings.Contains(result, "<strong>Safe</strong>") || !strings.Contains(result, `href="#note"`) || !strings.Contains(result, `src="../images/cover.png"`) {
		t.Fatalf("sanitized output lost safe semantic content: %q", result)
	}
	if len(diagnostics) < 3 {
		t.Fatalf("diagnostics = %#v, want removals", diagnostics)
	}
}

func TestSanitizeHTMLRejectsExternalAndScriptURLs(t *testing.T) {
	result, _, err := SanitizeHTML(`<a href="javascript:alert(1)">bad</a><img src="https://tracker.example/pixel.png"><img src="data:image/png;base64,AAAA">`)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(result, "javascript:") || strings.Contains(result, "tracker.example") {
		t.Fatalf("unsafe URL remains: %q", result)
	}
	if !strings.Contains(result, "data:image/png") {
		t.Fatalf("safe data image removed: %q", result)
	}
}

func TestSanitizeHTMLRetainsBookOwnedMediaURL(t *testing.T) {
	result, _, err := SanitizeHTML(`<img src="/media/loreweave-dev-books/imports/assets/sha/image.png">`)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(result, `src="/media/loreweave-dev-books/imports/assets/sha/image.png"`) {
		t.Fatalf("Book-owned media URL was removed: %q", result)
	}
}
