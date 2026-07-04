package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/observability"

	"github.com/loreweave/notification-service/internal/category"
	"github.com/loreweave/notification-service/internal/config"
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
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	// Internal (service-to-service)
	r.Route("/internal/notifications", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Post("/", s.createNotification)
		r.Post("/batch", s.createNotificationBatch)
	})

	// Public API (JWT required)
	r.Route("/v1/notifications", func(r chi.Router) {
		r.Get("/", s.listNotifications)
		r.Get("/unread-count", s.unreadCount)
		r.Post("/read-all", s.markAllRead)
		r.Patch("/{id}/read", s.markRead)
		r.Delete("/{id}", s.deleteNotification)
	})

	return r
}

// ── Middleware ─────────────────────────────────────────────────────────────

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "invalid internal token"})
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) requireUserID(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	claims, err := platformjwt.Verify(strings.TrimPrefix(auth, "Bearer "), s.secret)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := claims.UserID()
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// ── Internal Handlers ─────────────────────────────────────────────────────

func (s *Server) createNotification(w http.ResponseWriter, r *http.Request) {
	var body struct {
		UserID   string         `json:"user_id"`
		Category string         `json:"category"`
		Title    string         `json:"title"`
		Body     string         `json:"body"`
		Metadata map[string]any `json:"metadata"`
		// D-NOTIF-I18N (NOTIF-1): optional i18n substrate. A producer may
		// supply a stable message_key + interpolation params so a locale-aware
		// FE renders per-locale; title/body remain the rendered fallback. Both
		// are optional — omitted ⇒ NULL columns, text fallback only.
		MessageKey    string         `json:"message_key"`
		MessageParams map[string]any `json:"message_params"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid json")
		return
	}
	userID, err := uuid.Parse(body.UserID)
	if err != nil || strings.TrimSpace(body.Title) == "" {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "user_id and title required")
		return
	}
	if len(body.Title) > 500 {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "title exceeds 500 chars")
		return
	}
	if len(body.Body) > 5000 {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "body exceeds 5000 chars")
		return
	}
	category := body.Category
	if category == "" {
		category = "system"
	}
	if !validCategory(category) {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid category")
		return
	}
	meta, _ := json.Marshal(body.Metadata)
	if body.Metadata == nil {
		meta = []byte("{}")
	}

	var id uuid.UUID
	var createdAt time.Time
	err = s.pool.QueryRow(r.Context(), `
		INSERT INTO notifications (user_id, category, title, body, metadata, message_key, message_params)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		RETURNING id, created_at`,
		userID, category, body.Title, body.Body, meta,
		nullableText(body.MessageKey), nullableJSONB(body.MessageParams),
	).Scan(&id, &createdAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "insert failed")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id":         id,
		"created_at": createdAt.UTC().Format(time.RFC3339Nano),
	})
}

func (s *Server) createNotificationBatch(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Notifications []struct {
			UserID        string         `json:"user_id"`
			Category      string         `json:"category"`
			Title         string         `json:"title"`
			Body          string         `json:"body"`
			Metadata      map[string]any `json:"metadata"`
			MessageKey    string         `json:"message_key"`
			MessageParams map[string]any `json:"message_params"`
		} `json:"notifications"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid json")
		return
	}
	if len(body.Notifications) == 0 || len(body.Notifications) > 100 {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "1-100 notifications required")
		return
	}

	ctx := r.Context()
	created := 0
	failed := 0
	for _, n := range body.Notifications {
		userID, err := uuid.Parse(n.UserID)
		if err != nil || strings.TrimSpace(n.Title) == "" || len(n.Title) > 500 {
			failed++
			continue
		}
		cat := n.Category
		if cat == "" {
			cat = "system"
		}
		if !validCategory(cat) {
			failed++
			continue
		}
		meta, _ := json.Marshal(n.Metadata)
		if n.Metadata == nil {
			meta = []byte("{}")
		}
		_, err = s.pool.Exec(ctx, `
			INSERT INTO notifications (user_id, category, title, body, metadata, message_key, message_params)
			VALUES ($1, $2, $3, $4, $5, $6, $7)`,
			userID, cat, n.Title, n.Body, meta,
			nullableText(n.MessageKey), nullableJSONB(n.MessageParams))
		if err == nil {
			created++
		} else {
			failed++
		}
	}
	writeJSON(w, http.StatusCreated, map[string]any{"created": created, "failed": failed})
}

// ── Public Handlers ───────────────────────────────────────────────────────

func (s *Server) listNotifications(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}

	limit := queryInt(r, "limit", 20)
	offset := queryInt(r, "offset", 0)
	if limit > 100 {
		limit = 100
	}
	category := r.URL.Query().Get("category")
	unreadOnly := r.URL.Query().Get("unread") == "true"

	query := `SELECT id, category, title, body, metadata, message_key, message_params, read_at, created_at
		FROM notifications WHERE user_id = $1`
	args := []any{userID}
	argIdx := 2

	if category != "" {
		query += fmt.Sprintf(` AND category = $%d`, argIdx)
		args = append(args, category)
		argIdx++
	}
	if unreadOnly {
		query += ` AND read_at IS NULL`
	}

	query += fmt.Sprintf(` ORDER BY created_at DESC LIMIT $%d OFFSET $%d`, argIdx, argIdx+1)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0, limit)
	for rows.Next() {
		var id uuid.UUID
		var cat, title string
		var body *string
		var metadata json.RawMessage
		var messageKey *string
		var messageParams json.RawMessage
		var readAt *time.Time
		var createdAt time.Time
		if err := rows.Scan(&id, &cat, &title, &body, &metadata, &messageKey, &messageParams, &readAt, &createdAt); err != nil {
			continue
		}
		items = append(items, serializeNotification(id, cat, title, body, metadata, messageKey, messageParams, readAt, createdAt))
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "row iteration failed")
		return
	}

	// Total count
	countQuery := `SELECT COUNT(*) FROM notifications WHERE user_id = $1`
	countArgs := []any{userID}
	countIdx := 2
	if category != "" {
		countQuery += fmt.Sprintf(` AND category = $%d`, countIdx)
		countArgs = append(countArgs, category)
		countIdx++
	}
	if unreadOnly {
		countQuery += ` AND read_at IS NULL`
	}
	var total int64
	_ = s.pool.QueryRow(r.Context(), countQuery, countArgs...).Scan(&total)

	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total})
}

func (s *Server) unreadCount(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	var count int64
	_ = s.pool.QueryRow(r.Context(), `SELECT COUNT(*) FROM notifications WHERE user_id=$1 AND read_at IS NULL`, userID).Scan(&count)
	writeJSON(w, http.StatusOK, map[string]any{"count": count})
}

func (s *Server) markRead(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid id")
		return
	}
	tag, err := s.pool.Exec(r.Context(), `UPDATE notifications SET read_at = now() WHERE id=$1 AND user_id=$2 AND read_at IS NULL`, id, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "NOTIF_NOT_FOUND", "notification not found or already read")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) markAllRead(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	tag, _ := s.pool.Exec(r.Context(), `UPDATE notifications SET read_at = now() WHERE user_id=$1 AND read_at IS NULL`, userID)
	writeJSON(w, http.StatusOK, map[string]any{"marked": tag.RowsAffected()})
}

func (s *Server) deleteNotification(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_AUTH_ERROR", "authentication required")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid id")
		return
	}
	tag, _ := s.pool.Exec(r.Context(), `DELETE FROM notifications WHERE id=$1 AND user_id=$2`, id, userID)
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "NOTIF_NOT_FOUND", "notification not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ── Helpers ───────────────────────────────────────────────────────────────

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

// validCategory delegates to the single source-of-truth enum in the
// category package so the HTTP ingress path and the AMQP consumer path
// validate against the exact same set (audit P0-4 / NOTIF-2).
func validCategory(c string) bool {
	return category.Valid(c)
}

// serializeNotification builds the JSON row shape the GET/list endpoint
// returns. Pure (no DB) so the serialization contract — including the
// D-NOTIF-I18N message_key/message_params fields — is unit-testable without
// a broker or Postgres. message_key (*string) and message_params
// (json.RawMessage) are ALWAYS present in the map; both marshal to JSON
// `null` when nil (legacy row or a producer that supplied no key), so a
// locale-aware FE keys off them while any other client falls back to
// title/body. body stays omitted-when-null to preserve the prior contract.
func serializeNotification(
	id uuid.UUID,
	category, title string,
	body *string,
	metadata json.RawMessage,
	messageKey *string,
	messageParams json.RawMessage,
	readAt *time.Time,
	createdAt time.Time,
) map[string]any {
	m := map[string]any{
		"id":             id,
		"category":       category,
		"title":          title,
		"metadata":       json.RawMessage(metadata),
		"read":           readAt != nil,
		"created_at":     createdAt.UTC().Format(time.RFC3339Nano),
		"message_key":    messageKey,    // *string → JSON string or null
		"message_params": messageParams, // json.RawMessage → JSON object or null
	}
	if body != nil {
		m["body"] = *body
	}
	return m
}

// nullableText maps an empty string to a SQL NULL (nil) so an omitted
// message_key stores as NULL rather than an empty string — keeping the
// "no i18n key ⇒ NULL ⇒ text fallback" contract clean. (D-NOTIF-I18N)
func nullableText(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// nullableJSONB maps an omitted/empty params map to a SQL NULL (nil) rather
// than an empty '{}' — so a reader can distinguish "no params supplied" from
// "params present but empty". A present map is marshalled to JSONB bytes
// (Go json is UTF-8; ML-5 — no \uXXXX inflation on any prose param). (D-NOTIF-I18N)
func nullableJSONB(m map[string]any) any {
	if len(m) == 0 {
		return nil
	}
	b, err := json.Marshal(m)
	if err != nil {
		return nil
	}
	return b
}

func queryInt(r *http.Request, key string, def int) int {
	v := r.URL.Query().Get(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < 0 {
		return def
	}
	return n
}
