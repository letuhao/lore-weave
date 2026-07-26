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
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/observability"

	"github.com/loreweave/notification-service/internal/category"
	"github.com/loreweave/notification-service/internal/config"
	"github.com/loreweave/notification-service/internal/prefs"
	"github.com/loreweave/notification-service/internal/push"
	"github.com/loreweave/notification-service/internal/redact"
)

type Server struct {
	pool   *pgxpool.Pool
	cfg    *config.Config
	secret []byte
	vapid  push.VAPIDConfig
	sender *push.Sender
}

func NewServer(pool *pgxpool.Pool, cfg *config.Config) *Server {
	vapid := push.VAPIDConfig{
		PublicKey:  cfg.VAPIDPublicKey,
		PrivateKey: cfg.VAPIDPrivateKey,
		Subscriber: cfg.VAPIDSubscriber,
	}
	return &Server{
		pool:   pool,
		cfg:    cfg,
		secret: []byte(cfg.JWTSecret),
		vapid:  vapid,
		sender: push.NewSender(pool, vapid, nil),
	}
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
		// P2·C (opt-out) — per-user category delivery preferences.
		r.Get("/preferences", s.getPreferences)
		r.Put("/preferences", s.setPreference)
		// M5 (D-MOB-4) — Web Push: device registration + per-topic push toggle + the VAPID public
		// key. Owner-scoped from the JWT `sub` (§8-H4) except the VAPID key, which is public by design
		// (its handler skips requireUserID). All under /v1/notifications so they ride the gateway's
		// existing notification proxy — no new gateway route.
		r.Post("/push-subscriptions", s.registerPushSubscription)
		r.Delete("/push-subscriptions", s.deletePushSubscription)
		r.Get("/push-preferences", s.getPushPreferences)
		r.Put("/push-preferences", s.setPushPreference)
		r.Get("/push/vapid-public-key", s.getVAPIDPublicKey)
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

// getPreferences returns EVERY category with its effective enabled state for the
// caller — the user's explicit rows merged over the default-enabled set — so a
// client can render a complete opt-out screen without knowing the category list.
func (s *Server) getPreferences(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_UNAUTHORIZED", "unauthorized")
		return
	}
	explicit, err := prefs.List(r.Context(), s.pool, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "failed to load preferences")
		return
	}
	out := make([]map[string]any, 0, len(category.Allowed))
	for cat := range category.Allowed {
		enabled := true // default deliver
		if v, present := explicit[cat]; present {
			enabled = v
		}
		out = append(out, map[string]any{"category": cat, "enabled": enabled})
	}
	writeJSON(w, http.StatusOK, map[string]any{"preferences": out})
}

// setPreference upserts one category's delivery preference for the caller.
func (s *Server) setPreference(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "NOTIF_UNAUTHORIZED", "unauthorized")
		return
	}
	var body struct {
		Category string `json:"category"`
		Enabled  *bool  `json:"enabled"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.Enabled == nil {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "category and enabled required")
		return
	}
	if !validCategory(body.Category) {
		writeError(w, http.StatusBadRequest, "NOTIF_VALIDATION_ERROR", "invalid category")
		return
	}
	if err := prefs.Set(r.Context(), s.pool, userID, body.Category, *body.Enabled); err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "failed to save preference")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"category": body.Category, "enabled": *body.Enabled})
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
		// DedupKey (P2·C) — optional idempotency key. When set, a repeated create
		// with the same (user_id, dedup_key) is collapsed to the existing row
		// (returned idempotently), so an at-least-once HTTP producer can't double-post.
		DedupKey string `json:"dedup_key"`
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
	// P2·C (opt-out) — the user disabled this category → accept but don't store
	// (idempotent 200, suppressed=true). Fail-OPEN on a lookup error (deliver).
	if suppressed, perr := prefs.Suppressed(r.Context(), s.pool, userID, category); perr == nil && suppressed {
		writeJSON(w, http.StatusOK, map[string]any{"suppressed": true})
		return
	}
	meta, _ := json.Marshal(body.Metadata)
	if body.Metadata == nil {
		meta = []byte("{}")
	}

	var id uuid.UUID
	var createdAt time.Time
	// P2·C — ON CONFLICT DO NOTHING dedups on (user_id, dedup_key); a NULL dedup_key
	// never conflicts (partial index), so the prior behavior is unchanged when the
	// producer supplies no key. On a conflict RETURNING yields no row (ErrNoRows) →
	// re-read the existing row so the create is idempotent (same id/created_at).
	err = s.pool.QueryRow(r.Context(), `
		INSERT INTO notifications (user_id, category, title, body, metadata, message_key, message_params, dedup_key)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (user_id, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
		RETURNING id, created_at`,
		userID, category, body.Title, redact.Body(body.Body), meta,
		nullableText(body.MessageKey), nullableJSONB(body.MessageParams), nullableText(body.DedupKey),
	).Scan(&id, &createdAt)
	// B4 (§8-B4) exactly-once push: a FRESH insert returns a row (err==nil); a dedup collision
	// returns pgx.ErrNoRows (we re-read the existing row, but it was ALREADY pushed on its first
	// insert — so we must NOT push again). Track it before the re-read overwrites `err`.
	freshInsert := err == nil
	if err == pgx.ErrNoRows && strings.TrimSpace(body.DedupKey) != "" {
		if e := s.pool.QueryRow(r.Context(),
			`SELECT id, created_at FROM notifications WHERE user_id=$1 AND dedup_key=$2`,
			userID, body.DedupKey).Scan(&id, &createdAt); e != nil {
			writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "insert failed")
			return
		}
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "insert failed")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id":         id,
		"created_at": createdAt.UTC().Format(time.RFC3339Nano),
	})

	// Fire a content-free push out-of-band, EXACTLY ONCE per stored row (fresh insert only). The
	// gate inside pushForNotification is fail-closed + respects the per-topic opt-out; a push
	// failure never affects the already-committed in-app row.
	if freshInsert {
		go s.pushForNotification(userID, category, body.MessageKey, "/activity", id.String())
	}
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
			DedupKey      string         `json:"dedup_key"`
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
	deduped := 0
	suppressed := 0
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
		// P2·C (opt-out) — skip a category the user disabled (fail-open on error).
		if sup, perr := prefs.Suppressed(ctx, s.pool, userID, cat); perr == nil && sup {
			suppressed++
			continue
		}
		meta, _ := json.Marshal(n.Metadata)
		if n.Metadata == nil {
			meta = []byte("{}")
		}
		// P2·C — dedup on (user_id, dedup_key). A conflict inserts 0 rows; count the
		// row as deduped (neither created nor failed) via RowsAffected, so a redelivered
		// batch reports an honest created count rather than over-counting.
		tag, eerr := s.pool.Exec(ctx, `
			INSERT INTO notifications (user_id, category, title, body, metadata, message_key, message_params, dedup_key)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
			ON CONFLICT (user_id, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING`,
			userID, cat, n.Title, redact.Body(n.Body), meta,
			nullableText(n.MessageKey), nullableJSONB(n.MessageParams), nullableText(n.DedupKey))
		switch {
		case eerr != nil:
			failed++
		case tag.RowsAffected() > 0:
			created++
		default:
			deduped++
		}
	}
	writeJSON(w, http.StatusCreated, map[string]any{"created": created, "failed": failed, "deduped": deduped, "suppressed": suppressed})
}

// ── Public Handlers ───────────────────────────────────────────────────────

// listNotificationsQuery builds the SELECT + args for the notifications feed. Pure (no DB) so
// the keyset/offset/ordering logic is unit-testable. When both `before` and `beforeID` are set it
// engages KEYSET paging — pages by the stable (created_at, id) tuple and omits OFFSET so a row
// arriving between fetches can't shift the page boundary (MB3); otherwise it uses legacy OFFSET.
// Ordering is always created_at DESC, id DESC (the id tiebreaker makes the keyset total-ordered).
// The third return value reports whether keyset was engaged.
func listNotificationsQuery(userID uuid.UUID, category string, unreadOnly bool, before *time.Time, beforeID *uuid.UUID, limit, offset int) (string, []any, bool) {
	keyset := before != nil && beforeID != nil

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
	if keyset {
		// Row-value compare against the DESC ordering: the next (older) page is everything
		// strictly before the cursor tuple.
		query += fmt.Sprintf(` AND (created_at, id) < ($%d, $%d)`, argIdx, argIdx+1)
		args = append(args, *before, *beforeID)
		argIdx += 2
	}

	query += fmt.Sprintf(` ORDER BY created_at DESC, id DESC LIMIT $%d`, argIdx)
	args = append(args, limit)
	argIdx++
	if !keyset {
		query += fmt.Sprintf(` OFFSET $%d`, argIdx)
		args = append(args, offset)
	}
	return query, args, keyset
}

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

	// Keyset cursor (the mobile Activity feed — MB3): `before`/`before_id` page by the stable
	// (created_at, id) tuple so a new notification arriving between fetches never duplicates or
	// drops a row at a page boundary (the flaw of OFFSET paging). Both must be present + valid to
	// engage keyset; otherwise we keep the legacy OFFSET path so existing consumers are unchanged.
	var beforeTime *time.Time
	var beforeID *uuid.UUID
	if bs := r.URL.Query().Get("before"); bs != "" {
		if t, err := time.Parse(time.RFC3339Nano, bs); err == nil {
			beforeTime = &t
		}
	}
	if bid := r.URL.Query().Get("before_id"); bid != "" {
		if id, err := uuid.Parse(bid); err == nil {
			beforeID = &id
		}
	}
	query, args, _ := listNotificationsQuery(userID, category, unreadOnly, beforeTime, beforeID, limit, offset)

	rows, err := s.pool.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "NOTIF_INTERNAL_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0, limit)
	var lastCreatedAt time.Time
	var lastID uuid.UUID
	// rowCount counts rows the DB RETURNED (not just successfully-scanned ones) so a rare per-row
	// scan error can't shrink items below `limit` and falsely null the cursor — which would
	// silently truncate the feed and lose every older notification (cold-review M2).
	rowCount := 0
	for rows.Next() {
		rowCount++
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
		lastCreatedAt = createdAt
		lastID = id
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

	// next_cursor for keyset paging: the tuple of the last (oldest) row, emitted only when the DB
	// returned a FULL page (rowCount == limit → there may be more) AND we have an anchor row to
	// point at. A short page means end-of-feed → null cursor → the client stops paging.
	var nextCursor any
	if rowCount == limit && limit > 0 && len(items) > 0 {
		nextCursor = map[string]any{
			"before":    lastCreatedAt.Format(time.RFC3339Nano),
			"before_id": lastID.String(),
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": total, "next_cursor": nextCursor})
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
