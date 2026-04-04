package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
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
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"github.com/loreweave/book-service/internal/config"
)

type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
	minio  *minio.Client
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	s := &Server{pool: pool, cfg: cfg, secret: []byte(cfg.JWTSecret)}
	if cfg.MinioEndpoint != "" && cfg.MinioSecretKey != "" {
		mc, err := minio.New(cfg.MinioEndpoint, &minio.Options{
			Creds:  credentials.NewStaticV4(cfg.MinioAccessKey, cfg.MinioSecretKey, ""),
			Secure: cfg.MinioUseSSL,
		})
		if err == nil {
			s.minio = mc
		}
	}
	return s
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

	r.Route("/internal", func(r chi.Router) {
		r.Get("/books/{book_id}/projection", s.getBookProjection)
		r.Get("/books/{book_id}/chapters", s.getInternalBookChapters)
		r.Get("/books/{book_id}/chapters/{chapter_id}", s.getInternalBookChapter)
	})

	r.Route("/v1/books", func(r chi.Router) {
		r.Get("/storage-usage", s.getStorageUsage)
		r.Post("/", s.createBook)
		r.Get("/", s.listBooks)
		r.Get("/trash", s.listTrashedBooks)

		r.Route("/{book_id}", func(r chi.Router) {
			r.Get("/", s.getBook)
			r.Patch("/", s.patchBook)
			r.Delete("/", s.trashBook)
			r.Post("/restore", s.restoreBook)
			r.Delete("/purge", s.purgeBook)

			r.Get("/cover", s.getCover)
			r.Post("/cover", s.uploadCover)
			r.Delete("/cover", s.deleteCover)

			r.Get("/chapters", s.listChapters)
			r.Post("/chapters", s.createChapter)

			r.Route("/chapters/{chapter_id}", func(r chi.Router) {
				r.Get("/", s.getChapter)
				r.Patch("/", s.patchChapter)
				r.Delete("/", s.trashChapter)
				r.Post("/restore", s.restoreChapter)
				r.Delete("/purge", s.purgeChapter)
				r.Get("/content", s.getChapterContent)
				r.Get("/export", s.exportChapter)
				r.Get("/draft", s.getDraft)
				r.Patch("/draft", s.patchDraft)
				r.Get("/revisions", s.listRevisions)
				r.Get("/revisions/{revision_id}", s.getRevision)
				r.Post("/revisions/{revision_id}/restore", s.restoreRevision)
				r.Post("/media", s.uploadChapterMedia)
				r.Post("/media-generate", s.generateChapterMedia)
				r.Get("/media-versions", s.listMediaVersions)
				r.Post("/media-versions", s.createMediaVersion)
				r.Delete("/media-versions/{version_id}", s.deleteMediaVersion)
			})
		})
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

func parseUUIDParam(w http.ResponseWriter, r *http.Request, name string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, name))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid "+name)
		return uuid.Nil, false
	}
	return id, true
}

func (s *Server) ensureOwnerBook(ctx context.Context, bookID, ownerID uuid.UUID) (lifecycle string, ok bool, status int) {
	err := s.pool.QueryRow(ctx, `SELECT lifecycle_state FROM books WHERE id=$1 AND owner_user_id=$2`, bookID, ownerID).Scan(&lifecycle)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", false, http.StatusNotFound
	}
	if err != nil {
		return "", false, http.StatusInternalServerError
	}
	return lifecycle, true, http.StatusOK
}

func (s *Server) fetchSharingVisibility(ctx context.Context, bookID uuid.UUID) string {
	if strings.TrimSpace(s.cfg.SharingInternalURL) == "" {
		return "private"
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("%s/internal/sharing/books/%s/visibility", strings.TrimRight(s.cfg.SharingInternalURL, "/"), bookID), nil)
	if err != nil {
		return "private"
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "private"
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "private"
	}
	var out struct {
		Visibility string `json:"visibility"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "private"
	}
	switch out.Visibility {
	case "private", "unlisted", "public":
		return out.Visibility
	default:
		return "private"
	}
}

func parseLimitOffset(r *http.Request) (limit, offset int) {
	limit = 20
	offset = 0
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
	return
}

func (s *Server) ensureQuotaRow(ctx context.Context, ownerID uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `
INSERT INTO user_storage_quota(owner_user_id, used_bytes, quota_bytes)
VALUES($1, 0, $2)
ON CONFLICT(owner_user_id) DO NOTHING
`, ownerID, s.cfg.QuotaBytesDefault)
	return err
}

func (s *Server) recalcQuota(ctx context.Context, ownerID uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `
WITH bytes AS (
  SELECT COALESCE(SUM(c.byte_size),0)::bigint AS chapter_bytes
  FROM books b
  JOIN chapters c ON c.book_id=b.id
  WHERE b.owner_user_id=$1 AND c.lifecycle_state!='purge_pending'
), cover AS (
  SELECT COALESCE(SUM(a.byte_size),0)::bigint AS cover_bytes
  FROM books b
  JOIN book_cover_assets a ON a.book_id=b.id
  WHERE b.owner_user_id=$1
)
UPDATE user_storage_quota q
SET used_bytes = bytes.chapter_bytes + cover.cover_bytes
FROM bytes, cover
WHERE q.owner_user_id=$1
`, ownerID)
	return err
}

func (s *Server) getStorageUsage(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil || s.recalcQuota(ctx, ownerID) != nil {
		writeError(w, http.StatusInternalServerError, "STORAGE_BACKEND_ERROR", "failed to load storage usage")
		return
	}
	var used, quota int64
	if err := s.pool.QueryRow(ctx, `SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, ownerID).Scan(&used, &quota); err != nil {
		writeError(w, http.StatusInternalServerError, "STORAGE_BACKEND_ERROR", "failed to load storage usage")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"used_bytes": used, "quota_bytes": quota})
}

func (s *Server) createBook(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	var in struct {
		Title            string `json:"title"`
		Description      string   `json:"description"`
		OriginalLanguage string   `json:"original_language"`
		Summary          string   `json:"summary"`
		GenreTags        []string `json:"genre_tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || strings.TrimSpace(in.Title) == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "title is required")
		return
	}
	if in.GenreTags == nil {
		in.GenreTags = []string{}
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to initialize quota")
		return
	}
	var bookID uuid.UUID
	if err := s.pool.QueryRow(ctx, `
INSERT INTO books(owner_user_id,title,description,original_language,summary,genre_tags)
VALUES($1,$2,$3,$4,$5,$6)
RETURNING id
`, ownerID, in.Title, in.Description, in.OriginalLanguage, in.Summary, in.GenreTags).Scan(&bookID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create book")
		return
	}
	s.getBookByID(w, ctx, bookID, ownerID, http.StatusCreated)
}

func (s *Server) listBooks(w http.ResponseWriter, r *http.Request) {
	s.listBooksByLifecycle(w, r, "active")
}

func (s *Server) listTrashedBooks(w http.ResponseWriter, r *http.Request) {
	s.listBooksByLifecycle(w, r, "trashed")
}

func (s *Server) listBooksByLifecycle(w http.ResponseWriter, r *http.Request, lifecycle string) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	limit, offset := parseLimitOffset(r)
	ctx := r.Context()
	rows, err := s.pool.Query(ctx, `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.lifecycle_state,b.trashed_at,b.purge_eligible_at,b.created_at,b.updated_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0) AS chapter_count,
  EXISTS(SELECT 1 FROM book_cover_assets a WHERE a.book_id=b.id) AS has_cover,
  b.genre_tags
FROM books b
WHERE b.owner_user_id=$1 AND b.lifecycle_state=$2
ORDER BY b.created_at DESC
LIMIT $3 OFFSET $4
`, ownerID, lifecycle, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list books")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, owner uuid.UUID
		var title, state string
		var desc, lang, summary *string
		var trashedAt, purgeAt, createdAt, updatedAt *time.Time
		var chapterCount int
		var hasCover bool
		var genreTags []string
		if err := rows.Scan(&id, &owner, &title, &desc, &lang, &summary, &state, &trashedAt, &purgeAt, &createdAt, &updatedAt, &chapterCount, &hasCover, &genreTags); err == nil {
			if genreTags == nil {
				genreTags = []string{}
			}
			visibility := s.fetchSharingVisibility(ctx, id)
			items = append(items, map[string]any{
				"book_id":           id,
				"owner_user_id":     owner,
				"title":             title,
				"description":       desc,
				"original_language": lang,
				"summary":           summary,
				"lifecycle_state":   state,
				"trashed_at":        trashedAt,
				"purge_eligible_at": purgeAt,
				"chapter_count":     chapterCount,
				"has_cover":         hasCover,
				"visibility":        visibility,
				"genre_tags":        genreTags,
				"created_at":        createdAt,
				"updated_at":        updatedAt,
			})
		}
	}
	var total int
	_ = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM books WHERE owner_user_id=$1 AND lifecycle_state=$2`, ownerID, lifecycle).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

func nullableString(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func (s *Server) getBook(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	s.getBookByID(w, r.Context(), bookID, ownerID, http.StatusOK)
}

func (s *Server) getBookByID(w http.ResponseWriter, ctx context.Context, bookID, ownerID uuid.UUID, status int) {
	var id, owner uuid.UUID
	var title, state string
	var desc, lang, summary *string
	var trashedAt, purgeAt, createdAt, updatedAt *time.Time
	var chapterCount int
	var genreTags []string
	err := s.pool.QueryRow(ctx, `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.lifecycle_state,b.trashed_at,b.purge_eligible_at,b.created_at,b.updated_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0) AS chapter_count,
  b.genre_tags
FROM books b
WHERE b.id=$1 AND b.owner_user_id=$2
`, bookID, ownerID).Scan(&id, &owner, &title, &desc, &lang, &summary, &state, &trashedAt, &purgeAt, &createdAt, &updatedAt, &chapterCount, &genreTags)
	if errors.Is(err, pgx.ErrNoRows) || state == "purge_pending" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to get book")
		return
	}

	var cover any
	var ctype, skey string
	var csize int64
	var cupdated *time.Time
	if err := s.pool.QueryRow(ctx, `SELECT content_type, byte_size, storage_key, updated_at FROM book_cover_assets WHERE book_id=$1`, bookID).Scan(&ctype, &csize, &skey, &cupdated); err == nil {
		cover = map[string]any{
			"content_type": ctype,
			"byte_size":    csize,
			"download_url": fmt.Sprintf("/v1/books/%s/cover?key=%s", bookID, skey),
		}
	}
	if genreTags == nil {
		genreTags = []string{}
	}
	writeJSON(w, status, map[string]any{
		"book_id":           id,
		"owner_user_id":     owner,
		"title":             title,
		"description":       desc,
		"original_language": lang,
		"summary":           summary,
		"cover":             cover,
		"chapter_count":     chapterCount,
		"visibility":        s.fetchSharingVisibility(ctx, id),
		"lifecycle_state":   state,
		"genre_tags":        genreTags,
		"trashed_at":        trashedAt,
		"purge_eligible_at": purgeAt,
		"created_at":        createdAt,
		"updated_at":        updatedAt,
	})
}

func (s *Server) patchBook(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		if status == http.StatusNotFound {
			writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		} else {
			writeError(w, status, "BOOK_CONFLICT", "failed to read book")
		}
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book is not active")
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	// Build dynamic UPDATE — only set fields that were explicitly provided in the payload.
	// This allows sending null to clear a field (vs omitting to keep it unchanged).
	setClauses := []string{"updated_at=now()"}
	args := []any{bookID, ownerID}
	paramIdx := 3
	if _, ok := in["title"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("title=COALESCE($%d,title)", paramIdx))
		args = append(args, stringFromAny(in["title"]))
		paramIdx++
	}
	if _, ok := in["description"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("description=$%d", paramIdx))
		args = append(args, stringFromAny(in["description"]))
		paramIdx++
	}
	if _, ok := in["original_language"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("original_language=$%d", paramIdx))
		args = append(args, stringFromAny(in["original_language"]))
		paramIdx++
	}
	if _, ok := in["summary"]; ok {
		setClauses = append(setClauses, fmt.Sprintf("summary=$%d", paramIdx))
		args = append(args, stringFromAny(in["summary"]))
		paramIdx++
	}
	if v, ok := in["genre_tags"]; ok {
		tags := make([]string, 0)
		if arr, ok := v.([]any); ok {
			for _, item := range arr {
				if s, ok := item.(string); ok {
					tags = append(tags, s)
				}
			}
		}
		setClauses = append(setClauses, fmt.Sprintf("genre_tags=$%d", paramIdx))
		args = append(args, tags)
		paramIdx++
	}
	query := fmt.Sprintf("UPDATE books SET %s WHERE id=$1 AND owner_user_id=$2", strings.Join(setClauses, ", "))
	_, err := s.pool.Exec(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch book")
		return
	}
	s.getBookByID(w, r.Context(), bookID, ownerID, http.StatusOK)
}

func stringFromAny(v any) *string {
	if v == nil {
		return nil
	}
	s, ok := v.(string)
	if !ok {
		return nil
	}
	return &s
}

func (s *Server) trashBook(w http.ResponseWriter, r *http.Request) {
	s.transitionBookLifecycle(w, r, "trashed")
}
func (s *Server) restoreBook(w http.ResponseWriter, r *http.Request) {
	s.transitionBookLifecycle(w, r, "active")
}
func (s *Server) purgeBook(w http.ResponseWriter, r *http.Request) {
	s.transitionBookLifecycle(w, r, "purge_pending")
}

func (s *Server) transitionBookLifecycle(w http.ResponseWriter, r *http.Request, target string) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	ctx := r.Context()
	lifecycle, okBook, status := s.ensureOwnerBook(ctx, bookID, ownerID)
	if !okBook {
		if status == http.StatusNotFound {
			writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		} else {
			writeError(w, status, "BOOK_CONFLICT", "failed to read book")
		}
		return
	}
	switch target {
	case "trashed":
		if lifecycle != "active" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "only active book can be trashed")
			return
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE book_id=$1 AND lifecycle_state='active'`, bookID)
		w.WriteHeader(http.StatusNoContent)
	case "active":
		if lifecycle != "trashed" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book must be trashed before restore")
			return
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='active', trashed_at=NULL, purge_eligible_at=NULL, updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='active', trashed_at=NULL, purge_eligible_at=NULL, updated_at=now() WHERE book_id=$1`, bookID)
		s.getBookByID(w, ctx, bookID, ownerID, http.StatusOK)
	case "purge_pending":
		if lifecycle != "trashed" {
			writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book must be trashed before purge")
			return
		}
		_, _ = s.pool.Exec(ctx, `UPDATE books SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE id=$1`, bookID)
		_, _ = s.pool.Exec(ctx, `UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE book_id=$1`, bookID)
		w.WriteHeader(http.StatusNoContent)
	default:
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "unsupported transition")
	}
}

func (s *Server) uploadCover(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "BOOK_INVALID_LIFECYCLE", "book not active")
		return
	}
	if err := r.ParseMultipartForm(10 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid multipart")
		return
	}
	f, fh, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
		return
	}
	defer f.Close()
	data, _ := io.ReadAll(f)
	contentType := fh.Header.Get("Content-Type")
	if !strings.HasPrefix(contentType, "image/") {
		writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", "cover must be image/*")
		return
	}
	ctx := r.Context()
	if err := s.ensureQuotaRow(ctx, ownerID); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "quota init failed")
		return
	}
	_, err = s.pool.Exec(ctx, `
INSERT INTO book_cover_assets(book_id, content_type, byte_size, storage_key, data, updated_at)
VALUES($1,$2,$3,$4,$5,now())
ON CONFLICT(book_id) DO UPDATE SET content_type=EXCLUDED.content_type, byte_size=EXCLUDED.byte_size, storage_key=EXCLUDED.storage_key, data=EXCLUDED.data, updated_at=now()
`, bookID, contentType, int64(len(data)), fmt.Sprintf("covers/%s", bookID), data)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to save cover")
		return
	}
	_ = s.recalcQuota(ctx, ownerID)
	s.getBookByID(w, ctx, bookID, ownerID, http.StatusOK)
}

func (s *Server) deleteCover(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	_, err := s.pool.Exec(r.Context(), `DELETE FROM book_cover_assets WHERE book_id=$1 AND EXISTS (SELECT 1 FROM books WHERE id=$1 AND owner_user_id=$2)`, bookID, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to delete cover")
		return
	}
	_ = s.recalcQuota(r.Context(), ownerID)
	s.getBookByID(w, r.Context(), bookID, ownerID, http.StatusOK)
}

func (s *Server) getCover(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	var contentType string
	var data []byte
	err := s.pool.QueryRow(r.Context(), `
SELECT a.content_type, a.data
FROM book_cover_assets a
JOIN books b ON b.id=a.book_id
WHERE a.book_id=$1 AND b.owner_user_id=$2
`, bookID, ownerID).Scan(&contentType, &data)
	if err != nil {
		writeError(w, http.StatusNotFound, "COVER_NOT_FOUND", "cover not found")
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "private, max-age=3600")
	_, _ = w.Write(data)
}

func (s *Server) listChapters(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	state, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		return
	}
	lifecycle := r.URL.Query().Get("lifecycle_state")
	if lifecycle == "" {
		if state == "trashed" {
			lifecycle = "trashed"
		} else {
			lifecycle = "active"
		}
	}
	limit, offset := parseLimitOffset(r)
	args := []any{bookID, lifecycle}
	where := `book_id=$1 AND lifecycle_state=$2`
	if v := r.URL.Query().Get("original_language"); v != "" {
		args = append(args, v)
		where += fmt.Sprintf(" AND original_language=$%d", len(args))
	}
	if v := r.URL.Query().Get("sort_order"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			args = append(args, n)
			where += fmt.Sprintf(" AND sort_order=$%d", len(args))
		}
	}
	countArgs := append([]any{}, args...)
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapters WHERE `+where, countArgs...).Scan(&total)
	args = append(args, limit, offset)
	rows, err := s.pool.Query(r.Context(), `SELECT id,book_id,title,original_filename,original_language,content_type,byte_size,sort_order,draft_updated_at,draft_revision_count,lifecycle_state,trashed_at,purge_eligible_at,created_at,updated_at FROM chapters WHERE `+where+` ORDER BY sort_order, created_at LIMIT $`+strconv.Itoa(len(args)-1)+` OFFSET $`+strconv.Itoa(len(args)), args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to list chapters")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id, bid uuid.UUID
		var title, fn, lang, ctype, lstate string
		var size int64
		var order int
		var draftUpdated, trashedAt, purgeAt, createdAt, updatedAt *time.Time
		var revCount int
		_ = rows.Scan(&id, &bid, &title, &fn, &lang, &ctype, &size, &order, &draftUpdated, &revCount, &lstate, &trashedAt, &purgeAt, &createdAt, &updatedAt)
		items = append(items, map[string]any{
			"chapter_id":           id,
			"book_id":              bid,
			"title":                nullableString(title),
			"original_filename":    fn,
			"original_language":    lang,
			"content_type":         ctype,
			"byte_size":            size,
			"sort_order":           order,
			"draft_updated_at":     draftUpdated,
			"draft_revision_count": revCount,
			"lifecycle_state":      lstate,
			"trashed_at":           trashedAt,
			"purge_eligible_at":    purgeAt,
			"created_at":           createdAt,
			"updated_at":           updatedAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

func (s *Server) createChapter(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	lifecycle, okBook, status := s.ensureOwnerBook(r.Context(), bookID, ownerID)
	if !okBook {
		writeError(w, status, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if lifecycle != "active" {
		writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "parent book is not active")
		return
	}
	contentType := strings.ToLower(r.Header.Get("Content-Type"))
	switch {
	case strings.HasPrefix(contentType, "application/json"):
		var in struct {
			Title            string `json:"title"`
			OriginalLanguage string `json:"original_language"`
			SortOrder        int    `json:"sort_order"`
			Body             string `json:"body"`
		}
		if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
			return
		}
		if strings.TrimSpace(in.OriginalLanguage) == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "original_language is required")
			return
		}
		filename := fmt.Sprintf("editor-%s.txt", uuid.NewString())
		s.createChapterRecord(w, r.Context(), ownerID, bookID, in.Title, filename, in.OriginalLanguage, in.SortOrder, in.Body, "seed from editor", true)
		return
	default:
		if err := r.ParseMultipartForm(50 << 20); err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid multipart")
			return
		}
		lang := r.FormValue("original_language")
		if lang == "" {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "original_language is required")
			return
		}
		f, fh, err := r.FormFile("file")
		if err != nil {
			writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "file is required")
			return
		}
		defer f.Close()
		if ct := fh.Header.Get("Content-Type"); !strings.Contains(ct, "text/plain") {
			writeError(w, http.StatusUnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE", "chapter must be text/plain")
			return
		}
		data, _ := io.ReadAll(f)
		title := r.FormValue("title")
		sortOrder := 0
		if v := r.FormValue("sort_order"); v != "" {
			sortOrder, _ = strconv.Atoi(v)
		}
		s.createChapterRecord(w, r.Context(), ownerID, bookID, title, fh.Filename, lang, sortOrder, string(data), "seed from upload", true)
	}
}

func (s *Server) createChapterRecord(
	w http.ResponseWriter,
	ctx context.Context,
	ownerID uuid.UUID,
	bookID uuid.UUID,
	title string,
	originalFilename string,
	lang string,
	sortOrder int,
	body string,
	revisionMessage string,
	includeRaw bool,
) {
	if sortOrder == 0 {
		_ = s.pool.QueryRow(ctx, `SELECT COALESCE(MAX(sort_order),0)+1 FROM chapters WHERE book_id=$1`, bookID).Scan(&sortOrder)
	}
	_ = s.ensureQuotaRow(ctx, ownerID)
	var used, quota int64
	_ = s.recalcQuota(ctx, ownerID)
	_ = s.pool.QueryRow(ctx, `SELECT used_bytes, quota_bytes FROM user_storage_quota WHERE owner_user_id=$1`, ownerID).Scan(&used, &quota)
	if used+int64(len(body)) > quota {
		writeError(w, http.StatusInsufficientStorage, "STORAGE_QUOTA_EXCEEDED", "quota exceeded")
		return
	}
	// Convert plain text → Tiptap JSON with _text snapshots
	jsonBody := plainTextToTiptapJSON(body)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create chapter")
		return
	}
	defer tx.Rollback(ctx)
	var chapterID uuid.UUID
	err = tx.QueryRow(ctx, `
INSERT INTO chapters(book_id,title,original_filename,original_language,content_type,byte_size,sort_order,storage_key,lifecycle_state,draft_updated_at,updated_at)
VALUES($1,$2,$3,$4,'text/plain',$5,$6,$7,'active',now(),now())
RETURNING id
`, bookID, nullIfEmpty(title), originalFilename, lang, int64(len(body)), sortOrder, fmt.Sprintf("chapters/%s/%s", bookID, uuid.New())).Scan(&chapterID)
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "duplicate sort/language or invalid chapter")
		return
	}
	if includeRaw {
		_, _ = tx.Exec(ctx, `INSERT INTO chapter_raw_objects(chapter_id, body_text) VALUES($1,$2)`, chapterID, body)
	}
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_drafts(chapter_id, body, draft_format, draft_updated_at, draft_version) VALUES($1,$2,'json',now(),1)`, chapterID, jsonBody)
	_, _ = tx.Exec(ctx, `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`, chapterID, jsonBody, "json", revisionMessage, ownerID)
	_, _ = tx.Exec(ctx, `UPDATE chapters SET draft_revision_count=1 WHERE id=$1`, chapterID)
	if err := insertOutboxEvent(ctx, tx, "chapter.created", chapterID, map[string]any{"book_id": bookID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit chapter")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to commit chapter")
		return
	}
	_ = s.recalcQuota(ctx, ownerID)
	s.getChapterByID(w, ctx, bookID, chapterID, ownerID, http.StatusCreated)
}

func nullIfEmpty(v string) any {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	return v
}

func (s *Server) getChapter(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	s.getChapterByID(w, r.Context(), bookID, chID, ownerID, http.StatusOK)
}

func (s *Server) getChapterByID(w http.ResponseWriter, ctx context.Context, bookID, chapterID, ownerID uuid.UUID, status int) {
	var id, bid uuid.UUID
	var title, fn, lang, ctype, state string
	var size int64
	var order, revCount int
	var draftUpdated, trashedAt, purgeAt, createdAt, updatedAt *time.Time
	err := s.pool.QueryRow(ctx, `
SELECT c.id,c.book_id,c.title,c.original_filename,c.original_language,c.content_type,c.byte_size,c.sort_order,c.draft_updated_at,c.draft_revision_count,c.lifecycle_state,c.trashed_at,c.purge_eligible_at,c.created_at,c.updated_at
FROM chapters c
JOIN books b ON b.id=c.book_id
WHERE c.id=$1 AND c.book_id=$2 AND b.owner_user_id=$3
`, chapterID, bookID, ownerID).Scan(&id, &bid, &title, &fn, &lang, &ctype, &size, &order, &draftUpdated, &revCount, &state, &trashedAt, &purgeAt, &createdAt, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) || state == "purge_pending" {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to get chapter")
		return
	}
	writeJSON(w, status, map[string]any{
		"chapter_id":           id,
		"book_id":              bid,
		"title":                nullableString(title),
		"original_filename":    fn,
		"original_language":    lang,
		"content_type":         ctype,
		"byte_size":            size,
		"sort_order":           order,
		"draft_updated_at":     draftUpdated,
		"draft_revision_count": revCount,
		"lifecycle_state":      state,
		"trashed_at":           trashedAt,
		"purge_eligible_at":    purgeAt,
		"created_at":           createdAt,
		"updated_at":           updatedAt,
	})
}

func (s *Server) patchChapter(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var in map[string]any
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid payload")
		return
	}
	var bState, cState string
	err := s.pool.QueryRow(r.Context(), `
SELECT b.lifecycle_state,c.lifecycle_state
FROM books b JOIN chapters c ON c.book_id=b.id
WHERE b.id=$1 AND c.id=$2 AND b.owner_user_id=$3
`, bookID, chID, ownerID).Scan(&bState, &cState)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to patch chapter")
		return
	}
	if bState != "active" || cState != "active" {
		writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "parent book not active or chapter not patchable")
		return
	}
	_, err = s.pool.Exec(r.Context(), `
UPDATE chapters
SET title=COALESCE($3,title),
    sort_order=COALESCE($4,sort_order),
    original_language=COALESCE($5,original_language),
    updated_at=now()
WHERE id=$1 AND book_id=$2
`, chID, bookID, stringFromAny(in["title"]), intFromAny(in["sort_order"]), stringFromAny(in["original_language"]))
	if err != nil {
		writeError(w, http.StatusConflict, "BOOK_CONFLICT", "failed to patch chapter")
		return
	}
	s.getChapterByID(w, r.Context(), bookID, chID, ownerID, http.StatusOK)
}

func intFromAny(v any) any {
	switch x := v.(type) {
	case float64:
		return int(x)
	case int:
		return x
	default:
		return nil
	}
}

func (s *Server) trashChapter(w http.ResponseWriter, r *http.Request) {
	s.transitionChapterLifecycle(w, r, "trashed")
}
func (s *Server) restoreChapter(w http.ResponseWriter, r *http.Request) {
	s.transitionChapterLifecycle(w, r, "active")
}
func (s *Server) purgeChapter(w http.ResponseWriter, r *http.Request) {
	s.transitionChapterLifecycle(w, r, "purge_pending")
}
func (s *Server) transitionChapterLifecycle(w http.ResponseWriter, r *http.Request, target string) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var bState, cState string
	err := s.pool.QueryRow(r.Context(), `
SELECT b.lifecycle_state,c.lifecycle_state FROM books b JOIN chapters c ON c.book_id=b.id
WHERE b.id=$1 AND c.id=$2 AND b.owner_user_id=$3
`, bookID, chID, ownerID).Scan(&bState, &cState)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to transition chapter")
		return
	}
	switch target {
	case "trashed":
		if bState != "active" || cState != "active" {
			writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "invalid lifecycle for trash")
			return
		}
		tx, txErr := s.pool.Begin(r.Context())
		if txErr != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash chapter")
			return
		}
		defer tx.Rollback(r.Context())
		_, _ = tx.Exec(r.Context(), `UPDATE chapters SET lifecycle_state='trashed', trashed_at=now(), updated_at=now() WHERE id=$1`, chID)
		if err := insertOutboxEvent(r.Context(), tx, "chapter.trashed", chID, map[string]any{"book_id": bookID}); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash chapter")
			return
		}
		if err := tx.Commit(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to trash chapter")
			return
		}
		w.WriteHeader(http.StatusNoContent)
	case "active":
		if bState != "active" || cState != "trashed" {
			writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "chapter not trashed or book inactive")
			return
		}
		_, _ = s.pool.Exec(r.Context(), `UPDATE chapters SET lifecycle_state='active', trashed_at=NULL, purge_eligible_at=NULL, updated_at=now() WHERE id=$1`, chID)
		s.getChapterByID(w, r.Context(), bookID, chID, ownerID, http.StatusOK)
	case "purge_pending":
		if cState != "trashed" {
			writeError(w, http.StatusConflict, "CHAPTER_INVALID_LIFECYCLE", "chapter must be trashed before purge")
			return
		}
		tx, txErr := s.pool.Begin(r.Context())
		if txErr != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to purge chapter")
			return
		}
		defer tx.Rollback(r.Context())
		_, _ = tx.Exec(r.Context(), `UPDATE chapters SET lifecycle_state='purge_pending', purge_eligible_at=now(), updated_at=now() WHERE id=$1`, chID)
		if err := insertOutboxEvent(r.Context(), tx, "chapter.deleted", chID, map[string]any{"book_id": bookID}); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to purge chapter")
			return
		}
		if err := tx.Commit(r.Context()); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to purge chapter")
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}

func (s *Server) getChapterContent(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var body string
	err := s.pool.QueryRow(r.Context(), `
SELECT ro.body_text
FROM chapter_raw_objects ro
JOIN chapters c ON c.id=ro.chapter_id
JOIN books b ON b.id=c.book_id
WHERE c.id=$1 AND c.book_id=$2 AND b.owner_user_id=$3
`, chID, bookID, ownerID).Scan(&body)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to fetch content")
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(body))
}

func (s *Server) exportChapter(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var originalFilename string
	var title *string
	err := s.pool.QueryRow(r.Context(), `
SELECT c.title, c.original_filename
FROM chapters c
JOIN books b ON b.id=c.book_id
WHERE c.id=$1 AND c.book_id=$2 AND b.owner_user_id=$3
`, chID, bookID, ownerID).Scan(&title, &originalFilename)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to fetch chapter")
		return
	}
	// Read plain text from chapter_blocks (trigger-extracted); fall back to draft body
	var textContent string
	err = s.pool.QueryRow(r.Context(), `
SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
FROM chapter_blocks WHERE chapter_id=$1
`, chID).Scan(&textContent)
	if err != nil || textContent == "" {
		// Fallback: no blocks yet (legacy data), read raw draft body as text
		var rawBody []byte
		if ferr := s.pool.QueryRow(r.Context(), `SELECT d.body FROM chapter_drafts d WHERE d.chapter_id=$1`, chID).Scan(&rawBody); ferr != nil {
			writeError(w, http.StatusInternalServerError, "CHAPTER_EXPORT_FAILED", "failed to fetch draft")
			return
		}
		textContent = string(rawBody)
	}
	filename := "chapter.txt"
	if title != nil && *title != "" {
		filename = *title + ".txt"
	} else if originalFilename != "" {
		filename = originalFilename
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="`+filename+`"`)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(textContent))
}

func (s *Server) getDraft(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var chapterID uuid.UUID
	var body json.RawMessage
	var format string
	var updated time.Time
	var version int64
	err := s.pool.QueryRow(r.Context(), `
SELECT d.chapter_id,d.body,d.draft_format,d.draft_updated_at,d.draft_version
FROM chapter_drafts d
JOIN chapters c ON c.id=d.chapter_id
JOIN books b ON b.id=c.book_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND b.owner_user_id=$3
`, chID, bookID, ownerID).Scan(&chapterID, &body, &format, &updated, &version)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to get draft")
		return
	}
	var textContent *string
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
FROM chapter_blocks WHERE chapter_id=$1
`, chID).Scan(&textContent)
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id":       chapterID,
		"body":             body,
		"draft_format":     format,
		"draft_updated_at": updated,
		"draft_version":    version,
		"text_content":     textContent,
	})
}

func (s *Server) patchDraft(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	var in struct {
		Body                 json.RawMessage `json:"body"`
		BodyFormat           string          `json:"body_format"`
		CommitMessage        string          `json:"commit_message"`
		ExpectedDraftVersion *int64          `json:"expected_draft_version"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil || len(in.Body) == 0 {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "body is required")
		return
	}
	if !json.Valid(in.Body) {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "body must be valid JSON")
		return
	}
	if in.BodyFormat == "" {
		in.BodyFormat = "json"
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	defer tx.Rollback(r.Context())
	var curr int64
	err = tx.QueryRow(r.Context(), `
SELECT d.draft_version
FROM chapter_drafts d
JOIN chapters c ON c.id=d.chapter_id
JOIN books b ON b.id=c.book_id
WHERE d.chapter_id=$1 AND c.book_id=$2 AND b.owner_user_id=$3
`, chID, bookID, ownerID).Scan(&curr)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	if in.ExpectedDraftVersion != nil && *in.ExpectedDraftVersion != curr {
		writeError(w, http.StatusConflict, "CHAPTER_DRAFT_CONFLICT", "stale draft version")
		return
	}
	_, _ = tx.Exec(r.Context(), `UPDATE chapter_drafts SET body=$2,draft_format=$3,draft_updated_at=now(),draft_version=draft_version+1 WHERE chapter_id=$1`, chID, in.Body, in.BodyFormat)
	_, _ = tx.Exec(r.Context(), `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`, chID, in.Body, in.BodyFormat, nullIfEmpty(in.CommitMessage), ownerID)
	_, _ = tx.Exec(r.Context(), `UPDATE chapters SET draft_updated_at=now(), draft_revision_count=draft_revision_count+1, updated_at=now() WHERE id=$1`, chID)
	if err := insertOutboxEvent(r.Context(), tx, "chapter.saved", chID, map[string]any{"book_id": bookID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to patch draft")
		return
	}
	s.getDraft(w, r)
}

func (s *Server) listRevisions(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	limit, offset := parseLimitOffset(r)
	rows, err := s.pool.Query(r.Context(), `
SELECT rv.id,rv.chapter_id,rv.created_at,rv.author_user_id,rv.message,octet_length(rv.body::text)
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
JOIN books b ON b.id=c.book_id
WHERE rv.chapter_id=$1 AND c.book_id=$2 AND b.owner_user_id=$3
ORDER BY rv.created_at DESC
LIMIT $4 OFFSET $5
`, chID, bookID, ownerID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to list revisions")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var rid, cid uuid.UUID
		var at time.Time
		var uid *uuid.UUID
		var msg *string
		var n int
		_ = rows.Scan(&rid, &cid, &at, &uid, &msg, &n)
		items = append(items, map[string]any{
			"revision_id":      rid,
			"chapter_id":       cid,
			"created_at":       at,
			"author_user_id":   uid,
			"message":          msg,
			"body_byte_length": n,
		})
	}
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapter_revisions WHERE chapter_id=$1`, chID).Scan(&total)
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

func (s *Server) getRevision(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	revID, ok := parseUUIDParam(w, r, "revision_id")
	if !ok {
		return
	}
	var rid, cid uuid.UUID
	var at time.Time
	var uid *uuid.UUID
	var msg *string
	var body json.RawMessage
	var bodyFormat string
	err := s.pool.QueryRow(r.Context(), `
SELECT rv.id,rv.chapter_id,rv.created_at,rv.author_user_id,rv.message,rv.body,COALESCE(rv.body_format,'plain')
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
JOIN books b ON b.id=c.book_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3 AND b.owner_user_id=$4
`, revID, chID, bookID, ownerID).Scan(&rid, &cid, &at, &uid, &msg, &body, &bodyFormat)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "revision not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to get revision")
		return
	}
	// Extract text_content from revision JSONB body (_text fields)
	var textContent *string
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(t::text, E'\n\n' ORDER BY ordinality)
FROM jsonb_path_query(($1)::jsonb, '$.content[*]._text') WITH ORDINALITY AS x(t, ordinality)
`, body).Scan(&textContent)
	writeJSON(w, http.StatusOK, map[string]any{
		"revision_id":    rid,
		"chapter_id":     cid,
		"created_at":     at,
		"author_user_id": uid,
		"message":        msg,
		"body":           body,
		"body_format":    bodyFormat,
		"text_content":   textContent,
	})
}

func (s *Server) restoreRevision(w http.ResponseWriter, r *http.Request) {
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chID, ok := parseUUIDParam(w, r, "chapter_id")
	if !ok {
		return
	}
	revID, ok := parseUUIDParam(w, r, "revision_id")
	if !ok {
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore revision")
		return
	}
	defer tx.Rollback(r.Context())
	var currentBody json.RawMessage
	var currentFormat string
	if err := tx.QueryRow(r.Context(), `SELECT body,draft_format FROM chapter_drafts WHERE chapter_id=$1`, chID).Scan(&currentBody, &currentFormat); err != nil {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "draft not found")
		return
	}
	var body json.RawMessage
	var bodyFormat string
	err = tx.QueryRow(r.Context(), `
SELECT rv.body,COALESCE(rv.body_format,'plain')
FROM chapter_revisions rv
JOIN chapters c ON c.id=rv.chapter_id
JOIN books b ON b.id=c.book_id
WHERE rv.id=$1 AND rv.chapter_id=$2 AND c.book_id=$3 AND b.owner_user_id=$4
`, revID, chID, bookID, ownerID).Scan(&body, &bodyFormat)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "REVISION_NOT_FOUND", "revision not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "REVISION_NOT_FOUND", "failed to restore revision")
		return
	}
	_, _ = tx.Exec(r.Context(), `INSERT INTO chapter_revisions(chapter_id, body, body_format, message, author_user_id) VALUES($1,$2,$3,$4,$5)`, chID, currentBody, currentFormat, "before restore", ownerID)
	_, _ = tx.Exec(r.Context(), `UPDATE chapter_drafts SET body=$2,draft_format=$3,draft_updated_at=now(),draft_version=draft_version+1 WHERE chapter_id=$1`, chID, body, bodyFormat)
	_, _ = tx.Exec(r.Context(), `UPDATE chapters SET draft_updated_at=now(),draft_revision_count=draft_revision_count+1,updated_at=now() WHERE id=$1`, chID)
	if err := insertOutboxEvent(r.Context(), tx, "chapter.saved", chID, map[string]any{"book_id": bookID}); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore revision")
		return
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to restore revision")
		return
	}
	s.getDraft(w, r)
}

func (s *Server) getBookProjection(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	var id, owner uuid.UUID
	var title, desc, lang, summary, state string
	var chapterCount int
	var createdAt time.Time
	var genreTags []string
	err = s.pool.QueryRow(r.Context(), `
SELECT b.id,b.owner_user_id,b.title,b.description,b.original_language,b.summary,b.lifecycle_state,b.created_at,
  COALESCE((SELECT COUNT(*) FROM chapters c WHERE c.book_id=b.id AND c.lifecycle_state='active'),0),
  b.genre_tags
FROM books b WHERE b.id=$1
`, bookID).Scan(&id, &owner, &title, &desc, &lang, &summary, &state, &createdAt, &chapterCount, &genreTags)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to load projection")
		return
	}
	var hasCover bool
	var coverURL *string
	var ctype string
	var csize int64
	if err := s.pool.QueryRow(r.Context(), `SELECT content_type, byte_size, storage_key FROM book_cover_assets WHERE book_id=$1`, bookID).Scan(&ctype, &csize, &title); err == nil {
		hasCover = true
		u := fmt.Sprintf("/v1/books/%s/cover", bookID)
		coverURL = &u
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":           id,
		"owner_user_id":     owner,
		"title":             title,
		"description":       nullableString(desc),
		"original_language": nullableString(lang),
		"summary_excerpt":   excerpt(summary, 180),
		"has_cover":         hasCover,
		"cover_url":         coverURL,
		"chapter_count":     chapterCount,
		"lifecycle_state":   state,
		"genre_tags":        genreTags,
		"created_at":        createdAt,
	})
}

func (s *Server) getInternalBookChapters(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	var lifecycle string
	if err := s.pool.QueryRow(r.Context(), `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); errors.Is(err, pgx.ErrNoRows) || lifecycle != "active" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	limit, offset := parseLimitOffset(r)
	var total int
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM chapters WHERE book_id=$1 AND lifecycle_state='active'`, bookID).Scan(&total)
	rows, err := s.pool.Query(r.Context(), `
SELECT c.id, c.title, c.sort_order, c.original_language, c.draft_updated_at,
  COALESCE((SELECT octet_length(d.body::text) / 5 FROM chapter_drafts d WHERE d.chapter_id = c.id LIMIT 1), 0) AS word_count_estimate
FROM chapters c
WHERE c.book_id=$1 AND c.lifecycle_state='active'
ORDER BY c.sort_order, c.created_at
LIMIT $2 OFFSET $3
`, bookID, limit, offset)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to list chapters")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var chapterID uuid.UUID
		var title, lang string
		var sortOrder int
		var draftUpdated *time.Time
		var wordCount int
		if err := rows.Scan(&chapterID, &title, &sortOrder, &lang, &draftUpdated, &wordCount); err == nil {
			items = append(items, map[string]any{
				"chapter_id":          chapterID,
				"title":               nullableString(title),
				"sort_order":          sortOrder,
				"original_language":   lang,
				"draft_updated_at":    draftUpdated,
				"word_count_estimate": wordCount,
			})
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

func (s *Server) getInternalBookChapter(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid book id")
		return
	}
	chapterID, err := uuid.Parse(chi.URLParam(r, "chapter_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid chapter id")
		return
	}
	var lifecycle string
	if err := s.pool.QueryRow(r.Context(), `SELECT lifecycle_state FROM books WHERE id=$1`, bookID).Scan(&lifecycle); errors.Is(err, pgx.ErrNoRows) || lifecycle != "active" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}
	var title, lang string
	var body json.RawMessage
	var sortOrder int
	var draftUpdated *time.Time
	err = s.pool.QueryRow(r.Context(), `
SELECT c.title,c.sort_order,c.original_language,c.draft_updated_at,d.body
FROM chapters c
JOIN chapter_drafts d ON d.chapter_id=c.id
WHERE c.id=$1 AND c.book_id=$2 AND c.lifecycle_state='active'
`, chapterID, bookID).Scan(&title, &sortOrder, &lang, &draftUpdated, &body)
	if errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "CHAPTER_NOT_FOUND", "failed to load chapter")
		return
	}
	// Aggregate plain text from chapter_blocks for translation-service consumption
	var textContent *string
	_ = s.pool.QueryRow(r.Context(), `
SELECT string_agg(text_content, E'\n\n' ORDER BY block_index)
FROM chapter_blocks WHERE chapter_id=$1
`, chapterID).Scan(&textContent)
	writeJSON(w, http.StatusOK, map[string]any{
		"chapter_id":        chapterID,
		"title":             nullableString(title),
		"sort_order":        sortOrder,
		"original_language": lang,
		"draft_updated_at":  draftUpdated,
		"body":              body,
		"body_format":       "json",
		"text_content":      textContent,
	})
}

func excerpt(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
