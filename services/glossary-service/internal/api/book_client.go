package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
)

// bookHTTPClient is shared across requests; 5 s timeout prevents goroutine leaks
// when book-service is slow or unreachable.
var bookHTTPClient = &http.Client{Timeout: 5 * time.Second}

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
	return &p, http.StatusOK
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
