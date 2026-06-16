package adminprincipal_test

// PG-gated contract test for the admin-principal + issuance-audit SQL. The
// handler tests use an in-memory fake, so this is the ONLY place the real
// queries (Lookup JOIN + account_status filter + TEXT[] scan; the 18-column
// INSERT with *uuid/BYTEA/*int64 encoding; the jti-unique index; the reason_len
// CHECK) actually run against Postgres.
//
// Gated on AUTH_TEST_PG_URL so the normal `go test` job skips it; set it to a
// throwaway PG (e.g. infra/foundation-dev) to run, and wire it into the CI
// db-smoke job (tracked alongside D-ADMIN-JWT-KMS-LIVE-SMOKE, 094).

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/auth-service/internal/adminprincipal"
	"github.com/loreweave/auth-service/internal/migrate"
)

func pgPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("AUTH_TEST_PG_URL")
	if dsn == "" {
		t.Skip("AUTH_TEST_PG_URL not set; skipping PG store contract test")
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
	return pool
}

// makeUser inserts a users row and returns its id. Unique email per call.
func makeUser(t *testing.T, pool *pgxpool.Pool) (uuid.UUID, string) {
	t.Helper()
	ctx := context.Background()
	email := "admin-" + uuid.NewString() + "@test.local"
	var id uuid.UUID
	err := pool.QueryRow(ctx,
		`INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id`,
		email, "x").Scan(&id)
	if err != nil {
		t.Fatalf("insert user: %v", err)
	}
	return id, email
}

func TestStore_Lookup_ActivePrincipal(t *testing.T) {
	pool := pgPool(t)
	ctx := context.Background()
	store := adminprincipal.New(pool)

	uid, email := makeUser(t, pool)
	_, err := pool.Exec(ctx,
		`INSERT INTO admin_principals (user_id, role, scopes, active) VALUES ($1,$2,$3,TRUE)`,
		uid, "admin", []string{"admin:read", "admin:destructive"})
	if err != nil {
		t.Fatalf("insert principal: %v", err)
	}

	p, found, err := store.Lookup(ctx, uid)
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if !found {
		t.Fatal("expected principal found")
	}
	if p.Role != "admin" || len(p.Scopes) != 2 || p.Scopes[1] != "admin:destructive" {
		t.Errorf("scopes/role scan wrong: %+v", p)
	}
	if p.Handle != email {
		t.Errorf("handle = %q, want %q", p.Handle, email)
	}
}

func TestStore_Lookup_ExcludesSoftDeletedUser(t *testing.T) {
	pool := pgPool(t)
	ctx := context.Background()
	store := adminprincipal.New(pool)

	uid, _ := makeUser(t, pool)
	if _, err := pool.Exec(ctx,
		`INSERT INTO admin_principals (user_id, role, scopes, active) VALUES ($1,'admin','{}',TRUE)`, uid); err != nil {
		t.Fatalf("insert principal: %v", err)
	}
	// Soft-delete the account (DELETE /account path).
	if _, err := pool.Exec(ctx, `UPDATE users SET account_status='deleted' WHERE id=$1`, uid); err != nil {
		t.Fatalf("soft delete: %v", err)
	}
	_, found, err := store.Lookup(ctx, uid)
	if err != nil {
		t.Fatalf("Lookup: %v", err)
	}
	if found {
		t.Fatal("soft-deleted user must NOT be a valid admin principal")
	}
}

func TestStore_Lookup_NotFound(t *testing.T) {
	pool := pgPool(t)
	store := adminprincipal.New(pool)
	_, found, err := store.Lookup(context.Background(), uuid.New())
	if err != nil {
		t.Fatalf("Lookup error for absent principal (want found=false,nil): %v", err)
	}
	if found {
		t.Fatal("absent user must not be found")
	}
}

func TestStore_InsertAudit_RoundTripAndConstraints(t *testing.T) {
	pool := pgPool(t)
	ctx := context.Background()
	store := adminprincipal.New(pool)

	now := time.Now().UnixNano()
	jti := uuid.New()
	role := "admin"
	reasonLen := 120
	ticket := "INC-1"
	exp := now + int64(time.Hour)
	row := adminprincipal.IssuanceAuditRow{
		AuditID: uuid.New(), ActorID: uuid.New(), ActorHandle: "a@test",
		TokenKind: "break_glass", Outcome: "success", Role: &role,
		Scopes: []string{"admin:destructive"}, BreakGlass: true,
		IncidentTicket: &ticket, ReasonLen: &reasonLen, ReasonHMAC: []byte{1, 2, 3},
		JTI: &jti, IssuedAtNanos: &now, ExpiresAtNanos: &exp, CreatedAtNanos: now,
	}
	if err := store.InsertAudit(ctx, row); err != nil {
		t.Fatalf("InsertAudit: %v", err)
	}

	// Read it back.
	var gotOutcome string
	var gotJTI uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT outcome, jti FROM admin_token_issuance_audit WHERE audit_id=$1`, row.AuditID).
		Scan(&gotOutcome, &gotJTI); err != nil {
		t.Fatalf("read back: %v", err)
	}
	if gotOutcome != "success" || gotJTI != jti {
		t.Errorf("round-trip mismatch: outcome=%s jti=%s", gotOutcome, gotJTI)
	}

	// jti unique index: a second SUCCESS row with the same jti must fail.
	dup := row
	dup.AuditID = uuid.New()
	if err := store.InsertAudit(ctx, dup); err == nil {
		t.Error("expected unique-jti violation on duplicate jti")
	}

	// reason_len CHECK (>=100): a sub-100 value must be rejected.
	bad := row
	bad.AuditID = uuid.New()
	badJTI := uuid.New()
	bad.JTI = &badJTI
	badLen := 50
	bad.ReasonLen = &badLen
	if err := store.InsertAudit(ctx, bad); err == nil {
		t.Error("expected reason_len CHECK violation for len<100")
	}
}
