package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/observability"
)

// bookHTTPClient is shared across requests; 5 s timeout prevents goroutine leaks
// when book-service is slow or unreachable.
// Phase 6c — traced transport so outbound calls carry a W3C traceparent + emit a CLIENT span.
var bookHTTPClient = &http.Client{Timeout: 5 * time.Second, Transport: observability.HTTPTransport(nil)}

type wikiSettingsProjection struct {
	Visibility     string `json:"visibility"`
	CommunityMode  string `json:"community_mode"`
	AIAssist       bool   `json:"ai_assist"`
	GlossaryExpose string `json:"glossary_exposure"`
	AutoGenerate   bool   `json:"auto_generate"`
}

type bookProjection struct {
	BookID       uuid.UUID               `json:"book_id"`
	OwnerUserID  uuid.UUID               `json:"owner_user_id"`
	// PP-2 (WS-1.2 / spec 08 R5) — "the diary taint" the book projection emits so consumers can guard
	// on it. Every wiki/enrichment/community reader resolves the book through fetchBookProjection, so
	// nulling WikiSettings here (below) is the SINGLE chokepoint that keeps a diary's colleagues off the
	// public wiki — closing checkWikiPublic, listUserWikiContributions, and submitWikiSuggestion at once,
	// INCLUDING any residual `visibility=public` blob written before book-service's EGRESS GUARD #3 landed.
	Kind         string                  `json:"kind"`
	WikiSettings *wikiSettingsProjection  `json:"wiki_settings"`
}

type chapterSummary struct {
	ChapterID uuid.UUID `json:"chapter_id"`
	Title     *string   `json:"title"`
	SortOrder int       `json:"sort_order"`
}

// fetchBookProjection calls the book-service internal projection endpoint.
// Returns (nil, 503) if unreachable; (nil, 404) if the book does not exist.
func (s *Server) fetchBookProjection(ctx context.Context, bookID uuid.UUID) (*bookProjection, int) {
	url := fmt.Sprintf("%s/internal/books/%s/projection",
		strings.TrimRight(s.cfg.BookServiceURL, "/"), bookID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, http.StatusInternalServerError
	}
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	// K7e: forward the caller's trace id so book-service can stitch
	// its logs to the chat → knowledge → glossary → book chain.
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := bookHTTPClient.Do(req)
	if err != nil {
		return nil, http.StatusServiceUnavailable
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var p bookProjection
	if err := json.NewDecoder(res.Body).Decode(&p); err != nil {
		return nil, http.StatusServiceUnavailable
	}
	// PP-2 — neutralize the diary taint at the one place every wiki/enrichment/community reader passes
	// through. A diary has NO wiki (spec 08 R5); treat the JSONB blob as untrusted (assume drift) and
	// strip it fail-closed, so no downstream reader can serve a diary colleague's page even if a stale
	// `visibility=public` row exists. Defense-in-depth behind book-service's EGRESS GUARD #3 (which
	// blocks NEW mutations but not rows written before it).
	if p.Kind == "diary" {
		p.WikiSettings = nil
	}
	return &p, http.StatusOK
}

// refuseDiaryWikiSurface (PP-3, spec 08 R5) — a shared guard for the auto-WRITE wiki/enrichment
// surfaces (generateWikiStubs, internalUpsertEnrichments) that manufacture AI prose about an entity
// regardless of visibility. Resolves the book's kind via the projection; if it's a diary, writes a
// 403 and returns true (the caller returns). Fails CLOSED: if the projection is unreachable we refuse
// (a wiki/enrichment write is not worth the risk of publishing a diary colleague on a transient miss).
func (s *Server) refuseDiaryWikiSurface(w http.ResponseWriter, r *http.Request, bookID uuid.UUID) bool {
	proj, status := s.fetchBookProjection(r.Context(), bookID)
	if status != http.StatusOK || proj == nil {
		writeError(w, http.StatusServiceUnavailable, "GLOSS_BOOK_UNAVAILABLE",
			"cannot resolve the book to authorize this wiki operation")
		return true
	}
	if proj.Kind == "diary" {
		writeError(w, http.StatusForbidden, "GLOSS_DIARY_NO_WIKI",
			"a diary has no wiki — it is private and cannot be published or enriched")
		return true
	}
	return false
}

// fetchBookChapters calls the book-service internal chapters endpoint.
// Returns (nil, 503) if unreachable; (nil, 404) if the book does not exist.
func (s *Server) fetchBookChapters(ctx context.Context, bookID uuid.UUID) ([]chapterSummary, int) {
	url := fmt.Sprintf("%s/internal/books/%s/chapters",
		strings.TrimRight(s.cfg.BookServiceURL, "/"), bookID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, http.StatusInternalServerError
	}
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	// K7e: forward the caller's trace id so book-service can stitch
	// its logs to the chat → knowledge → glossary → book chain.
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := bookHTTPClient.Do(req)
	if err != nil {
		return nil, http.StatusServiceUnavailable
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var cr struct {
		Items []chapterSummary `json:"items"`
	}
	if err := json.NewDecoder(res.Body).Decode(&cr); err != nil {
		return nil, http.StatusServiceUnavailable
	}
	return cr.Items, http.StatusOK
}
