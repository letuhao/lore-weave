package api

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"regexp"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// KG-ML M3 (DD3) — per-(user,book) reader-language preference.
//
// The language a user prefers to READ a book in, kept server-side so it follows
// them across devices (NOT localStorage — CLAUDE.md). Distinct from UI language
// (auth.user_preferences.ui_language). Scope is per-(user,book): a viewer's
// choice can never mutate another user's view or a shared row. Consumed by
// knowledge-service language-aware retrieval (M4) + chat/composition (M7) via the
// internal resolver below.

// langTagRe is a lenient BCP-47-ish guard: a 2-3 letter primary subtag with
// optional script/region/variant subtags (e.g. "vi", "zh", "zh-Hant", "pt-BR").
// We store the tag faithfully rather than collapsing to the primary subtag —
// M4 normalizes both sides when comparing against a passage's source_lang, so a
// reader keeping "zh-Hant" vs "zh-Hans" is preserved here.
var langTagRe = regexp.MustCompile(`^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$`)

const maxReaderLangLen = 35

// getReaderLanguage — GET /v1/books/{book_id}/reader-language
// View-gated (a public/unlisted book counts as viewable so a reader of a shared
// novel can keep a preference). Returns reader_language=null when unset.
func (s *Server) getReaderLanguage(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	// Same gate as favorites: a grant OR a public book. Missing/private/no-access
	// → 404 (uniform, no existence oracle).
	if !s.canViewOrPublic(r.Context(), bookID, userID) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}

	var lang *string
	err := s.pool.QueryRow(r.Context(),
		`SELECT reader_language FROM user_book_prefs WHERE user_id=$1 AND book_id=$2`,
		userID, bookID).Scan(&lang)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		writeError(w, http.StatusInternalServerError, "BOOK_ERROR", "query failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":         bookID.String(),
		"reader_language": lang, // null when unset
	})
}

// setReaderLanguage — PUT /v1/books/{book_id}/reader-language
// View-gated (parity with favorites: per-user data on a book the caller can
// read). Body {"reader_language":"vi"}. An empty/whitespace value CLEARS the
// preference (delete → GET returns null). A malformed tag is 400.
func (s *Server) setReaderLanguage(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	bookID, ok := parseUUIDParam(w, r, "book_id")
	if !ok {
		return
	}
	if !s.canViewOrPublic(r.Context(), bookID, userID) {
		writeError(w, http.StatusNotFound, "BOOK_NOT_FOUND", "book not found")
		return
	}

	bodyBytes, err := io.ReadAll(io.LimitReader(r.Body, 1024))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid body")
		return
	}
	var body struct {
		ReaderLanguage string `json:"reader_language"`
	}
	if err := json.Unmarshal(bodyBytes, &body); err != nil {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid JSON")
		return
	}

	lang := strings.TrimSpace(body.ReaderLanguage)
	if lang == "" {
		// Clear the preference.
		if _, err := s.pool.Exec(r.Context(),
			`DELETE FROM user_book_prefs WHERE user_id=$1 AND book_id=$2`,
			userID, bookID); err != nil {
			writeError(w, http.StatusInternalServerError, "BOOK_ERROR", "failed to clear preference")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"book_id":         bookID.String(),
			"reader_language": nil,
		})
		return
	}

	if len(lang) > maxReaderLangLen || !langTagRe.MatchString(lang) {
		writeError(w, http.StatusBadRequest, "BOOK_VALIDATION_ERROR", "invalid reader_language tag")
		return
	}

	if _, err := s.pool.Exec(r.Context(), `
		INSERT INTO user_book_prefs (user_id, book_id, reader_language)
		VALUES ($1, $2, $3)
		ON CONFLICT (user_id, book_id) DO UPDATE SET
			reader_language = EXCLUDED.reader_language,
			updated_at      = now()
	`, userID, bookID, lang); err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_ERROR", "failed to save preference")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":         bookID.String(),
		"reader_language": lang,
	})
}

// getInternalReaderLanguage — GET /internal/books/{book_id}/reader-language?user_id=
// Cross-service resolver source (M4 retrieval, M7 consumers). Internal-token
// gated; the caller has already authorized the user (mirrors getBookAccess
// taking user_id as a param), so no per-book grant check here. Returns
// reader_language=null when unset. The FALLBACK chain
// (reader-pref → detected query lang → source lang) lives at the CONSUMER where
// the query text + source language are known.
func (s *Server) getInternalReaderLanguage(w http.ResponseWriter, r *http.Request) {
	bookID, err := uuid.Parse(chi.URLParam(r, "book_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_BOOK_ID", "invalid book id")
		return
	}
	userID, err := uuid.Parse(r.URL.Query().Get("user_id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "BAD_USER_ID", "invalid user_id")
		return
	}
	var lang *string
	e := s.pool.QueryRow(r.Context(),
		`SELECT reader_language FROM user_book_prefs WHERE user_id=$1 AND book_id=$2`,
		userID, bookID).Scan(&lang)
	if e != nil && !errors.Is(e, pgx.ErrNoRows) {
		writeError(w, http.StatusServiceUnavailable, "RESOLVE_FAILED", "reader-language resolution failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"book_id":         bookID.String(),
		"user_id":         userID.String(),
		"reader_language": lang, // null when unset
	})
}
