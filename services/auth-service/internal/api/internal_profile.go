package api

import (
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// Internal full-profile read + update routes (S-SETTINGS / MCP fan-out).
//
// The sibling internalGetUserProfile returns only {display_name, avatar_url} —
// enough for book-service's collaborator panel, but NOT enough for the settings
// MCP tools (settings_get_profile / settings_update_profile), which need the
// full editable profile. Rather than teach provider-registry-service to read
// auth's `users` table directly (cross-service DB access — forbidden: each
// service owns its DB), the settings MCP server (hosted in provider-registry)
// calls these two routes over the internal network.
//
// These are gated by X-Internal-Token (defense in depth): the /internal subtree
// is network-isolated, but a profile WRITE reachable from another service should
// still require the platform service token so a foothold on the internal network
// can't silently rewrite any user's profile. The user_id is a path param — the
// CALLER (the MCP server) is responsible for having scoped it to the envelope's
// caller; auth trusts the internal token + the explicit user_id (it never serves
// these on the public edge).

// requireInternalServiceToken gates a handler on the platform InternalServiceToken
// using a constant-time compare (fail-closed: an empty configured token rejects).
func (s *Server) requireInternalServiceToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		tok := r.Header.Get("X-Internal-Token")
		if s.cfg.InternalServiceToken == "" ||
			subtle.ConstantTimeCompare([]byte(tok), []byte(s.cfg.InternalServiceToken)) != 1 {
			writeErr(w, http.StatusUnauthorized, "AUTH_INTERNAL_UNAUTHORIZED", "invalid internal token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

// internalFullProfile is the full editable profile shape returned to the settings
// MCP server. Mirrors the public GET /v1/account/profile body minus security-only
// fields — display_name, locale, avatar_url, bio, languages, email, email_verified.
type internalFullProfile struct {
	UserID        string   `json:"user_id"`
	Email         string   `json:"email"`
	EmailVerified bool     `json:"email_verified"`
	DisplayName   string   `json:"display_name"`
	Locale        string   `json:"locale"`
	AvatarURL     string   `json:"avatar_url"`
	Bio           string   `json:"bio"`
	Languages     []string `json:"languages"`
	UpdatedAt     string   `json:"updated_at"`
}

// internalGetFullProfile — GET /internal/users/{user_id}/full-profile
// (X-Internal-Token). Returns the full editable profile for the settings MCP
// server's settings_get_profile read.
func (s *Server) internalGetFullProfile(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid user_id")
		return
	}
	out, err := s.loadFullProfile(r, userID)
	if err != nil {
		writeErr(w, http.StatusNotFound, "AUTH_USER_NOT_FOUND", "user not found")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) loadFullProfile(r *http.Request, userID uuid.UUID) (internalFullProfile, error) {
	var email string
	var displayName, locale, avatarURL, bio *string
	var languages []string
	var emailVerified bool
	var updatedAt time.Time
	err := s.pool.QueryRow(r.Context(), `
		SELECT email, display_name, locale, avatar_url, email_verified, updated_at, bio, languages
		FROM users WHERE id = $1`, userID,
	).Scan(&email, &displayName, &locale, &avatarURL, &emailVerified, &updatedAt, &bio, &languages)
	if err != nil {
		return internalFullProfile{}, err
	}
	if languages == nil {
		languages = []string{}
	}
	out := internalFullProfile{
		UserID:        userID.String(),
		Email:         email,
		EmailVerified: emailVerified,
		Languages:     languages,
		UpdatedAt:     updatedAt.UTC().Format(time.RFC3339Nano),
	}
	if displayName != nil {
		out.DisplayName = *displayName
	}
	if locale != nil {
		out.Locale = *locale
	}
	if avatarURL != nil {
		out.AvatarURL = *avatarURL
	}
	if bio != nil {
		out.Bio = *bio
	}
	return out, nil
}

// internalUpdateFullProfile — PATCH /internal/users/{user_id}/full-profile
// (X-Internal-Token). Applies the same validated partial update as the public
// PATCH /v1/account/profile, for the settings MCP server's settings_update_profile
// (Tier-A) write. Only the four prose fields + languages are mutable here; email,
// verification, password, security prefs are NOT settable via this route.
func (s *Server) internalUpdateFullProfile(w http.ResponseWriter, r *http.Request) {
	userID, err := uuid.Parse(chi.URLParam(r, "user_id"))
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid user_id")
		return
	}
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	dn, loc, av, bi, langs, verr := parseProfilePatch(body)
	if verr != "" {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", verr)
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
		UPDATE users SET
		  display_name = COALESCE($2, display_name),
		  locale = COALESCE($3, locale),
		  avatar_url = COALESCE($4, avatar_url),
		  bio = COALESCE($5, bio),
		  languages = COALESCE($6, languages),
		  updated_at = now()
		WHERE id = $1`,
		userID, dn, loc, av, bi, langs)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_INTERNAL", "update failed")
		return
	}
	if tag.RowsAffected() == 0 {
		writeErr(w, http.StatusNotFound, "AUTH_USER_NOT_FOUND", "user not found")
		return
	}
	out, err := s.loadFullProfile(r, userID)
	if err != nil {
		writeErr(w, http.StatusNotFound, "AUTH_USER_NOT_FOUND", "user not found")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

// validAvatarURL gates the avatar_url value to an http(s) URL or empty/clear.
// avatar_url is LLM-writable via the settings MCP profile tool and rendered in
// the UI verbatim, so a `javascript:`/`data:` scheme is a stored-XSS surface —
// only http:// and https:// (and clearing it) are accepted.
func validAvatarURL(s string) bool {
	if s == "" {
		return true // clearing the avatar is allowed
	}
	low := strings.ToLower(s)
	return strings.HasPrefix(low, "http://") || strings.HasPrefix(low, "https://")
}

// parseProfilePatch validates a partial profile body into nullable column values
// (nil = leave unchanged). Shared validation rules with patchProfile: bio ≤1000
// chars, languages ≤20 items / ≤50 chars each. Returns a non-empty error string
// on a validation failure.
func parseProfilePatch(body map[string]any) (dn, loc, av, bi *string, langs []string, verr string) {
	if v, ok := body["display_name"]; ok && v != nil {
		s := strings.TrimSpace(fmt.Sprint(v))
		dn = &s
	}
	if v, ok := body["locale"]; ok && v != nil {
		s := strings.TrimSpace(fmt.Sprint(v))
		loc = &s
	}
	if v, ok := body["avatar_url"]; ok && v != nil {
		s := strings.TrimSpace(fmt.Sprint(v))
		if !validAvatarURL(s) {
			return nil, nil, nil, nil, nil, "avatar_url must be an http(s) URL or empty"
		}
		av = &s
	}
	if v, ok := body["bio"]; ok && v != nil {
		s := fmt.Sprint(v)
		if len(s) > 1000 {
			return nil, nil, nil, nil, nil, "bio must be 1000 characters or fewer"
		}
		bi = &s
	}
	if v, ok := body["languages"]; ok && v != nil {
		arr, ok := v.([]any)
		if !ok {
			return nil, nil, nil, nil, nil, "languages must be an array of strings"
		}
		if len(arr) > 20 {
			return nil, nil, nil, nil, nil, "languages must have 20 items or fewer"
		}
		for _, item := range arr {
			l := strings.TrimSpace(fmt.Sprint(item))
			if l == "" || len(l) > 50 {
				continue
			}
			langs = append(langs, l)
		}
	}
	return dn, loc, av, bi, langs, ""
}
