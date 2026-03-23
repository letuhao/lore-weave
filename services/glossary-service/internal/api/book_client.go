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

type bookProjection struct {
	BookID      uuid.UUID `json:"book_id"`
	OwnerUserID uuid.UUID `json:"owner_user_id"`
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
