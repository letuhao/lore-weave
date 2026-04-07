package api

import (
	"encoding/json"
	"io"
	"net/http"

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

	_, err = s.pool.Exec(r.Context(), `
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
		var readAt string
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

	_, err := s.pool.Exec(r.Context(), `
		INSERT INTO book_views (book_id, user_id, session_id, referrer)
		VALUES ($1, $2, $3, $4)
	`, bookID, userID, nilIfEmpty(body.SessionID), nilIfEmpty(body.Referrer))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ANALYTICS_ERROR", "failed to record view")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) getBookStats(w http.ResponseWriter, r *http.Request) {
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}

	// Aggregate view stats
	var viewCount int64
	var uniqueReaders int64
	_ = s.pool.QueryRow(r.Context(), `
		SELECT COUNT(*), COUNT(DISTINCT user_id)
		FROM book_views WHERE book_id=$1
	`, bookID).Scan(&viewCount, &uniqueReaders)

	// Aggregate reading stats
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
		"view_count":       viewCount,
		"unique_readers":   uniqueReaders,
		"total_readers":    totalReaders,
		"avg_time_ms":      int64(avgTimeMs),
		"avg_scroll_depth": avgScrollDepth,
	})
}

// nilIfEmpty is already defined in media.go — reused here
