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
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

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

type accessClaims struct {
	jwt.RegisteredClaims
}

func (s *Server) requireUserID(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	tok, err := jwt.ParseWithClaims(strings.TrimPrefix(auth, "Bearer "), &accessClaims{}, func(t *jwt.Token) (any, error) {
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

// ── Internal Handlers ─────────────────────────────────────────────────────

func (s *Server) createNotification(w http.ResponseWriter, r *http.Request) {
	var body struct {
		UserID   string         `json:"user_id"`
		Category string         `json:"category"`
		Title    string         `json:"title"`
		Body     string         `json:"body"`
		Metadata map[string]any `json:"metadata"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid json")
		return
	}
	userID, err := uuid.Parse(body.UserID)
	if err != nil || body.Title == "" {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "user_id and title required")
		return
	}
	category := body.Category
	if category == "" {
		category = "system"
	}
	meta, _ := json.Marshal(body.Metadata)
	if body.Metadata == nil {
		meta = []byte("{}")
	}

	var id uuid.UUID
	var createdAt time.Time
	err = s.pool.QueryRow(r.Context(), `
		INSERT INTO notifications (user_id, category, title, body, metadata)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, created_at`,
		userID, category, body.Title, body.Body, meta,
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
			UserID   string         `json:"user_id"`
			Category string         `json:"category"`
			Title    string         `json:"title"`
			Body     string         `json:"body"`
			Metadata map[string]any `json:"metadata"`
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
	for _, n := range body.Notifications {
		userID, err := uuid.Parse(n.UserID)
		if err != nil || n.Title == "" {
			continue
		}
		cat := n.Category
		if cat == "" {
			cat = "system"
		}
		meta, _ := json.Marshal(n.Metadata)
		if n.Metadata == nil {
			meta = []byte("{}")
		}
		_, err = s.pool.Exec(ctx, `
			INSERT INTO notifications (user_id, category, title, body, metadata)
			VALUES ($1, $2, $3, $4, $5)`,
			userID, cat, n.Title, n.Body, meta)
		if err == nil {
			created++
		}
	}
	writeJSON(w, http.StatusCreated, map[string]any{"created": created})
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

	query := `SELECT id, category, title, body, metadata, read_at, created_at
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

	items := make([]map[string]any, 0)
	for rows.Next() {
		var id uuid.UUID
		var cat, title string
		var body *string
		var metadata json.RawMessage
		var readAt *time.Time
		var createdAt time.Time
		if err := rows.Scan(&id, &cat, &title, &body, &metadata, &readAt, &createdAt); err != nil {
			continue
		}
		m := map[string]any{
			"id":         id,
			"category":   cat,
			"title":      title,
			"metadata":   json.RawMessage(metadata),
			"read":       readAt != nil,
			"created_at": createdAt.UTC().Format(time.RFC3339Nano),
		}
		if body != nil {
			m["body"] = *body
		}
		items = append(items, m)
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
