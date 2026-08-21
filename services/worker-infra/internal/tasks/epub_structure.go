package tasks

import (
	"fmt"

	"github.com/loreweave/epubimport"
)

type epubChapter struct {
	Title     string
	Path      string
	HTML      string
	SourceKey string
}

// extractEPUBChapters is the legacy importer adapter. The shared inspector is
// now the only EPUB boundary authority: it selects EPUB3 nav, then NCX, then
// spine fallback and extracts DOM-valid chapter fragments. The V2 worker uses
// the inspection nodes directly; this adapter keeps non-V2 call sites stable
// while rollout mode still permits the legacy processor.
func extractEPUBChapters(data []byte) ([]epubChapter, error) {
	inspection, err := epubimport.Inspect(data, epubimport.DefaultLimits())
	if err != nil {
		return nil, fmt.Errorf("inspect EPUB: %w", err)
	}
	nodes := epubimport.SelectedNodes(inspection.Structure)
	chapters := make([]epubChapter, 0, len(nodes))
	for _, node := range nodes {
		html, _, err := epubimport.ExtractChapter(data, *node, epubimport.DefaultLimits())
		if err != nil {
			return nil, fmt.Errorf("extract EPUB chapter %q: %w", node.SourceKey, err)
		}
		chapters = append(chapters, epubChapter{
			Title:     node.Title,
			Path:      node.SourceHref,
			HTML:      html,
			SourceKey: node.SourceKey,
		})
	}
	if len(chapters) == 0 {
		return nil, fmt.Errorf("EPUB has no selected logical chapters")
	}
	return chapters, nil
}
