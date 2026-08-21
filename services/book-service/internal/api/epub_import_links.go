package api

import (
	"encoding/json"
	"fmt"
	"net/url"

	"github.com/google/uuid"

	"github.com/loreweave/epubimport"
)

type epubStagingLink struct {
	OriginalHref   string `json:"original_href"`
	TargetHref     string `json:"target_href"`
	TargetFragment string `json:"target_fragment,omitempty"`
}

type epubChapterLinkTarget struct {
	ChapterID      uuid.UUID
	SourceHref     string
	SourceFragment string
}

// rewriteEPUBInternalLinks rewrites only TipTap link marks identified by the
// worker's normalized EPUB link intents. It never rewrites arbitrary strings,
// preserving external URLs and preventing accidental changes to prose.
func rewriteEPUBInternalLinks(raw json.RawMessage, bookID uuid.UUID, current epubChapterLinkTarget, links []epubStagingLink, targets []epubChapterLinkTarget) (json.RawMessage, []epubimport.Diagnostic, error) {
	if len(links) == 0 {
		return raw, nil, nil
	}
	exact := make(map[string]uuid.UUID, len(targets))
	byHref := make(map[string]uuid.UUID, len(targets))
	for _, target := range targets {
		if target.SourceHref == "" || target.ChapterID == uuid.Nil {
			continue
		}
		if _, exists := byHref[target.SourceHref]; !exists {
			byHref[target.SourceHref] = target.ChapterID
		}
		if target.SourceFragment != "" {
			exact[target.SourceHref+"#"+target.SourceFragment] = target.ChapterID
		}
	}
	replacements := make(map[string]string, len(links))
	warnings := make([]epubimport.Diagnostic, 0)
	for _, link := range links {
		if link.OriginalHref == "" || link.TargetHref == "" {
			continue
		}
		targetID, ok := exact[link.TargetHref+"#"+link.TargetFragment]
		if !ok && link.TargetHref == current.SourceHref {
			targetID, ok = current.ChapterID, current.ChapterID != uuid.Nil
		}
		if !ok {
			targetID, ok = byHref[link.TargetHref]
		}
		if !ok {
			warnings = append(warnings, epubimport.Diagnostic{Code: epubimport.CodeContentUnavailable, Message: "internal EPUB link target was not imported"})
			continue
		}
		replacement := fmt.Sprintf("/books/%s/chapters/%s/read", bookID, targetID)
		if link.TargetFragment != "" {
			replacement += "#" + url.PathEscape(link.TargetFragment)
		}
		replacements[link.OriginalHref] = replacement
	}
	if len(replacements) == 0 {
		return raw, warnings, nil
	}
	var document any
	if err := json.Unmarshal(raw, &document); err != nil {
		return nil, warnings, err
	}
	rewriteEPUBLinkMarks(document, replacements)
	rewritten, err := json.Marshal(document)
	if err != nil {
		return nil, warnings, err
	}
	return rewritten, warnings, nil
}

func rewriteEPUBLinkMarks(node any, replacements map[string]string) {
	switch value := node.(type) {
	case []any:
		for _, child := range value {
			rewriteEPUBLinkMarks(child, replacements)
		}
	case map[string]any:
		if marks, ok := value["marks"].([]any); ok {
			for _, markValue := range marks {
				mark, ok := markValue.(map[string]any)
				if !ok || mark["type"] != "link" {
					continue
				}
				attrs, ok := mark["attrs"].(map[string]any)
				if !ok {
					continue
				}
				href, ok := attrs["href"].(string)
				if ok {
					if replacement, exists := replacements[href]; exists {
						attrs["href"] = replacement
					}
				}
			}
		}
		for _, child := range value {
			rewriteEPUBLinkMarks(child, replacements)
		}
	}
}
