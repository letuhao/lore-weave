package api

import (
	"context"
	"encoding/json"
	"net/http"
	"sort"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/loreweave/epubimport"
)

type epubShadowComparison struct {
	LegacyChapterCount int      `json:"legacy_chapter_count"`
	V2ChapterCount     int      `json:"v2_chapter_count"`
	Delta              int      `json:"delta"`
	LegacyProjection   string   `json:"legacy_projection"`
	Differences        []string `json:"differences"`
}

func buildEPUBShadowComparison(inspection epubimport.Inspection) epubShadowComparison {
	// The retired importer treated each linear content document as a chapter
	// candidate before the combined-HTML parser guessed heading boundaries. This
	// deterministic document-order projection is the comparison baseline; V2's
	// navigation leaves remain authoritative and are never changed by shadow.
	hrefs := make(map[string]struct{})
	v2 := 0
	var visit func([]*epubimport.NavigationNode)
	visit = func(nodes []*epubimport.NavigationNode) {
		for _, node := range nodes {
			if node.SourceHref != "" && node.Linear {
				hrefs[node.SourceHref] = struct{}{}
			}
			if len(node.Children) == 0 && node.Selected {
				v2++
			}
			visit(node.Children)
		}
	}
	visit(inspection.Structure)
	differences := make([]string, 0, 2)
	if len(hrefs) != v2 {
		differences = append(differences, "logical_navigation_count_differs_from_document_projection")
	}
	if inspection.NavigationSource == epubimport.NavigationSpine {
		differences = append(differences, "navigation_fallback_used")
	}
	sort.Strings(differences)
	return epubShadowComparison{
		LegacyChapterCount: len(hrefs), V2ChapterCount: v2, Delta: v2 - len(hrefs),
		LegacyProjection: "linear_content_document_order", Differences: differences,
	}
}

func (s *Server) persistEPUBShadowComparison(ctx context.Context, sourceID uuid.UUID, inspection epubimport.Inspection) error {
	comparison := buildEPUBShadowComparison(inspection)
	raw, err := json.Marshal(comparison)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx, `
INSERT INTO epub_import_shadow_comparisons(source_id,legacy_chapter_count,v2_chapter_count,delta,comparison_json)
VALUES($1,$2,$3,$4,$5)
ON CONFLICT(source_id) DO UPDATE SET legacy_chapter_count=EXCLUDED.legacy_chapter_count,
  v2_chapter_count=EXCLUDED.v2_chapter_count,delta=EXCLUDED.delta,
  comparison_json=EXCLUDED.comparison_json,updated_at=now()
`, sourceID, comparison.LegacyChapterCount, comparison.V2ChapterCount, comparison.Delta, raw)
	return err
}

func (s *Server) getEPUBShadowComparison(w http.ResponseWriter, r *http.Request) {
	sourceID, err := uuid.Parse(chi.URLParam(r, "source_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INVALID_ID", "invalid source_id")
		return
	}
	caller, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	var raw []byte
	var owner uuid.UUID
	if err := s.pool.QueryRow(r.Context(), `
SELECT c.comparison_json,s.owner_user_id
FROM epub_import_shadow_comparisons c JOIN import_sources s ON s.id=c.source_id
WHERE c.source_id=$1
`, sourceID).Scan(&raw, &owner); err != nil {
		writeError(w, http.StatusNotFound, "SHADOW_COMPARISON_NOT_FOUND", "shadow comparison not found")
		return
	}
	if owner != caller {
		writeError(w, http.StatusNotFound, "SHADOW_COMPARISON_NOT_FOUND", "shadow comparison not found")
		return
	}
	var comparison any
	if err := json.Unmarshal(raw, &comparison); err != nil {
		writeError(w, http.StatusInternalServerError, "IMPORT_ERROR", "invalid shadow comparison")
		return
	}
	writeJSON(w, http.StatusOK, comparison)
}
