package epubimport

import "testing"

func TestCollectInternalLinksNormalizesArchiveTargets(t *testing.T) {
	links, diagnostics := CollectInternalLinks("OEBPS/text/chapter-01.xhtml", `<p><a href="#note-1">note</a><a href="chapter-02.xhtml#start">next</a><a href="../notes/endnotes.xhtml#n2">endnote</a><a href="https://example.test">external</a></p>`)
	if len(diagnostics) != 0 {
		t.Fatalf("diagnostics = %#v", diagnostics)
	}
	if len(links) != 3 {
		t.Fatalf("links = %#v", links)
	}
	want := []InternalLink{
		{OriginalHref: "#note-1", TargetHref: "OEBPS/text/chapter-01.xhtml", TargetFragment: "note-1"},
		{OriginalHref: "chapter-02.xhtml#start", TargetHref: "OEBPS/text/chapter-02.xhtml", TargetFragment: "start"},
		{OriginalHref: "../notes/endnotes.xhtml#n2", TargetHref: "OEBPS/notes/endnotes.xhtml", TargetFragment: "n2"},
	}
	for index := range want {
		if links[index] != want[index] {
			t.Fatalf("link[%d] = %#v, want %#v", index, links[index], want[index])
		}
	}
}

func TestCollectInternalLinksRejectsUnsafeTargets(t *testing.T) {
	links, _ := CollectInternalLinks("OEBPS/text/chapter.xhtml", `<a href="../chapter.xhtml">ok</a><a href="../../../../escape.xhtml">bad</a><a href="javascript:alert(1)">bad</a><a href="//example.test/x">bad</a>`)
	if len(links) != 1 {
		t.Fatalf("links = %#v", links)
	}
	if links[0].TargetHref != "OEBPS/chapter.xhtml" {
		t.Fatalf("target = %q", links[0].TargetHref)
	}
}
