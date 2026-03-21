package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/catalog-service/internal/config"
)

type Server struct {
	pool *pgxpool.Pool
	cfg  *config.Config
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	return &Server{pool: pool, cfg: cfg}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)
	r.Get("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	r.Route("/v1/catalog", func(r chi.Router) {
		r.Get("/books", s.listPublicBooks)
		r.Get("/books/{book_id}", s.getPublicBook)
	})
	return r
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}

type sharingPublicList struct {
	BookIDs []uuid.UUID `json:"book_ids"`
	Total   int         `json:"total"`
}
type bookProjection struct {
	BookID           uuid.UUID  `json:"book_id"`
	Title            string     `json:"title"`
	Description      *string    `json:"description"`
	OriginalLanguage *string    `json:"original_language"`
	SummaryExcerpt   *string    `json:"summary_excerpt"`
	HasCover         bool       `json:"has_cover"`
	CoverURL         *string    `json:"cover_url"`
	ChapterCount     int        `json:"chapter_count"`
	LifecycleState   string     `json:"lifecycle_state"`
	CreatedAt        *time.Time `json:"created_at"`
}

func (s *Server) fetchPublicIDs(limit, offset int, q string) (*sharingPublicList, int) {
	u := fmt.Sprintf("%s/internal/sharing/public?limit=%d&offset=%d", strings.TrimRight(s.cfg.SharingServiceInternalURL, "/"), limit, offset)
	if q != "" {
		u += "&q=" + url.QueryEscape(q)
	}
	res, err := http.Get(u)
	if err != nil {
		return nil, http.StatusBadGateway
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var out sharingPublicList
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, http.StatusBadGateway
	}
	return &out, http.StatusOK
}

func (s *Server) fetchProjection(id uuid.UUID) (*bookProjection, int) {
	res, err := http.Get(fmt.Sprintf("%s/internal/books/%s/projection", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), id))
	if err != nil {
		return nil, http.StatusBadGateway
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var out bookProjection
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, http.StatusBadGateway
	}
	return &out, http.StatusOK
}

func (s *Server) listPublicBooks(w http.ResponseWriter, r *http.Request) {
	limit := 20
	offset := 0
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 100 {
			limit = n
		}
	}
	if v := r.URL.Query().Get("offset"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			offset = n
		}
	}
	q := r.URL.Query().Get("q")
	ids, status := s.fetchPublicIDs(limit, offset, q)
	if status != http.StatusOK {
		writeError(w, http.StatusBadGateway, "BOOK_CONFLICT", "failed to query public books")
		return
	}
	items := make([]map[string]any, 0, len(ids.BookIDs))
	for _, id := range ids.BookIDs {
		p, st := s.fetchProjection(id)
		if st != http.StatusOK || p.LifecycleState != "active" {
			continue
		}
		items = append(items, map[string]any{
			"book_id":           p.BookID,
			"title":             p.Title,
			"description":       p.Description,
			"original_language": p.OriginalLanguage,
			"summary_excerpt":   p.SummaryExcerpt,
			"has_cover":         p.HasCover,
			"cover_url":         p.CoverURL,
			"chapter_count":     p.ChapterCount,
			"visibility":        "public",
			"created_at":        p.CreatedAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": items,
		"total": ids.Total,
	})
}

func (s *Server) getPublicBook(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "CATALOG_INVALID_QUERY", "invalid book id")
		return
	}
	res, err := http.Get(fmt.Sprintf("%s/internal/sharing/public/%s", strings.TrimRight(s.cfg.SharingServiceInternalURL, "/"), bookID))
	if err != nil || res.StatusCode != http.StatusOK {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if res != nil {
		res.Body.Close()
	}
	p, st := s.fetchProjection(bookID)
	if st != http.StatusOK || p.LifecycleState != "active" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":           p.BookID,
		"title":             p.Title,
		"description":       p.Description,
		"original_language": p.OriginalLanguage,
		"summary_excerpt":   p.SummaryExcerpt,
		"has_cover":         p.HasCover,
		"cover_url":         p.CoverURL,
		"chapter_count":     p.ChapterCount,
		"visibility":        "public",
		"created_at":        p.CreatedAt,
	})
}
