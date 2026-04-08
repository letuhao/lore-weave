package api

import (
	"encoding/json"
	"io"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// ── Reading Progress ────────────────────────────────────────────────────────

func (s *Server) upsertReadingProgress(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	chapterID := chi.URLParam(r, "chapter_id")
	if chapterID == "" {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "chapter_id required")
		return
	}

	// Validate chapter belongs to book
	var chapterExists bool
	_ = s.pool.QueryRow(r.Context(),
		`SELECT EXISTS(SELECT 1 FROM chapters WHERE id=$1 AND book_id=$2)`,
		chapterID, bookID).Scan(&chapterExists)
	if !chapterExists {
		writeError(w, http.StatusNotFound, "CHAPTER_NOT_FOUND", "chapter not found in this book")
		return
	}

	// Accept both application/json and text/plain (sendBeacon sends text/plain)
	bodyBytes, err := io.ReadAll(io.LimitReader(r.Body, 4096))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid body")
		return
	}

	var body struct {
		TimeSpentMs int64   `json:"time_spent_ms"`
		ScrollDepth float64 `json:"scroll_depth"`
	}
	if err := json.Unmarshal(bodyBytes, &body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON")
		return
	}

	if body.ScrollDepth < 0 {
		body.ScrollDepth = 0
	}
	if body.ScrollDepth > 1 {
		body.ScrollDepth = 1
	}
	if body.TimeSpentMs < 0 {
		body.TimeSpentMs = 0
	}

	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "failed to begin tx")
		return
	}
	defer tx.Rollback(r.Context())

	_, err = tx.Exec(r.Context(), `
		INSERT INTO reading_progress (user_id, book_id, chapter_id, time_spent_ms, scroll_depth, read_count)
		VALUES ($1, $2, $3, $4, $5, 1)
		ON CONFLICT (user_id, book_id, chapter_id) DO UPDATE SET
			time_spent_ms = reading_progress.time_spent_ms + EXCLUDED.time_spent_ms,
			scroll_depth  = GREATEST(reading_progress.scroll_depth, EXCLUDED.scroll_depth),
			read_count    = reading_progress.read_count + 1,
			read_at       = now()
	`, userID, bookID, chapterID, body.TimeSpentMs, body.ScrollDepth)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "failed to save progress")
		return
	}

	chUID, _ := uuid.Parse(chapterID)
	_ = insertOutboxEvent(r.Context(), tx, "reading.progress", chUID, map[string]any{
		"book_id":       bookID.String(),
		"chapter_id":    chapterID,
		"user_id":       userID.String(),
		"time_spent_ms": body.TimeSpentMs,
		"scroll_depth":  body.ScrollDepth,
	})

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "failed to commit progress")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) listReadingProgress(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT chapter_id, read_at, time_spent_ms, scroll_depth, read_count
		FROM reading_progress
		WHERE user_id=$1 AND book_id=$2
		ORDER BY read_at DESC
	`, userID, bookID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var chapterID uuid.UUID
		var readAt time.Time
		var timeSpent int64
		var scrollDepth float64
		var readCount int
		if err := rows.Scan(&chapterID, &readAt, &timeSpent, &scrollDepth, &readCount); err != nil {
			continue
		}
		items = append(items, map[string]any{
			"chapter_id":    chapterID,
			"read_at":       readAt,
			"time_spent_ms": timeSpent,
			"scroll_depth":  scrollDepth,
			"read_count":    readCount,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// ── Book Views ──────────────────────────────────────────────────────────────

func (s *Server) recordBookView(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	// Auth is optional — anonymous views are tracked
	var userID *uuid.UUID
	if uid, ok := s.requireUserID(r); ok {
		userID = &uid
	}

	// Accept sendBeacon (text/plain) or JSON
	bodyBytes, _ := io.ReadAll(io.LimitReader(r.Body, 2048))
	var body struct {
		SessionID string `json:"session_id"`
		Referrer  string `json:"referrer"`
	}
	_ = json.Unmarshal(bodyBytes, &body) // best-effort parse

	// Sanitize referrer
	if len(body.Referrer) > 500 {
		body.Referrer = body.Referrer[:500]
	}
	if len(body.SessionID) > 100 {
		body.SessionID = body.SessionID[:100]
	}

	// Emit outbox event — statistics-service owns view storage and aggregation
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "failed to begin tx")
		return
	}
	defer tx.Rollback(r.Context())

	var userIDStr string
	if userID != nil {
		userIDStr = userID.String()
	}
	_ = insertOutboxEvent(r.Context(), tx, "book.viewed", bookID, map[string]any{
		"book_id":    bookID.String(),
		"user_id":    userIDStr,
		"session_id": body.SessionID,
	})

	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "failed to commit view")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) getBookStats(w http.ResponseWriter, r *http.Request) {
	// Deprecated: book stats now served by statistics-service at /v1/stats/books/{book_id}
	if _, ok := s.requireUserID(r); !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	// Return reading progress data (domain data owned by book-service)
	var avgTimeMs float64
	var avgScrollDepth float64
	var totalReaders int64
	_ = s.pool.QueryRow(r.Context(), `
		SELECT COALESCE(AVG(time_spent_ms), 0),
		       COALESCE(AVG(scroll_depth), 0),
		       COUNT(DISTINCT user_id)
		FROM reading_progress WHERE book_id=$1
	`, bookID).Scan(&avgTimeMs, &avgScrollDepth, &totalReaders)

	writeJSON(w, http.StatusOK, map[string]any{
		"total_readers":    totalReaders,
		"avg_time_ms":      int64(avgTimeMs),
		"avg_scroll_depth": avgScrollDepth,
	})
}

// ── Reading History (all books) ──────────────────────────────────────────────

func (s *Server) getReadingHistory(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}

	rows, err := s.pool.Query(r.Context(), `
		SELECT rp.book_id, rp.chapter_id, rp.read_at, rp.time_spent_ms, rp.scroll_depth, rp.read_count,
		       b.title AS book_title,
		       ch.title AS chapter_title,
		       ch.sort_order
		FROM reading_progress rp
		JOIN books b ON b.id = rp.book_id AND b.lifecycle_state = 'active'
		LEFT JOIN chapters ch ON ch.id = rp.chapter_id
		WHERE rp.user_id = $1
		ORDER BY rp.read_at DESC
		LIMIT 100
	`, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "query failed")
		return
	}
	defer rows.Close()

	items := make([]map[string]any, 0)
	for rows.Next() {
		var bookID, chapterID uuid.UUID
		var readAt time.Time
		var timeSpent int64
		var scrollDepth float64
		var readCount int
		var bookTitle string
		var chapterTitle *string
		var sortOrder *int
		if err := rows.Scan(&bookID, &chapterID, &readAt, &timeSpent, &scrollDepth, &readCount,
			&bookTitle, &chapterTitle, &sortOrder); err != nil {
			continue
		}
		items = append(items, map[string]any{
			"book_id":       bookID,
			"chapter_id":    chapterID,
			"read_at":       readAt,
			"time_spent_ms": timeSpent,
			"scroll_depth":  scrollDepth,
			"read_count":    readCount,
			"book_title":    bookTitle,
			"chapter_title": chapterTitle,
			"sort_order":    sortOrder,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
