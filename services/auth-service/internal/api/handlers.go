package api

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/authpwd"
	"github.com/loreweave/auth-service/internal/mail"
)

func (s *Server) register(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email       string  `json:"email"`
		Password    string  `json:"password"`
		DisplayName *string `json:"display_name"`
		Locale      *string `json:"locale"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	if !validEmail(body.Email) || !validPassword(body.Password, s.cfg.PasswordMinLength) {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid email or password policy")
		return
	}
	hash, err := authpwd.Hash(body.Password)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "could not hash password")
		return
	}
	ctx := r.Context()
	var uid uuid.UUID
	var createdAt time.Time
	err = s.pool.QueryRow(ctx, `
		INSERT INTO users (email, password_hash, display_name, locale)
		VALUES ($1, $2, $3, $4)
		RETURNING id, created_at`,
		strings.ToLower(strings.TrimSpace(body.Email)), hash, body.DisplayName, body.Locale,
	).Scan(&uid, &createdAt)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			writeErr(w, http.StatusConflict, "AUTH_EMAIL_ALREADY_EXISTS", "email already registered")
			return
		}
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "could not create user")
		return
	}
	_, _ = s.pool.Exec(ctx, `
		INSERT INTO security_preferences (user_id) VALUES ($1)
		ON CONFLICT (user_id) DO NOTHING`, uid)

	emailNorm := strings.ToLower(strings.TrimSpace(body.Email))
	if s.cfg.SMTPHost != "" {
		token, err := s.insertVerificationTicket(ctx, uid)
		if err != nil {
			log.Printf("register: verification ticket: %v", err)
		} else {
			subject := "Verify your LoreWeave email"
			bodyText := verifyEmailPlainBody(token, s.cfg.PublicAppURL)
			if err := s.smtpSend(emailNorm, subject, bodyText); err != nil {
				log.Printf("register: verify email smtp: %v", err)
			}
			if s.cfg.DevLogEmailTokens {
				fmt.Printf("[dev email] verify token for user %s (%s): %s\n", uid.String(), emailNorm, token)
			}
		}
	}

	verificationRequired := true
	writeJSON(w, http.StatusCreated, map[string]any{
		"user_id":               uid.String(),
		"email":                 strings.ToLower(strings.TrimSpace(body.Email)),
		"email_verified":        false,
		"created_at":            createdAt.UTC().Format(time.RFC3339Nano),
		"verification_required": verificationRequired,
	})
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	ctx := r.Context()
	var uid uuid.UUID
	var email string
	var hash string
	var displayName *string
	var emailVerified bool
	err := s.pool.QueryRow(ctx, `
		SELECT id, email, password_hash, display_name, email_verified FROM users WHERE lower(email) = lower($1)`,
		strings.TrimSpace(body.Email),
	).Scan(&uid, &email, &hash, &displayName, &emailVerified)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			writeErr(w, http.StatusUnauthorized, "AUTH_INVALID_CREDENTIALS", "invalid email or password")
			return
		}
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "lookup failed")
		return
	}
	ok, err := authpwd.Verify(body.Password, hash)
	if err != nil || !ok {
		writeErr(w, http.StatusUnauthorized, "AUTH_INVALID_CREDENTIALS", "invalid email or password")
		return
	}
	if err := s.issueSessionAndTokens(w, ctx, uid, email, displayName, emailVerified); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "session error")
		return
	}
}

func (s *Server) issueSessionAndTokens(w http.ResponseWriter, ctx context.Context, uid uuid.UUID, email string, displayName *string, emailVerified bool) error {
	refreshRaw := make([]byte, 32)
	if _, err := rand.Read(refreshRaw); err != nil {
		return err
	}
	refreshToken := base64.RawURLEncoding.EncodeToString(refreshRaw)
	refreshHash := hashOpaque(refreshToken)
	sid := uuid.New()
	expires := time.Now().UTC().Add(s.cfg.RefreshTokenTTL)
	_, err := s.pool.Exec(ctx, `
		INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at)
		VALUES ($1, $2, $3, $4)`, sid, uid, refreshHash, expires)
	if err != nil {
		return err
	}
	access, err := authjwt.SignAccess(s.secret, uid, sid, s.cfg.AccessTokenTTL)
	if err != nil {
		return err
	}
	up := map[string]any{
		"user_id":        uid.String(),
		"email":          email,
		"email_verified": emailVerified,
	}
	if displayName != nil {
		up["display_name"] = *displayName
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token":         access,
		"refresh_token":        refreshToken,
		"expires_in_seconds":   int(s.cfg.AccessTokenTTL.Seconds()),
		"user_profile":         up,
	})
	return nil
}

func hashOpaque(t string) string {
	h := sha256.Sum256([]byte(t))
	return hex.EncodeToString(h[:])
}

func (s *Server) refresh(w http.ResponseWriter, r *http.Request) {
	var body struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.RefreshToken == "" {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "refresh_token required")
		return
	}
	ctx := r.Context()
	h := hashOpaque(body.RefreshToken)
	var sid uuid.UUID
	var uid uuid.UUID
	var expiresAt time.Time
	var revokedAt *time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT id, user_id, expires_at, revoked_at FROM sessions WHERE refresh_token_hash = $1`, h,
	).Scan(&sid, &uid, &expiresAt, &revokedAt)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid refresh token")
		return
	}
	if revokedAt != nil || time.Now().UTC().After(expiresAt) {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_EXPIRED", "refresh expired")
		return
	}
	newRaw := make([]byte, 32)
	if _, err := rand.Read(newRaw); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "rng error")
		return
	}
	newRefresh := base64.RawURLEncoding.EncodeToString(newRaw)
	newHash := hashOpaque(newRefresh)
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "tx error")
		return
	}
	defer tx.Rollback(ctx)
	_, err = tx.Exec(ctx, `UPDATE sessions SET revoked_at = now() WHERE id = $1`, sid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "rotate error")
		return
	}
	newSid := uuid.New()
	expires := time.Now().UTC().Add(s.cfg.RefreshTokenTTL)
	_, err = tx.Exec(ctx, `
		INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at)
		VALUES ($1, $2, $3, $4)`, newSid, uid, newHash, expires)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "rotate error")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "commit error")
		return
	}
	access, err := authjwt.SignAccess(s.secret, uid, newSid, s.cfg.AccessTokenTTL)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "token error")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token":       access,
		"refresh_token":      newRefresh,
		"expires_in_seconds": int(s.cfg.AccessTokenTTL.Seconds()),
	})
}

func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	tok := bearerToken(r)
	if tok == "" {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "missing bearer token")
		return
	}
	claims, err := authjwt.ParseAccess(s.secret, tok)
	if err != nil {
		code := jwtErrorCode(err)
		writeErr(w, http.StatusUnauthorized, code, "invalid access token")
		return
	}
	sid, err := uuid.Parse(claims.SessionID)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid session")
		return
	}
	ctx := r.Context()
	_, err = s.pool.Exec(ctx, `UPDATE sessions SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL`, sid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "logout failed")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) parseAccess(r *http.Request) (*authjwt.AccessClaims, error) {
	tok := bearerToken(r)
	if tok == "" {
		return nil, jwt.ErrTokenMalformed
	}
	return authjwt.ParseAccess(s.secret, tok)
}

func (s *Server) getProfile(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	ctx := r.Context()
	var email string
	var displayName, locale, avatarURL *string
	var emailVerified bool
	var updatedAt time.Time
	err = s.pool.QueryRow(ctx, `
		SELECT email, display_name, locale, avatar_url, email_verified, updated_at
		FROM users WHERE id = $1`, uid,
	).Scan(&email, &displayName, &locale, &avatarURL, &emailVerified, &updatedAt)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "user not found")
		return
	}
	m := map[string]any{
		"user_id":        uid.String(),
		"email":          email,
		"email_verified": emailVerified,
		"updated_at":     updatedAt.UTC().Format(time.RFC3339Nano),
	}
	if displayName != nil {
		m["display_name"] = *displayName
	}
	if locale != nil {
		m["locale"] = *locale
	}
	if avatarURL != nil {
		m["avatar_url"] = *avatarURL
	}
	writeJSON(w, http.StatusOK, m)
}

func (s *Server) patchProfile(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	ctx := r.Context()
	// simple patch: only known keys
	var dn, loc, av *string
	if v, ok := body["display_name"]; ok && v != nil {
		s := fmt.Sprint(v)
		dn = &s
	}
	if v, ok := body["locale"]; ok && v != nil {
		s := fmt.Sprint(v)
		loc = &s
	}
	if v, ok := body["avatar_url"]; ok && v != nil {
		s := fmt.Sprint(v)
		av = &s
	}
	_, err = s.pool.Exec(ctx, `
		UPDATE users SET
		  display_name = COALESCE($2, display_name),
		  locale = COALESCE($3, locale),
		  avatar_url = COALESCE($4, avatar_url),
		  updated_at = now()
		WHERE id = $1`,
		uid, dn, loc, av)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "update failed")
		return
	}
	s.getProfile(w, r)
}

func (s *Server) getSecurityPrefs(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	ctx := r.Context()
	var evr, sa bool
	var prm string
	err = s.pool.QueryRow(ctx, `
		SELECT email_verification_required, password_reset_method, session_alerts_enabled
		FROM security_preferences WHERE user_id = $1`, uid,
	).Scan(&evr, &prm, &sa)
	if err != nil {
		writeErr(w, http.StatusNotFound, "AUTH_VALIDATION_ERROR", "preferences not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"email_verification_required": evr,
		"password_reset_method":       prm,
		"session_alerts_enabled":      sa,
	})
}

func (s *Server) patchSecurityPrefs(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	ctx := r.Context()
	var evr *bool
	var prm *string
	var sa *bool
	if v, ok := body["email_verification_required"]; ok {
		b, ok := v.(bool)
		if ok {
			evr = &b
		}
	}
	if v, ok := body["password_reset_method"]; ok {
		s := fmt.Sprint(v)
		if s == "email_link" || s == "email_code" {
			prm = &s
		}
	}
	if v, ok := body["session_alerts_enabled"]; ok {
		b, ok := v.(bool)
		if ok {
			sa = &b
		}
	}
	_, err = s.pool.Exec(ctx, `
		UPDATE security_preferences SET
		  email_verification_required = COALESCE($2, email_verification_required),
		  password_reset_method = COALESCE($3, password_reset_method),
		  session_alerts_enabled = COALESCE($4, session_alerts_enabled),
		  updated_at = now()
		WHERE user_id = $1`,
		uid, evr, prm, sa)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "update failed")
		return
	}
	s.getSecurityPrefs(w, r)
}

func (s *Server) verifyEmailRequest(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	uid, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid subject")
		return
	}
	ctx := r.Context()
	var email string
	err = s.pool.QueryRow(ctx, `SELECT email FROM users WHERE id = $1`, uid).Scan(&email)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "user lookup failed")
		return
	}
	token, err := s.insertVerificationTicket(ctx, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "ticket error")
		return
	}
	if s.cfg.SMTPHost != "" {
		if err := s.smtpSend(email, "Verify your LoreWeave email", verifyEmailPlainBody(token, s.cfg.PublicAppURL)); err != nil {
			log.Printf("verify email smtp: %v", err)
			writeErr(w, http.StatusBadGateway, "AUTH_EMAIL_SEND_FAILED", "could not send verification email")
			return
		}
	}
	if s.cfg.DevLogEmailTokens {
		fmt.Printf("[dev email] verify token for user %s (%s): %s\n", uid.String(), email, token)
	}
	w.WriteHeader(http.StatusAccepted)
}

func (s *Server) verifyEmailConfirm(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.Token == "" {
		writeErr(w, http.StatusBadRequest, "AUTH_VERIFY_TOKEN_INVALID", "token required")
		return
	}
	ctx := r.Context()
	th := hashOpaque(body.Token)
	var ticketID uuid.UUID
	var uid uuid.UUID
	var exp time.Time
	var consumed *time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT id, user_id, expires_at, consumed_at FROM verification_tickets
		WHERE token_hash = $1 ORDER BY expires_at DESC LIMIT 1`, th,
	).Scan(&ticketID, &uid, &exp, &consumed)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VERIFY_TOKEN_INVALID", "invalid token")
		return
	}
	if consumed != nil || time.Now().UTC().After(exp) {
		writeErr(w, http.StatusBadRequest, "AUTH_VERIFY_TOKEN_INVALID", "token expired")
		return
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "tx error")
		return
	}
	defer tx.Rollback(ctx)
	_, err = tx.Exec(ctx, `UPDATE users SET email_verified = true, updated_at = now() WHERE id = $1`, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "update user")
		return
	}
	_, err = tx.Exec(ctx, `UPDATE verification_tickets SET consumed_at = now() WHERE id = $1`, ticketID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "consume ticket")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "commit")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "verified"})
}

func (s *Server) passwordResetRequest(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Email string `json:"email"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || !validEmail(body.Email) {
		// generic accept
		w.WriteHeader(http.StatusAccepted)
		return
	}
	ctx := r.Context()
	var uid uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT id FROM users WHERE lower(email) = lower($1)`, strings.TrimSpace(body.Email)).Scan(&uid)
	if err != nil {
		w.WriteHeader(http.StatusAccepted)
		return
	}
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		w.WriteHeader(http.StatusAccepted)
		return
	}
	token := base64.RawURLEncoding.EncodeToString(raw)
	th := hashOpaque(token)
	exp := time.Now().UTC().Add(time.Hour)
	_, _ = s.pool.Exec(ctx, `DELETE FROM reset_tickets WHERE user_id = $1`, uid)
	_, err = s.pool.Exec(ctx, `
		INSERT INTO reset_tickets (user_id, token_hash, expires_at) VALUES ($1, $2, $3)`,
		uid, th, exp)
	if err != nil {
		w.WriteHeader(http.StatusAccepted)
		return
	}
	emailNorm := strings.TrimSpace(body.Email)
	if s.cfg.SMTPHost != "" {
		subject := "Reset your LoreWeave password"
		bodyText := passwordResetPlainBody(token, s.cfg.PublicAppURL)
		if err := s.smtpSend(emailNorm, subject, bodyText); err != nil {
			log.Printf("password reset smtp: %v", err)
		}
	}
	if s.cfg.DevLogEmailTokens {
		fmt.Printf("[dev email] password reset for user %s (%s): %s\n", uid.String(), emailNorm, token)
	}
	w.WriteHeader(http.StatusAccepted)
}

func (s *Server) passwordResetConfirm(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Token       string `json:"token"`
		NewPassword string `json:"new_password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_VALIDATION_ERROR", "invalid json")
		return
	}
	if body.Token == "" || !validPassword(body.NewPassword, s.cfg.PasswordMinLength) {
		writeErr(w, http.StatusBadRequest, "AUTH_RESET_TOKEN_INVALID", "invalid payload")
		return
	}
	ctx := r.Context()
	th := hashOpaque(body.Token)
	var ticketID uuid.UUID
	var uid uuid.UUID
	var exp time.Time
	var consumed *time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT id, user_id, expires_at, consumed_at FROM reset_tickets
		WHERE token_hash = $1`, th,
	).Scan(&ticketID, &uid, &exp, &consumed)
	if err != nil {
		writeErr(w, http.StatusBadRequest, "AUTH_RESET_TOKEN_INVALID", "invalid token")
		return
	}
	if consumed != nil || time.Now().UTC().After(exp) {
		writeErr(w, http.StatusBadRequest, "AUTH_RESET_TOKEN_INVALID", "token expired")
		return
	}
	hash, err := authpwd.Hash(body.NewPassword)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "hash error")
		return
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "tx error")
		return
	}
	defer tx.Rollback(ctx)
	_, err = tx.Exec(ctx, `UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1`, uid, hash)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "update password")
		return
	}
	_, err = tx.Exec(ctx, `UPDATE reset_tickets SET consumed_at = now() WHERE id = $1`, ticketID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "consume ticket")
		return
	}
	_, err = tx.Exec(ctx, `UPDATE sessions SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL`, uid)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "revoke sessions")
		return
	}
	if err := tx.Commit(ctx); err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "commit")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "password_updated"})
}

func (s *Server) insertVerificationTicket(ctx context.Context, uid uuid.UUID) (token string, err error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	token = base64.RawURLEncoding.EncodeToString(raw)
	th := hashOpaque(token)
	exp := time.Now().UTC().Add(24 * time.Hour)
	_, err = s.pool.Exec(ctx, `
		INSERT INTO verification_tickets (user_id, token_hash, expires_at) VALUES ($1, $2, $3)`,
		uid, th, exp)
	return token, err
}

func (s *Server) smtpSend(to, subject, body string) error {
	return mail.SendPlain(
		s.cfg.SMTPHost,
		s.cfg.SMTPPort,
		s.cfg.SMTPUser,
		s.cfg.SMTPPassword,
		s.cfg.SMTPFrom,
		to,
		subject,
		body,
	)
}

func verifyEmailPlainBody(token, publicBase string) string {
	var b strings.Builder
	b.WriteString("Your LoreWeave email verification token is:\n\n")
	b.WriteString(token)
	b.WriteString("\n\nPaste it on the Verify page in the app. This token expires in 24 hours.\n")
	if publicBase != "" {
		base := strings.TrimRight(publicBase, "/")
		b.WriteString("\nOpen the app: ")
		b.WriteString(base)
		b.WriteString("/verify\n")
	}
	return b.String()
}

func passwordResetPlainBody(token, publicBase string) string {
	var b strings.Builder
	b.WriteString("Your LoreWeave password reset token is:\n\n")
	b.WriteString(token)
	b.WriteString("\n\nPaste it on the Reset password page. This token expires in one hour.\n")
	if publicBase != "" {
		base := strings.TrimRight(publicBase, "/")
		b.WriteString("\nOpen the app: ")
		b.WriteString(base)
		b.WriteString("/reset\n")
	}
	return b.String()
}
