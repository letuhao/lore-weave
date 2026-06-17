package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/config"
	"github.com/loreweave/glossary-service/internal/migrate"
)

// ── token unit tests (no DB) — INV-9 / H8 ────────────────────────────────────

func TestSchemaToken_RoundTrip(t *testing.T) {
	secret := "test_jwt_secret_at_least_32_characters_long"
	u, b := uuid.New(), uuid.New()
	params := json.RawMessage(`{"code":"qa_new_kind","name":"Power System"}`)
	now := time.Unix(1_900_000_000, 0)
	tok := mintSchemaToken(secret, u, b, schemaOpKind, params, now)
	if tok == "" {
		t.Fatal("mint returned empty token")
	}
	claims, err := verifySchemaToken(secret, tok, now.Add(time.Minute))
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if claims.UserID != u || claims.BookID != b || claims.Op != schemaOpKind {
		t.Errorf("claims mismatch: %+v", claims)
	}
	if string(claims.Params) != string(params) {
		t.Errorf("params mismatch: %s", claims.Params)
	}
}

func TestSchemaToken_Expired(t *testing.T) {
	secret := "test_jwt_secret_at_least_32_characters_long"
	now := time.Unix(1_900_000_000, 0)
	tok := mintSchemaToken(secret, uuid.New(), uuid.New(), schemaOpKind, json.RawMessage(`{}`), now)
	if _, err := verifySchemaToken(secret, tok, now.Add(schemaTokenTTL+time.Second)); !errors.Is(err, ErrSchemaTokenExpired) {
		t.Fatalf("want ErrSchemaTokenExpired, got %v", err)
	}
}

func TestSchemaToken_TamperedSignatureRejected(t *testing.T) {
	secret := "test_jwt_secret_at_least_32_characters_long"
	now := time.Unix(1_900_000_000, 0)
	tok := mintSchemaToken(secret, uuid.New(), uuid.New(), schemaOpKind, json.RawMessage(`{}`), now)
	// flip the last char of the signature segment
	bad := tok[:len(tok)-1] + map[bool]string{true: "A", false: "B"}[tok[len(tok)-1] != 'A']
	if _, err := verifySchemaToken(secret, bad, now.Add(time.Minute)); !errors.Is(err, ErrSchemaTokenInvalid) {
		t.Fatalf("tampered sig must be invalid, got %v", err)
	}
	// a different secret must also reject (key binding)
	if _, err := verifySchemaToken("another_secret_at_least_32_characters_xx", tok, now.Add(time.Minute)); !errors.Is(err, ErrSchemaTokenInvalid) {
		t.Fatalf("wrong-secret must be invalid, got %v", err)
	}
}

func TestSchemaToken_FailClosedAndMalformed(t *testing.T) {
	now := time.Unix(1_900_000_000, 0)
	if mintSchemaToken("", uuid.New(), uuid.New(), schemaOpKind, json.RawMessage(`{}`), now) != "" {
		t.Error("empty secret must mint no token (fail closed)")
	}
	secret := "test_jwt_secret_at_least_32_characters_long"
	for _, bad := range []string{"", "nodot", "a.b.c", ".", "x."} {
		if _, err := verifySchemaToken(secret, bad, now); err == nil {
			t.Errorf("malformed token %q must error", bad)
		}
	}
}

// ── propose tool ownership (no DB) ───────────────────────────────────────────

func TestToolProposeNewKind_MissingIdentity(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolProposeNewKind(context.Background(), nil,
		proposeKindToolIn{BookID: uuid.NewString(), Code: "x", Name: "X"}); err == nil {
		t.Fatal("want missing-identity error")
	}
}

func TestToolProposeNewAttribute_RejectsBadFieldType(t *testing.T) {
	// field_type is validated at propose time (before ownership/DB) so a bogus
	// LLM-supplied type never reaches the create.
	s := &Server{}
	_, _, err := s.toolProposeNewAttribute(ctxWithUser(uuid.New()), nil,
		proposeAttrToolIn{BookID: uuid.NewString(), KindCode: "character", Code: "x", Name: "X", FieldType: "garbage"})
	if err == nil || !strings.Contains(err.Error(), "invalid field_type") {
		t.Fatalf("bad field_type must be rejected at propose, got %v", err)
	}
}

func TestToolProposeNewKind_OwnershipDenied(t *testing.T) {
	ts := httptest.NewServer(projection(uuid.New(), uuid.New())) // owned by someone else
	defer ts.Close()
	s := &Server{cfg: &config.Config{BookServiceURL: ts.URL, InternalServiceToken: "t", JWTSecret: "test_jwt_secret_at_least_32_characters_long"}, grantClient: buildGrantClient(ts.URL, "t")}
	_, _, err := s.toolProposeNewKind(ctxWithUser(uuid.New()), nil,
		proposeKindToolIn{BookID: uuid.NewString(), Code: "x", Name: "X"})
	if err == nil || !strings.Contains(err.Error(), "not accessible") {
		t.Fatalf("non-owner must be denied, got %v", err)
	}
}

// ── confirm endpoint (DB-backed) — the only create path ──────────────────────

type schemaFixture struct {
	srv     *Server
	jwt     string
	ownerID uuid.UUID
	bookID  uuid.UUID
}

func newSchemaFixture(t *testing.T, pool *pgxpool.Pool) *schemaFixture {
	t.Helper()
	runK2aMigrations(t, pool)
	// createAttrDefFromParams writes genre_tags/auto_fill_prompt/translation_hint —
	// columns added by UpGenreGroups (idempotent ADD COLUMN IF NOT EXISTS).
	if err := migrate.UpGenreGroups(context.Background(), pool); err != nil {
		t.Fatalf("UpGenreGroups: %v", err)
	}
	owner, book := uuid.New(), uuid.New()
	ts := httptest.NewServer(projection(book, owner))
	t.Cleanup(ts.Close)
	srv := NewServer(pool, &config.Config{
		JWTSecret: versionTestSecret, BookServiceURL: ts.URL, InternalServiceToken: "tok",
	})
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject: owner.String(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(versionTestSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), `DELETE FROM attribute_definitions WHERE kind_id IN (SELECT kind_id FROM entity_kinds WHERE code='qa_new_kind')`)
		pool.Exec(context.Background(), `DELETE FROM entity_kinds WHERE code='qa_new_kind'`)
	})
	return &schemaFixture{srv: srv, jwt: signed, ownerID: owner, bookID: book}
}

func (f *schemaFixture) confirm(t *testing.T, token string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"confirm_token": token})
	req := httptest.NewRequest(http.MethodPost, "/v1/glossary/schema/confirm", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+f.jwt)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func TestConfirmSchema_CreatesKindThenRejectsReplayAndBadTokens(t *testing.T) {
	pool := openTestDB(t)
	f := newSchemaFixture(t, pool)
	ctx := context.Background()
	params, _ := json.Marshal(kindCreateParams{Code: "qa_new_kind", Name: "Power System"})

	// valid token → 201 + kind created
	good := mintSchemaToken(versionTestSecret, f.ownerID, f.bookID, schemaOpKind, params, time.Now())
	if w := f.confirm(t, good); w.Code != http.StatusCreated {
		t.Fatalf("valid confirm: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM entity_kinds WHERE code='qa_new_kind'`).Scan(&n)
	if n != 1 {
		t.Fatalf("kind not created: count=%d", n)
	}

	// replay the SAME token → create runs again → duplicate code → 409 (no second kind)
	if w := f.confirm(t, good); w.Code != http.StatusConflict {
		t.Errorf("replay: want 409 dup, got %d", w.Code)
	}

	// expired token → 422
	expired := mintSchemaToken(versionTestSecret, f.ownerID, f.bookID, schemaOpKind, params, time.Now().Add(-2*schemaTokenTTL))
	if w := f.confirm(t, expired); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("expired: want 422, got %d", w.Code)
	}

	// tampered token → 422
	if w := f.confirm(t, good[:len(good)-2]+"zz"); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("tampered: want 422, got %d", w.Code)
	}

	// token minted for a DIFFERENT user → 403 (bound to proposer)
	other := mintSchemaToken(versionTestSecret, uuid.New(), f.bookID, schemaOpKind, params, time.Now())
	if w := f.confirm(t, other); w.Code != http.StatusForbidden {
		t.Errorf("wrong-user token: want 403, got %d", w.Code)
	}
}

// Round-trip: the ACTUAL flow — propose tool mints the token, confirm creates.
// Exercises the propose tool's param marshaling that the direct-mint tests skip.
func TestProposeNewKind_RoundTripToConfirm(t *testing.T) {
	pool := openTestDB(t)
	f := newSchemaFixture(t, pool)
	_, out, err := f.srv.toolProposeNewKind(ctxWithUser(f.ownerID), nil,
		proposeKindToolIn{BookID: f.bookID.String(), Code: "qa_new_kind", Name: "Power System"})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if out.ConfirmToken == "" || out.Op != schemaOpKind {
		t.Fatalf("bad propose output: %+v", out)
	}
	if w := f.confirm(t, out.ConfirmToken); w.Code != http.StatusCreated {
		t.Fatalf("confirm of a freshly-proposed token: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(context.Background(), `SELECT count(*) FROM entity_kinds WHERE code='qa_new_kind'`).Scan(&n)
	if n != 1 {
		t.Errorf("round-trip did not create the kind: count=%d", n)
	}
}

// The kind is deleted between propose and confirm → FK violation → clean 422.
func TestConfirmSchema_DeletedKindIsCleanError(t *testing.T) {
	pool := openTestDB(t)
	f := newSchemaFixture(t, pool)
	ctx := context.Background()
	k, err := f.srv.createKindFromParams(ctx, kindCreateParams{Code: "qa_new_kind", Name: "Power System"})
	if err != nil {
		t.Fatalf("seed kind: %v", err)
	}
	params, _ := json.Marshal(attrCreateParams{KindID: k.KindID, Code: "realm", Name: "Realm", FieldType: "text"})
	tok := mintSchemaToken(versionTestSecret, f.ownerID, f.bookID, schemaOpAttribute, params, time.Now())
	// kind vanishes (cascades its attribute_definitions) before the human confirms.
	if _, err := pool.Exec(ctx, `DELETE FROM entity_kinds WHERE kind_id=$1`, k.KindID); err != nil {
		t.Fatalf("delete kind: %v", err)
	}
	if w := f.confirm(t, tok); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("confirm against a deleted kind: want 422 (not 500), got %d", w.Code)
	}
}

func TestConfirmSchema_CreatesAttribute(t *testing.T) {
	pool := openTestDB(t)
	f := newSchemaFixture(t, pool)
	ctx := context.Background()
	// create the kind first (reuse the core directly)
	k, err := f.srv.createKindFromParams(ctx, kindCreateParams{Code: "qa_new_kind", Name: "Power System"})
	if err != nil {
		t.Fatalf("seed kind: %v", err)
	}
	params, _ := json.Marshal(attrCreateParams{KindID: k.KindID, Code: "realm", Name: "Realm", FieldType: "text"})
	tok := mintSchemaToken(versionTestSecret, f.ownerID, f.bookID, schemaOpAttribute, params, time.Now())
	if w := f.confirm(t, tok); w.Code != http.StatusCreated {
		t.Fatalf("attr confirm: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM attribute_definitions WHERE kind_id=$1 AND code='realm'`, k.KindID).Scan(&n)
	if n != 1 {
		t.Errorf("attribute not created: count=%d", n)
	}
}
