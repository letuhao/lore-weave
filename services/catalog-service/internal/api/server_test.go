package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/loreweave/catalog-service/internal/config"
)

func TestFetchPublicIDs(t *testing.T) {
	t.Parallel()
	var gotQuery string
	id := uuid.New()
	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_ids": []string{id.String()},
			"total":    1,
		})
	}))
	defer sharing.Close()

	srv := &Server{cfg: &config.Config{SharingServiceInternalURL: sharing.URL}}
	out, status := srv.fetchPublicIDs(10, 5, "hello world")
	if status != http.StatusOK || out == nil {
		t.Fatalf("expected status 200 with payload, got status=%d", status)
	}
	if len(out.BookIDs) != 1 || out.BookIDs[0] != id {
		t.Fatalf("unexpected book ids: %+v", out.BookIDs)
	}
	if !strings.Contains(gotQuery, "q=hello+world") {
		t.Fatalf("expected encoded q in query, got %q", gotQuery)
	}
}

func TestListPublicBooksFiltersInactive(t *testing.T) {
	t.Parallel()
	activeID := uuid.New()
	trashedID := uuid.New()

	sharing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_ids": []string{activeID.String(), trashedID.String()},
			"total":    2,
		})
	}))
	defer sharing.Close()

	book := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimPrefix(r.URL.Path, "/internal/books/")
		id = strings.TrimSuffix(id, "/projection")
		state := "active"
		title := "Active Book"
		if id == trashedID.String() {
			state = "trashed"
			title = "Trashed Book"
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"book_id":           id,
			"title":             title,
			"lifecycle_state":   state,
			"chapter_count":     1,
			"original_language": "en",
			"created_at":        time.Now().UTC(),
		})
	}))
	defer book.Close()

	srv := &Server{
		cfg: &config.Config{
			SharingServiceInternalURL: sharing.URL,
			BookServiceInternalURL:    book.URL,
		},
	}
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/catalog/books", nil)
	srv.listPublicBooks(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rr.Code)
	}
	var body struct {
		Items []map[string]any `json:"items"`
		Total int              `json:"total"`
	}
	if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(body.Items) != 1 {
		t.Fatalf("expected only active projection, got %d items", len(body.Items))
	}
}

func TestGetPublicBookInvalidUUID(t *testing.T) {
	t.Parallel()
	srv := &Server{cfg: &config.Config{}}
	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/catalog/books/bad-id", nil)
	rctx := chi.NewRouteContext()
	rctx.URLParams.Add("book_id", "bad-id")
	req = req.WithContext(context.WithValue(req.Context(), chi.RouteCtxKey, rctx))
	srv.getPublicBook(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rr.Code)
	}
}
