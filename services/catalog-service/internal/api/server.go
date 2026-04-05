package api

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"sort"
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

// internalGet makes a GET request to an internal service endpoint with X-Internal-Token.
func (s *Server) internalGet(url string) (*http.Response, error) {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	return http.DefaultClient.Do(req)
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
		r.Get("/books/{book_id}/chapters", s.listPublicBookChapters)
		r.Get("/books/{book_id}/chapters/{chapter_id}", s.getPublicBookChapter)
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
	OwnerUserID      uuid.UUID  `json:"owner_user_id"`
	Title            string     `json:"title"`
	Description      *string    `json:"description"`
	OriginalLanguage *string    `json:"original_language"`
	SummaryExcerpt   *string    `json:"summary_excerpt"`
	HasCover         bool       `json:"has_cover"`
	CoverURL         *string    `json:"cover_url"`
	ChapterCount     int        `json:"chapter_count"`
	LifecycleState   string     `json:"lifecycle_state"`
	GenreTags        []string   `json:"genre_tags"`
	CreatedAt        *time.Time `json:"created_at"`
}

func (s *Server) fetchPublicIDs(limit, offset int, q string) (*sharingPublicList, int) {
	u := fmt.Sprintf("%s/internal/sharing/public?limit=%d&offset=%d", strings.TrimRight(s.cfg.SharingServiceInternalURL, "/"), limit, offset)
	if q != "" {
		u += "&q=" + url.QueryEscape(q)
	}
	res, err := s.internalGet(u)
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
	res, err := s.internalGet(fmt.Sprintf("%s/internal/books/%s/projection", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), id))
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

func (s *Server) fetchPublicChapterList(bookID uuid.UUID, limit, offset int) (map[string]any, int) {
	res, err := s.internalGet(fmt.Sprintf("%s/internal/books/%s/chapters?limit=%d&offset=%d", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), bookID, limit, offset))
	if err != nil {
		return nil, http.StatusBadGateway
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var out map[string]any
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, http.StatusBadGateway
	}
	return out, http.StatusOK
}

func (s *Server) fetchPublicChapterDetail(bookID, chapterID uuid.UUID) (map[string]any, int) {
	res, err := s.internalGet(fmt.Sprintf("%s/internal/books/%s/chapters/%s", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), bookID, chapterID))
	if err != nil {
		return nil, http.StatusBadGateway
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var out map[string]any
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, http.StatusBadGateway
	}
	return out, http.StatusOK
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
	language := r.URL.Query().Get("language")
	genre := r.URL.Query().Get("genre") // filter by genre tag (OR if comma-separated)
	sortBy := r.URL.Query().Get("sort") // recent, chapters, alpha

	// Parse genre filter into a set for fast lookup
	genreFilter := make(map[string]bool)
	if genre != "" {
		for _, g := range strings.Split(genre, ",") {
			g = strings.TrimSpace(g)
			if g != "" {
				genreFilter[g] = true
			}
		}
	}

	// Fetch a large page to allow client-side filter/sort
	// (sharing-service handles the "public" gate, we filter further here)
	fetchLimit := 200
	ids, status := s.fetchPublicIDs(fetchLimit, 0, q)
	if status != http.StatusOK {
		writeError(w, http.StatusBadGateway, "BOOK_CONFLICT", "failed to query public books")
		return
	}

	// Collect projections
	type entry struct {
		data map[string]any
		proj *bookProjection
	}
	all := make([]entry, 0, len(ids.BookIDs))
	for _, id := range ids.BookIDs {
		p, st := s.fetchProjection(id)
		if st != http.StatusOK || p.LifecycleState != "active" {
			continue
		}
		// Language filter
		if language != "" && (p.OriginalLanguage == nil || *p.OriginalLanguage != language) {
			continue
		}
		// Genre filter (OR logic: book must have at least one matching genre tag)
		if len(genreFilter) > 0 {
			matched := false
			for _, t := range p.GenreTags {
				if genreFilter[t] {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
		}
		genreTags := p.GenreTags
		if genreTags == nil {
			genreTags = []string{}
		}
		all = append(all, entry{
			data: map[string]any{
				"book_id":           p.BookID,
				"title":             p.Title,
				"description":       p.Description,
				"original_language": p.OriginalLanguage,
				"summary_excerpt":   p.SummaryExcerpt,
				"has_cover":         p.HasCover,
				"cover_url":         p.CoverURL,
				"chapter_count":     p.ChapterCount,
				"genre_tags":        genreTags,
				"visibility":        "public",
				"created_at":        p.CreatedAt,
			},
			proj: p,
		})
	}

	// Sort
	switch sortBy {
	case "alpha":
		sort.Slice(all, func(i, j int) bool {
			return strings.ToLower(all[i].proj.Title) < strings.ToLower(all[j].proj.Title)
		})
	case "chapters":
		sort.Slice(all, func(i, j int) bool {
			return all[i].proj.ChapterCount > all[j].proj.ChapterCount
		})
	default: // "recent" or empty — newest first
		sort.Slice(all, func(i, j int) bool {
			ti := all[i].proj.CreatedAt
			tj := all[j].proj.CreatedAt
			if ti == nil || tj == nil {
				return ti != nil
			}
			return ti.After(*tj)
		})
	}

	// Paginate
	total := len(all)
	end := offset + limit
	if offset > total {
		offset = total
	}
	if end > total {
		end = total
	}
	page := all[offset:end]

	items := make([]map[string]any, len(page))
	for i, e := range page {
		items[i] = e.data
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": items,
		"total": total,
	})
}

func (s *Server) getPublicBook(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "CATALOG_INVALID_QUERY", "invalid book id")
		return
	}
	res, err := s.internalGet(fmt.Sprintf("%s/internal/sharing/public/%s", strings.TrimRight(s.cfg.SharingServiceInternalURL, "/"), bookID))
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
	// Fetch available translation languages (best-effort, non-blocking)
	languages := s.fetchBookLanguages(p.BookID)

	genreTags := p.GenreTags
	if genreTags == nil {
		genreTags = []string{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":             p.BookID,
		"owner_user_id":       p.OwnerUserID,
		"title":               p.Title,
		"description":         p.Description,
		"original_language":   p.OriginalLanguage,
		"summary_excerpt":     p.SummaryExcerpt,
		"has_cover":           p.HasCover,
		"cover_url":           p.CoverURL,
		"chapter_count":       p.ChapterCount,
		"genre_tags":          genreTags,
		"visibility":          "public",
		"created_at":          p.CreatedAt,
		"available_languages": languages,
	})
}

func (s *Server) fetchBookLanguages(bookID uuid.UUID) []map[string]any {
	u := fmt.Sprintf("%s/internal/books/%s/languages", strings.TrimRight(s.cfg.TranslationServiceInternalURL, "/"), bookID)
	res, err := s.internalGet(u)
	if err != nil {
		log.Printf("[catalog] failed to fetch languages for book %s: %v", bookID, err)
		return []map[string]any{}
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		log.Printf("[catalog] translation-service returned %d for book %s languages", res.StatusCode, bookID)
		return []map[string]any{}
	}
	var out struct {
		Languages []struct {
			Language     string `json:"language"`
			ChapterCount int    `json:"chapter_count"`
		} `json:"languages"`
	}
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil
	}
	result := make([]map[string]any, len(out.Languages))
	for i, l := range out.Languages {
		result[i] = map[string]any{"language": l.Language, "chapter_count": l.ChapterCount}
	}
	return result
}

func (s *Server) listPublicBookChapters(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "CATALOG_INVALID_QUERY", "invalid book id")
		return
	}
	res, err := s.internalGet(fmt.Sprintf("%s/internal/sharing/public/%s", strings.TrimRight(s.cfg.SharingServiceInternalURL, "/"), bookID))
	if err != nil || res.StatusCode != http.StatusOK {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if res != nil {
		res.Body.Close()
	}
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
	out, status := s.fetchPublicChapterList(bookID, limit, offset)
	if status != http.StatusOK {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) getPublicBookChapter(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "CATALOG_INVALID_QUERY", "invalid book id")
		return
	}
	chapterID, err := uuid.Parse(chi.URLParam(r, "chapter_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "CATALOG_INVALID_QUERY", "invalid chapter id")
		return
	}
	res, err := s.internalGet(fmt.Sprintf("%s/internal/sharing/public/%s", strings.TrimRight(s.cfg.SharingServiceInternalURL, "/"), bookID))
	if err != nil || res.StatusCode != http.StatusOK {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if res != nil {
		res.Body.Close()
	}
	out, status := s.fetchPublicChapterDetail(bookID, chapterID)
	if status != http.StatusOK {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	writeJSON(w, http.StatusOK, out)
}
