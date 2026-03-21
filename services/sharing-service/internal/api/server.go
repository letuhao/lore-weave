package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/sharing-service/internal/config"
)

type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	return &Server{pool: pool, cfg: cfg, secret: []byte(cfg.JWTSecret)}
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

	r.Route("/internal/sharing", func(r chi.Router) {
		r.Get("/public", s.listPublicInternal)
		r.Get("/public/{book_id}", s.getPublicInternal)
		r.Get("/books/{book_id}/visibility", s.getBookVisibilityInternal)
	})

	r.Route("/v1/sharing", func(r chi.Router) {
		r.Get("/books/{book_id}", s.getSharingPolicy)
		r.Patch("/books/{book_id}", s.patchSharingPolicy)
		r.Get("/unlisted/{access_token}", s.getUnlistedBook)
		r.Get("/unlisted/{access_token}/chapters", s.listUnlistedChapters)
		r.Get("/unlisted/{access_token}/chapters/{chapter_id}", s.getUnlistedChapter)
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

type accessClaims struct {
	jwt.RegisteredClaims
}

func (s *Server) requireUserID(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	tokenStr := strings.TrimPrefix(auth, "Bearer ")
	tok, err := jwt.ParseWithClaims(tokenStr, &accessClaims{}, func(t *jwt.Token) (any, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return s.secret, nil
	})
	if err != nil || !tok.Valid {
		return uuid.Nil, false
	}
	claims, ok := tok.Claims.(*accessClaims)
	if !ok {
		return uuid.Nil, false
	}
	id, err := uuid.Parse(claims.Subject)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

type bookProjection struct {
	BookID           uuid.UUID `json:"book_id"`
	OwnerUserID      uuid.UUID `json:"owner_user_id"`
	Title            string    `json:"title"`
	Description      *string   `json:"description"`
	OriginalLanguage *string   `json:"original_language"`
	SummaryExcerpt   *string   `json:"summary_excerpt"`
	HasCover         bool      `json:"has_cover"`
	CoverURL         *string   `json:"cover_url"`
	ChapterCount     int       `json:"chapter_count"`
	LifecycleState   string    `json:"lifecycle_state"`
	CreatedAt        time.Time `json:"created_at"`
}

func (s *Server) fetchBookProjection(bookID uuid.UUID) (*bookProjection, int) {
	res, err := http.Get(fmt.Sprintf("%s/internal/books/%s/projection", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), bookID))
	if err != nil {
		return nil, http.StatusBadGateway
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var p bookProjection
	if err := json.NewDecoder(res.Body).Decode(&p); err != nil {
		return nil, http.StatusBadGateway
	}
	return &p, http.StatusOK
}

func token() string {
	return strings.ReplaceAll(uuid.NewString(), "-", "")
}

func (s *Server) ensurePolicy(ctx context.Context, bookID uuid.UUID) (owner uuid.UUID, policy map[string]any, ok bool) {
	var ownerID uuid.UUID
	var visibility string
	var uToken *string
	var updatedAt time.Time
	err := s.pool.QueryRow(ctx, `SELECT owner_user_id, visibility, unlisted_access_token, updated_at FROM sharing_policies WHERE book_id=$1`, bookID).Scan(&ownerID, &visibility, &uToken, &updatedAt)
	if err == nil {
		return ownerID, map[string]any{
			"book_id":               bookID,
			"visibility":            visibility,
			"unlisted_access_token": uToken,
			"updated_at":            updatedAt,
		}, true
	}
	if err != pgx.ErrNoRows {
		return uuid.Nil, nil, false
	}
	p, status := s.fetchBookProjection(bookID)
	if status != http.StatusOK {
		return uuid.Nil, nil, false
	}
	_, err = s.pool.Exec(ctx, `
INSERT INTO sharing_policies(book_id, owner_user_id, visibility, updated_at)
VALUES($1,$2,'private',now())
ON CONFLICT(book_id) DO NOTHING`, bookID, p.OwnerUserID)
	if err != nil {
		return uuid.Nil, nil, false
	}
	return p.OwnerUserID, map[string]any{
		"book_id":               bookID,
		"visibility":            "private",
		"unlisted_access_token": nil,
		"updated_at":            time.Now().UTC(),
	}, true
}

func parseBookID(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "SHARE_POLICY_INVALID", "invalid book_id")
		return uuid.Nil, false
	}
	return id, true
}

func (s *Server) getSharingPolicy(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseBookID(w, r)
	if !ok {
		return
	}
	owner, policy, ok := s.ensurePolicy(r.Context(), bookID)
	if !ok {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if owner != userID {
		writeError(w, http.StatusForbidden, "BOOK_FORBIDDEN", "forbidden")
		return
	}
	writeJSON(w, http.StatusOK, policy)
}

func (s *Server) patchSharingPolicy(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseBookID(w, r)
	if !ok {
		return
	}
	owner, _, ok := s.ensurePolicy(r.Context(), bookID)
	if !ok {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if owner != userID {
		writeError(w, http.StatusForbidden, "BOOK_FORBIDDEN", "forbidden")
		return
	}
	var in struct {
		Visibility          string `json:"visibility"`
		RotateUnlistedToken bool   `json:"rotate_unlisted_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "SHARE_POLICY_INVALID", "invalid payload")
		return
	}
	if in.Visibility == "" {
		var curr string
		_ = s.pool.QueryRow(r.Context(), `SELECT visibility FROM sharing_policies WHERE book_id=$1`, bookID).Scan(&curr)
		in.Visibility = curr
	}
	if in.Visibility != "private" && in.Visibility != "unlisted" && in.Visibility != "public" {
		writeError(w, http.StatusBadRequest, "SHARE_POLICY_INVALID", "invalid visibility")
		return
	}
	var tok *string
	if in.Visibility == "unlisted" {
		t := token()
		tok = &t
		if !in.RotateUnlistedToken {
			var existing *string
			_ = s.pool.QueryRow(r.Context(), `SELECT unlisted_access_token FROM sharing_policies WHERE book_id=$1`, bookID).Scan(&existing)
			if existing != nil {
				tok = existing
			}
		}
	}
	_, err := s.pool.Exec(r.Context(), `
UPDATE sharing_policies
SET visibility=$2, unlisted_access_token=$3, updated_at=now()
WHERE book_id=$1
`, bookID, in.Visibility, tok)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "SHARE_POLICY_INVALID", "failed to update sharing policy")
		return
	}
	s.getSharingPolicy(w, r)
}

func (s *Server) getUnlistedBook(w http.ResponseWriter, r *http.Request) {
	tokenValue := chi.URLParam(r, "access_token")
	var bookID uuid.UUID
	err := s.pool.QueryRow(r.Context(), `SELECT book_id FROM sharing_policies WHERE visibility='unlisted' AND unlisted_access_token=$1`, tokenValue).Scan(&bookID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to resolve token")
		return
	}
	p, status := s.fetchBookProjection(bookID)
	if status != http.StatusOK || p.LifecycleState != "active" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
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
		"visibility":        "unlisted",
	})
}

func (s *Server) resolveUnlistedBookID(ctx context.Context, tokenValue string) (uuid.UUID, bool) {
	var bookID uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT book_id FROM sharing_policies WHERE visibility='unlisted' AND unlisted_access_token=$1`, tokenValue).Scan(&bookID)
	if err != nil {
		return uuid.Nil, false
	}
	return bookID, true
}

func (s *Server) fetchBookChaptersInternal(bookID uuid.UUID, limit, offset int) (map[string]any, int) {
	res, err := http.Get(fmt.Sprintf("%s/internal/books/%s/chapters?limit=%d&offset=%d", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), bookID, limit, offset))
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

func (s *Server) fetchBookChapterInternal(bookID, chapterID uuid.UUID) (map[string]any, int) {
	res, err := http.Get(fmt.Sprintf("%s/internal/books/%s/chapters/%s", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), bookID, chapterID))
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

func (s *Server) listUnlistedChapters(w http.ResponseWriter, r *http.Request) {
	tokenValue := chi.URLParam(r, "access_token")
	bookID, ok := s.resolveUnlistedBookID(r.Context(), tokenValue)
	if !ok {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
		return
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
	out, status := s.fetchBookChaptersInternal(bookID, limit, offset)
	if status != http.StatusOK {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) getUnlistedChapter(w http.ResponseWriter, r *http.Request) {
	tokenValue := chi.URLParam(r, "access_token")
	bookID, ok := s.resolveUnlistedBookID(r.Context(), tokenValue)
	if !ok {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
		return
	}
	chapterID, err := uuid.Parse(chi.URLParam(r, "chapter_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid chapter_id")
		return
	}
	out, status := s.fetchBookChapterInternal(bookID, chapterID)
	if status != http.StatusOK {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "not found")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) getBookVisibilityInternal(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseBookID(w, r)
	if !ok {
		return
	}
	var visibility string
	err := s.pool.QueryRow(r.Context(), `SELECT visibility FROM sharing_policies WHERE book_id=$1`, bookID).Scan(&visibility)
	if err == pgx.ErrNoRows {
		// Default is private when no row exists yet.
		writeJSON(w, http.StatusOK, map[string]any{
			"book_id":    bookID,
			"visibility": "private",
		})
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to load visibility")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":    bookID,
		"visibility": visibility,
	})
}

func (s *Server) listPublicInternal(w http.ResponseWriter, r *http.Request) {
	limit := 20
	offset := 0
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			limit = n
		}
	}
	if v := r.URL.Query().Get("offset"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			offset = n
		}
	}
	rows, err := s.pool.Query(r.Context(), `SELECT book_id FROM sharing_policies WHERE visibility='public' ORDER BY updated_at DESC LIMIT $1 OFFSET $2`, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to query public list")
		return
	}
	defer rows.Close()
	ids := make([]uuid.UUID, 0)
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err == nil {
			ids = append(ids, id)
		}
	}
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM sharing_policies WHERE visibility='public'`).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"book_ids": ids, "total": total})
}

func (s *Server) getPublicInternal(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseBookID(w, r)
	if !ok {
		return
	}
	var visibility string
	err := s.pool.QueryRow(r.Context(), `SELECT visibility FROM sharing_policies WHERE book_id=$1`, bookID).Scan(&visibility)
	if err == pgx.ErrNoRows || visibility != "public" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not public")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to check visibility")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"book_id": bookID, "visibility": "public"})
}
