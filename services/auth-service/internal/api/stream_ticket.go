package api

import (
	"net/http"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/auth-service/internal/authjwt"
)

func (s *Server) issueStreamTicket(w http.ResponseWriter, r *http.Request) {
	claims, err := s.parseAccess(r)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, jwtErrorCode(err), "invalid access token")
		return
	}
	userID, err := uuid.Parse(claims.Subject)
	if err != nil {
		writeErr(w, http.StatusUnauthorized, "AUTH_TOKEN_INVALID", "invalid access token")
		return
	}
	ttl := time.Duration(s.cfg.StreamTicketTTLSeconds) * time.Second
	if ttl <= 0 {
		ttl = 120 * time.Second
	}
	token, err := authjwt.SignStream(s.secret, userID, ttl)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "AUTH_VALIDATION_ERROR", "could not issue stream ticket")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"stream_token":       token,
		"expires_in_seconds": int(ttl.Seconds()),
	})
}
