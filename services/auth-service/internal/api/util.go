package api

import (
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strings"
	"unicode"

	"github.com/golang-jwt/jwt/v5"
)

var emailPattern = regexp.MustCompile(`^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$`)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, map[string]string{"code": code, "message": msg})
}

func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	const p = "Bearer "
	if len(h) >= len(p) && strings.EqualFold(h[:len(p)], p) {
		return strings.TrimSpace(h[len(p):])
	}
	return ""
}

func validEmail(s string) bool {
	return emailPattern.MatchString(strings.TrimSpace(s))
}

func validPassword(pw string, minLen int) bool {
	if len(pw) < minLen {
		return false
	}
	var letter, digit bool
	for _, r := range pw {
		if unicode.IsLetter(r) {
			letter = true
		}
		if unicode.IsDigit(r) {
			digit = true
		}
	}
	return letter && digit
}

func jwtErrorCode(err error) string {
	if err == nil {
		return ""
	}
	if errors.Is(err, jwt.ErrTokenExpired) {
		return "AUTH_TOKEN_EXPIRED"
	}
	if errors.Is(err, jwt.ErrTokenMalformed) {
		return "AUTH_TOKEN_INVALID"
	}
	return "AUTH_TOKEN_INVALID"
}
