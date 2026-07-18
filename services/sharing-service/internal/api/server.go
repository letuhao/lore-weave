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
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/observability"

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

// Phase 6c — traced transport so outbound calls carry a W3C traceparent + emit a CLIENT span.
var internalClient = &http.Client{Timeout: 10 * time.Second, Transport: observability.HTTPTransport(nil)}

func (s *Server) internalGet(url string) (*http.Response, error) {
	do := func() (*http.Response, error) {
		req, err := http.NewRequest(http.MethodGet, url, nil)
		if err != nil {
			return nil, err
		}
		if s.cfg.InternalServiceToken != "" {
			req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
		}
		return internalClient.Do(req)
	}
	res, err := do()
	if err != nil {
		time.Sleep(500 * time.Millisecond)
		return do()
	}
	return res, nil
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	// Phase 6c — OpenTelemetry SERVER span. Before Recoverer so the span
	// survives (and is marked 500) when a handler panics.
	r.Use(observability.ChiMiddleware())
	r.Use(middleware.Recoverer)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.pool != nil {
			if err := s.pool.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.pool == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.pool.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	r.Route("/internal/sharing", func(r chi.Router) {
		r.Use(s.requireInternalToken)
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
		r.Get("/unlisted/{access_token}/lore", s.getUnlistedLore) // W11-M3 public canon-only lore
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

func (s *Server) requireUserID(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	tokenStr := strings.TrimPrefix(auth, "Bearer ")
	claims, err := platformjwt.Verify(tokenStr, s.secret)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := claims.UserID()
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

type bookProjection struct {
	BookID           uuid.UUID `json:"book_id"`
	OwnerUserID      uuid.UUID `json:"owner_user_id"`
	// Kind rides the projection (WS-1.2 / D16). A diary is private-forever: no
	// sharing policy may ever expose it. Empty on a legacy book-service that
	// predates the field — treated as non-diary (normal book).
	Kind             string    `json:"kind"`
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

// diaryVisibilityGuard blocks any attempt to make a diary book non-private
// (P-4 egress / D16). A diary is private-forever; only 'private' (or an empty
// no-op patch) is ever allowed. Returns (0,"") to allow; a non-zero HTTP code
// to refuse. FAIL-CLOSED: if book-service can't confirm the kind, a non-private
// set is refused rather than risk exposing a diary during an outage. Pool-free
// (only reads the projection), so it is unit-testable without a DB.
func (s *Server) diaryVisibilityGuard(bookID uuid.UUID, visibility string) (code int, msg string) {
	if visibility == "" || visibility == "private" {
		return 0, ""
	}
	proj, status := s.fetchBookProjection(bookID)
	if status != http.StatusOK {
		return http.StatusBadGateway, "cannot verify book privacy"
	}
	if proj.Kind == "diary" {
		return http.StatusForbidden, "a diary cannot be shared"
	}
	return 0, ""
}

func (s *Server) fetchBookProjection(bookID uuid.UUID) (*bookProjection, int) {
	res, err := s.internalGet(fmt.Sprintf("%s/internal/books/%s/projection", strings.TrimRight(s.cfg.BookServiceInternalURL, "/"), bookID))
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
	// P-4 egress (D16): a diary can never be made shareable. Ownership is checked
	// above, so only the owner ever reaches this — no diary oracle to a stranger.
	if code, msg := s.diaryVisibilityGuard(bookID, in.Visibility); code != 0 {
		writeError(w, code, "SHARE_POLICY_DIARY_FORBIDDEN", msg)
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

func (s *Server) fetchBookChapterInternal(bookID, chapterID uuid.UUID) (map[string]any, int) {
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

// unlistedLoreBeforeChapterIndex parses the self-declared `?before_chapter=N` into
// the glossary `before_chapter_index` + a `valid` flag. Glossary is EXCLUSIVE
// (`chapter_index < before_chapter_index`), so to INCLUDE the reader's current
// chapter N we return N+1.
//   - ABSENT ("") → (-1, true): deliberate "no window" = the whole published canon.
//     (The unlisted link already exposes the full book TEXT, so its derived canon is
//     no greater exposure; the `windowed:false` response flag lets the UI prompt for
//     a position. The cutoff is an opt-in reader courtesy, not a security boundary.)
//   - VALID N≥0 → (N+1, true).
//   - MALFORMED / negative → (0, FALSE): a reader who TRIED to scope but fat-fingered
//     it must NOT silently get the whole (spoiler-laden) canon — the caller 400s.
func unlistedLoreBeforeChapterIndex(param string) (int, bool) {
	if param == "" {
		return -1, true
	}
	n, err := strconv.Atoi(param)
	if err != nil || n < 0 {
		return 0, false // present-but-invalid → fail closed at the handler
	}
	return n + 1, true
}

// fetchCanonLoreInternal pulls the book's CANON-ONLY glossary cast from glossary-
// service, windowed to beforeChapterIndex (-1 = whole book, no window). The
// canon-only guarantee is EXPLICIT here (`status=active`) — this is a public,
// unauthenticated surface, so it must NOT rely on the implicit "drafts have no
// chapter links" behaviour the grant-gated reader facade leans on. glossary_entities
// defaults status='draft'; WS-4C AI-suggested captures are 'draft'; only a
// human-promoted entity is 'active'. `alive=true` + `min_frequency>=1` are
// belt-and-suspenders (and glossary now also drops soft-deleted rows).
//
// The known-entities endpoint returns a BARE JSON ARRAY of entity objects
// (extraction_handler.go getKnownEntities), NOT an {entities,count} object — decode
// accordingly (a prior object-decode silently failed → the route always returned
// empty). Returns the entity slice; the handler wraps it.
func (s *Server) fetchCanonLoreInternal(bookID uuid.UUID, beforeChapterIndex, limit int) ([]map[string]any, int) {
	base := strings.TrimRight(s.cfg.GlossaryServiceInternalURL, "/")
	url := fmt.Sprintf(
		"%s/internal/books/%s/known-entities?alive=true&status=active&min_frequency=1&recency_window=0&limit=%d&before_chapter_index=%d",
		base, bookID, limit, beforeChapterIndex,
	)
	res, err := s.internalGet(url)
	if err != nil {
		return nil, http.StatusBadGateway
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, res.StatusCode
	}
	var out []map[string]any
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		return nil, http.StatusBadGateway
	}
	return out, http.StatusOK
}

// getUnlistedLore (W11-M3) — a public, spoiler-windowed, CANON-ONLY view of an
// unlisted book's glossary cast. Anonymous (no auth); reached only via the secret
// unlisted access token, so a bad/non-unlisted token → 404 (anti-oracle, same as
// the chapter reads). The spoiler cutoff is SELF-DECLARED (`?before_chapter=N`, the
// reader's own "I've read up to here") because an anonymous reader has no server
// reading position.
func (s *Server) getUnlistedLore(w http.ResponseWriter, r *http.Request) {
	tokenValue := chi.URLParam(r, "access_token")
	bookID, ok := s.resolveUnlistedBookID(r.Context(), tokenValue)
	if !ok {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
		return
	}
	// Confirm the book is live (mirror getUnlistedBook) so a trashed book's lore
	// isn't served through a still-valid token.
	p, status := s.fetchBookProjection(bookID)
	if status != http.StatusOK || p.LifecycleState != "active" {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "not found")
		return
	}

	beforeChapterIndex, cutoffOK := unlistedLoreBeforeChapterIndex(r.URL.Query().Get("before_chapter"))
	if !cutoffOK {
		// A present-but-malformed cutoff fails CLOSED: never fall through to whole
		// canon for a reader who intended a spoiler window but mistyped it.
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "before_chapter must be a non-negative integer")
		return
	}
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 200 {
			limit = n
		}
	}

	ents, st := s.fetchCanonLoreInternal(bookID, beforeChapterIndex, limit)
	if st != http.StatusOK {
		// Any glossary failure → an empty cast, never a 5xx that leaks structure.
		ents = []map[string]any{}
	}
	if ents == nil {
		ents = []map[string]any{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"entities": ents,
		"book_id":  bookID,
		"windowed": beforeChapterIndex >= 0, // false ⇒ whole canon; UI should prompt for a position
	})
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
