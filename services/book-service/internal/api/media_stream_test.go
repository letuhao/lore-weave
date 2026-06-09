package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

func TestRequireUserIDAllowQuery_streamTokenOnly(t *testing.T) {
	secret := []byte("test-jwt-secret-at-least-32-characters-long")
	uid := uuid.New()
	srv := &Server{secret: secret}

	streamTok := jwt.NewWithClaims(jwt.SigningMethodHS256, streamClaims{
		Type: "stream",
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   uid.String(),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(2 * time.Minute)),
		},
	})
	streamStr, err := streamTok.SignedString(secret)
	if err != nil {
		t.Fatal(err)
	}

	accessTok := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims{
		RegisteredClaims: jwt.RegisteredClaims{Subject: uid.String()},
	})
	accessStr, err := accessTok.SignedString(secret)
	if err != nil {
		t.Fatal(err)
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/books/x/media/object?stream_token="+streamStr, nil)
	got, ok := srv.requireUserIDAllowQuery(req)
	if !ok || got != uid {
		t.Fatalf("stream_token: got %v ok=%v", got, ok)
	}

	reqAccessQuery := httptest.NewRequest(http.MethodGet, "/v1/books/x/media/object?access_token="+accessStr, nil)
	if _, ok := srv.requireUserIDAllowQuery(reqAccessQuery); ok {
		t.Fatal("access_token query must be rejected")
	}

	reqBearer := httptest.NewRequest(http.MethodGet, "/v1/books/x/media/object", nil)
	reqBearer.Header.Set("Authorization", "Bearer "+accessStr)
	got, ok = srv.requireUserIDAllowQuery(reqBearer)
	if !ok || got != uid {
		t.Fatalf("Bearer access JWT still allowed: got %v ok=%v", got, ok)
	}
}
