package api_test

// PG-gated contract test for the E0-5 internal user-lookup-by-email endpoint
// (book-service's collaborators email-invite resolves an email → user via this).
// Gated on AUTH_TEST_PG_URL (skips in the normal job); point it at a throwaway PG.

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/api"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

func byEmailServer(t *testing.T) (*api.Server, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping PG by-email test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := migrate.Up(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return api.NewServer(pool, &config.Config{JWTSecret: "test-secret-at-least-32-characters-long!", InternalServiceToken: "itok"}), pool
}

func getByEmail(t *testing.T, s *api.Server, email string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, "/internal/users/by-email?email="+email, nil)
	rr := httptest.NewRecorder()
	s.Router().ServeHTTP(rr, req)
	return rr
}

func TestInternalGetUserByEmail_PG(t *testing.T) {
	s, pool := byEmailServer(t)
	ctx := context.Background()
	email := "collab-" + uuid.NewString() + "@test.local"
	var id uuid.UUID
	if err := pool.QueryRow(ctx,
		`INSERT INTO users (email, password_hash, display_name) VALUES ($1,'x','Collab Bob') RETURNING id`,
		email).Scan(&id); err != nil {
		t.Fatalf("insert: %v", err)
	}
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM users WHERE id=$1`, id) })

	// found (case-insensitive) → 200 with user_id + display_name.
	rr := getByEmail(t, s, strings.ToUpper(email))
	if rr.Code != http.StatusOK {
		t.Fatalf("found: got %d want 200 (%s)", rr.Code, rr.Body.String())
	}
	var body struct {
		UserID      string `json:"user_id"`
		Email       string `json:"email"`
		DisplayName string `json:"display_name"`
	}
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body.UserID != id.String() || body.DisplayName != "Collab Bob" {
		t.Errorf("got %+v want id=%s name=Collab Bob", body, id)
	}

	// unknown email → 404.
	if rr := getByEmail(t, s, "nobody-"+uuid.NewString()+"@x.co"); rr.Code != http.StatusNotFound {
		t.Errorf("unknown: got %d want 404", rr.Code)
	}

	// deleted account → 404 (can't invite a closed account).
	if _, err := pool.Exec(ctx, `UPDATE users SET account_status='deleted' WHERE id=$1`, id); err != nil {
		t.Fatalf("soft-delete: %v", err)
	}
	if rr := getByEmail(t, s, email); rr.Code != http.StatusNotFound {
		t.Errorf("deleted: got %d want 404", rr.Code)
	}

	// missing email param → 400.
	req := httptest.NewRequest(http.MethodGet, "/internal/users/by-email", nil)
	rr2 := httptest.NewRecorder()
	s.Router().ServeHTTP(rr2, req)
	if rr2.Code != http.StatusBadRequest {
		t.Errorf("missing email: got %d want 400", rr2.Code)
	}
}
