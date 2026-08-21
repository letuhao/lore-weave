package api

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestRewriteEPUBInternalLinksOnlyChangesMatchedTipTapLinks(t *testing.T) {
	bookID := uuid.MustParse("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
	currentID := uuid.MustParse("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
	targetID := uuid.MustParse("cccccccc-cccc-cccc-cccc-cccccccccccc")
	raw := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"note","marks":[{"type":"link","attrs":{"href":"#note"}}]},{"type":"text","text":" external","marks":[{"type":"link","attrs":{"href":"https://example.test"}}]}]}]}`)
	rewritten, warnings, err := rewriteEPUBInternalLinks(raw, bookID,
		epubChapterLinkTarget{ChapterID: currentID, SourceHref: "OEBPS/chapter.xhtml", SourceFragment: "start"},
		[]epubStagingLink{{OriginalHref: "#note", TargetHref: "OEBPS/chapter.xhtml", TargetFragment: "note"}},
		[]epubChapterLinkTarget{{ChapterID: currentID, SourceHref: "OEBPS/chapter.xhtml", SourceFragment: "start"}, {ChapterID: targetID, SourceHref: "OEBPS/chapter-2.xhtml", SourceFragment: "start"}},
	)
	if err != nil || len(warnings) != 0 {
		t.Fatalf("rewrite error=%v warnings=%#v", err, warnings)
	}
	if !strings.Contains(string(rewritten), "/books/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/chapters/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/read#note") {
		t.Fatalf("rewritten = %s", rewritten)
	}
	if !strings.Contains(string(rewritten), "https://example.test") {
		t.Fatalf("external link changed: %s", rewritten)
	}
}

func TestRewriteEPUBInternalLinksWarnsForExcludedTarget(t *testing.T) {
	raw := json.RawMessage(`{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"missing","marks":[{"type":"link","attrs":{"href":"chapter-2.xhtml#start"}}]}]}]}`)
	rewritten, warnings, err := rewriteEPUBInternalLinks(raw, uuid.New(), epubChapterLinkTarget{ChapterID: uuid.New(), SourceHref: "chapter-1.xhtml"}, []epubStagingLink{{OriginalHref: "chapter-2.xhtml#start", TargetHref: "chapter-2.xhtml", TargetFragment: "start"}}, nil)
	if err != nil || len(warnings) != 1 {
		t.Fatalf("rewrite error=%v warnings=%#v", err, warnings)
	}
	if string(rewritten) != string(raw) {
		t.Fatalf("unresolved link must remain unchanged: %s", rewritten)
	}
}
