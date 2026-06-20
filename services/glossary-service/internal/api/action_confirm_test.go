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
)

// ── token unit tests (no DB) — generalized action confirm token (§13.2) ───────

func mkClaims(u, b uuid.UUID, desc string) actionClaims {
	return actionClaims{JTI: uuid.NewString(), Authority: authorityGrant, UserID: u, BookID: b, Descriptor: desc,
		Params: json.RawMessage(`{"code":"qa_new_kind","name":"Power System"}`)}
}

func TestActionToken_RoundTrip(t *testing.T) {
	secret := "test_jwt_secret_at_least_32_characters_long"
	u, b := uuid.New(), uuid.New()
	now := time.Unix(1_900_000_000, 0)
	c := mkClaims(u, b, descSchemaCreateKind)
	tok := mintActionToken(secret, c, now)
	if tok == "" {
		t.Fatal("mint returned empty token")
	}
	got, err := verifyActionToken(secret, tok, now.Add(time.Minute))
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if got.UserID != u || got.BookID != b || got.Descriptor != descSchemaCreateKind || got.JTI != c.JTI || got.Authority != authorityGrant {
		t.Errorf("claims mismatch: %+v", got)
	}
}

func TestActionToken_Expired(t *testing.T) {
	secret := "test_jwt_secret_at_least_32_characters_long"
	now := time.Unix(1_900_000_000, 0)
	tok := mintActionToken(secret, mkClaims(uuid.New(), uuid.New(), descBookDelete), now)
	if _, err := verifyActionToken(secret, tok, now.Add(actionTokenTTL+time.Second)); !errors.Is(err, ErrActionTokenExpired) {
		t.Fatalf("want ErrActionTokenExpired, got %v", err)
	}
}

func TestActionToken_TamperAndUnknownDescriptorRejected(t *testing.T) {
	secret := "test_jwt_secret_at_least_32_characters_long"
	now := time.Unix(1_900_000_000, 0)
	tok := mintActionToken(secret, mkClaims(uuid.New(), uuid.New(), descSchemaCreateKind), now)
	// tamper the payload (deterministically invalidates the signature)
	parts := strings.SplitN(tok, ".", 3)
	flip := map[bool]byte{true: 'B', false: 'A'}[parts[0][0] == 'A']
	parts[0] = string(flip) + parts[0][1:]
	if _, err := verifyActionToken(secret, strings.Join(parts, "."), now.Add(time.Minute)); !errors.Is(err, ErrActionTokenInvalid) {
		t.Fatalf("tampered payload must be invalid, got %v", err)
	}
	// wrong secret
	if _, err := verifyActionToken("another_secret_at_least_32_characters_xx", tok, now.Add(time.Minute)); !errors.Is(err, ErrActionTokenInvalid) {
		t.Fatalf("wrong-secret must be invalid, got %v", err)
	}
	// a not-yet-live descriptor must NOT mint (fail closed)
	if mintActionToken(secret, mkClaims(uuid.New(), uuid.New(), "system_create"), now) != "" {
		t.Error("reserved descriptor must not mint a token")
	}
}

func TestActionToken_FailClosedAndMalformed(t *testing.T) {
	now := time.Unix(1_900_000_000, 0)
	secret := "test_jwt_secret_at_least_32_characters_long"
	if mintActionToken("", mkClaims(uuid.New(), uuid.New(), descBookDelete), now) != "" {
		t.Error("empty secret must mint no token (fail closed)")
	}
	if mintActionToken(secret, actionClaims{Authority: authorityGrant, Descriptor: descBookDelete}, now) != "" {
		t.Error("missing jti must mint no token (single-use needs an id)")
	}
	for _, bad := range []string{"", "nodot", "a.b.c", ".", "x."} {
		if _, err := verifyActionToken(secret, bad, now); err == nil {
			t.Errorf("malformed token %q must error", bad)
		}
	}
}

// ── base-version concurrency helper (§12.6) ───────────────────────────────────

func TestCompareBaseVersion(t *testing.T) {
	if err := compareBaseVersion("hashA", ""); err != nil {
		t.Errorf("empty base opts out → no error, got %v", err)
	}
	if err := compareBaseVersion("hashA", "hashA"); err != nil {
		t.Errorf("matching version → no error, got %v", err)
	}
	if err := compareBaseVersion("hashB", "hashA"); !errors.Is(err, errVersionConflict) {
		t.Errorf("drifted version → errVersionConflict, got %v", err)
	}
}

// ── propose tool ownership (no DB) ────────────────────────────────────────────

func TestToolProposeNewKind_MissingIdentity(t *testing.T) {
	s := &Server{}
	if _, _, err := s.toolProposeNewKind(context.Background(), nil,
		proposeKindToolIn{BookID: uuid.NewString(), Code: "x", Name: "X"}); err == nil {
		t.Fatal("want missing-identity error")
	}
}

func TestToolProposeNewAttribute_RejectsBadFieldType(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolProposeNewAttribute(ctxWithUser(uuid.New()), nil,
		proposeAttrToolIn{BookID: uuid.NewString(), KindCode: "character", Code: "x", Name: "X", FieldType: "garbage"})
	if err == nil || !strings.Contains(err.Error(), "invalid field_type") {
		t.Fatalf("bad field_type must be rejected at propose, got %v", err)
	}
}

func TestToolBookDelete_BadLevelRejected(t *testing.T) {
	s := &Server{}
	_, _, err := s.toolBookDelete(ctxWithUser(uuid.New()), nil,
		bookDeleteToolIn{BookID: uuid.NewString(), Level: "bogus", Code: "x"})
	if err == nil || !strings.Contains(err.Error(), "level must be") {
		t.Fatalf("bad level must be rejected, got %v", err)
	}
}

// ── confirm endpoint (DB-backed) ──────────────────────────────────────────────

type actionFixture struct {
	srv     *Server
	jwt     string
	ownerID uuid.UUID
	bookID  uuid.UUID
}

func newActionFixture(t *testing.T, pool *pgxpool.Pool) *actionFixture {
	t.Helper()
	runK2aMigrations(t, pool)
	owner, book := uuid.New(), uuid.New()
	adoptTestBook(t, pool, book)
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
		pool.Exec(context.Background(), `DELETE FROM book_kinds WHERE book_id=$1 AND code IN ('qa_new_kind','qa_del_kind')`, book)
	})
	return &actionFixture{srv: srv, jwt: signed, ownerID: owner, bookID: book}
}

func (f *actionFixture) post(t *testing.T, path, token string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"confirm_token": token})
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+f.jwt)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

func (f *actionFixture) confirm(t *testing.T, token string) *httptest.ResponseRecorder {
	return f.post(t, "/v1/glossary/actions/confirm", token)
}
func (f *actionFixture) preview(t *testing.T, token string) *httptest.ResponseRecorder {
	return f.post(t, "/v1/glossary/actions/preview", token)
}

// The schema-create path, migrated onto the generalized machinery. The KEY upgrade
// vs the old behavior: a replay of a consumed token is now rejected as single-use
// (422), not silently re-attempted into a 409 dup.
func TestConfirmAction_CreatesKindThenRejectsReplayAndBadTokens(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	params, _ := json.Marshal(kindCreateParams{Code: "qa_new_kind", Name: "Power System"})
	mint := func(u, b uuid.UUID, when time.Time) string {
		return mintActionToken(versionTestSecret, actionClaims{
			JTI: uuid.NewString(), Authority: authorityGrant, UserID: u, BookID: b,
			Descriptor: descSchemaCreateKind, Params: params,
		}, when)
	}

	good := mint(f.ownerID, f.bookID, time.Now())
	if w := f.confirm(t, good); w.Code != http.StatusCreated {
		t.Fatalf("valid confirm: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code='qa_new_kind'`, f.bookID).Scan(&n)
	if n != 1 {
		t.Fatalf("kind not created: count=%d", n)
	}
	// replay the SAME token → single-use → 422 (NOT a second create attempt → 409)
	if w := f.confirm(t, good); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay of a consumed token: want 422 single-use, got %d", w.Code)
	}
	// still exactly one kind — the replay never reached the create
	pool.QueryRow(ctx, `SELECT count(*) FROM book_kinds WHERE book_id=$1 AND code='qa_new_kind'`, f.bookID).Scan(&n)
	if n != 1 {
		t.Errorf("replay must not create a second kind: count=%d", n)
	}
	// expired → 422
	if w := f.confirm(t, mint(f.ownerID, f.bookID, time.Now().Add(-2*actionTokenTTL))); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("expired: want 422, got %d", w.Code)
	}
	// tampered → 422
	if w := f.confirm(t, good[:len(good)-2]+"zz"); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("tampered: want 422, got %d", w.Code)
	}
	// minted for a DIFFERENT user → 403 (bound to proposer, checked before consume)
	if w := f.confirm(t, mint(uuid.New(), f.bookID, time.Now())); w.Code != http.StatusForbidden {
		t.Errorf("wrong-user token: want 403, got %d", w.Code)
	}
}

// Round-trip: the ACTUAL flow — propose tool mints, confirm creates.
func TestProposeNewKind_RoundTripToConfirm(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	_, out, err := f.srv.toolProposeNewKind(ctxWithUser(f.ownerID), nil,
		proposeKindToolIn{BookID: f.bookID.String(), Code: "qa_new_kind", Name: "Power System"})
	if err != nil {
		t.Fatalf("propose: %v", err)
	}
	if out.ConfirmToken == "" || out.Descriptor != descSchemaCreateKind {
		t.Fatalf("bad propose output: %+v", out)
	}
	if w := f.confirm(t, out.ConfirmToken); w.Code != http.StatusCreated {
		t.Fatalf("confirm of a freshly-proposed token: want 201, got %d (%s)", w.Code, w.Body.String())
	}
}

// The kind is deleted between propose and confirm → clean 422 (re-validate at confirm).
func TestConfirmAction_DeletedKindIsCleanError(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	k, err := f.srv.createKindFromParams(ctx, f.bookID, kindCreateParams{Code: "qa_new_kind", Name: "Power System"})
	if err != nil {
		t.Fatalf("seed kind: %v", err)
	}
	params, _ := json.Marshal(attrCreateParams{KindID: k.KindID, Code: "realm", Name: "Realm", FieldType: "text"})
	tok := mintActionToken(versionTestSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityGrant, UserID: f.ownerID, BookID: f.bookID,
		Descriptor: descSchemaCreateAttr, Params: params,
	}, time.Now())
	if _, err := pool.Exec(ctx, `DELETE FROM book_kinds WHERE book_kind_id=$1`, k.KindID); err != nil {
		t.Fatalf("delete kind: %v", err)
	}
	if w := f.confirm(t, tok); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("confirm against a deleted kind: want 422 (not 500), got %d", w.Code)
	}
}

// CP-1 canary — the full book_delete round-trip: propose (mint+preview) → preview
// endpoint (current-state cascade) → confirm (soft-delete + cascade) → replay 422.
func TestBookDelete_CanaryRoundTripAndSingleUse(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	// a dedicated kind to delete (avoid disturbing seeded kinds)
	if _, err := f.srv.createKindFromParams(ctx, f.bookID, kindCreateParams{Code: "qa_del_kind", Name: "Disposable"}); err != nil {
		t.Fatalf("seed kind: %v", err)
	}

	_, card, err := f.srv.toolBookDelete(ctxWithUser(f.ownerID), nil,
		bookDeleteToolIn{BookID: f.bookID.String(), Level: "kind", Code: "qa_del_kind"})
	if err != nil {
		t.Fatalf("propose book_delete: %v", err)
	}
	if card.ConfirmToken == "" || card.Descriptor != descBookDelete || !card.Destructive {
		t.Fatalf("bad card: %+v", card)
	}

	// preview (non-consuming) returns current-state cascade rows
	if w := f.preview(t, card.ConfirmToken); w.Code != http.StatusOK {
		t.Fatalf("preview: want 200, got %d (%s)", w.Code, w.Body.String())
	} else {
		var pv actionPreview
		json.Unmarshal(w.Body.Bytes(), &pv)
		if pv.Descriptor != descBookDelete || len(pv.PreviewRows) == 0 {
			t.Errorf("preview should enumerate the cascade: %+v", pv)
		}
	}
	// preview did NOT consume — confirm still works
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusNoContent {
		t.Fatalf("confirm book_delete: want 204, got %d (%s)", w.Code, w.Body.String())
	}
	var dep *time.Time
	pool.QueryRow(ctx, `SELECT deprecated_at FROM book_kinds WHERE book_id=$1 AND code='qa_del_kind'`, f.bookID).Scan(&dep)
	if dep == nil {
		t.Error("kind was not soft-deleted")
	}
	// replay → single-use → 422
	if w := f.confirm(t, card.ConfirmToken); w.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay of consumed book_delete: want 422, got %d", w.Code)
	}
}

// Anti-griefing: a stranger submitting a victim's token is rejected (403) WITHOUT
// consuming it — so the legitimate proposer can still confirm. Proves authority is
// re-checked BEFORE the single-use jti is claimed (action_confirm.go ordering).
func TestConfirmAction_WrongUserDoesNotBurnToken(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	params, _ := json.Marshal(kindCreateParams{Code: "qa_new_kind", Name: "Power System"})
	tok := mintActionToken(versionTestSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityGrant, UserID: f.ownerID, BookID: f.bookID,
		Descriptor: descSchemaCreateKind, Params: params,
	}, time.Now())

	// A different signed-in user submits the owner's token → 403, no consume.
	stranger := uuid.New()
	sj := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject: stranger.String(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, _ := sj.SignedString([]byte(versionTestSecret))
	body, _ := json.Marshal(map[string]string{"confirm_token": tok})
	req := httptest.NewRequest(http.MethodPost, "/v1/glossary/actions/confirm", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+signed)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	// stranger is not a grantee of the book → 403/404 family, never 201; and crucially
	// not a 422-single-use (which would mean the token was consumed).
	if w.Code == http.StatusCreated || w.Code == http.StatusUnprocessableEntity {
		t.Fatalf("stranger confirm: want a denial that does NOT consume the token, got %d", w.Code)
	}

	// The owner can STILL confirm — the token was not burned by the stranger.
	if ow := f.confirm(t, tok); ow.Code != http.StatusCreated {
		t.Fatalf("owner confirm after stranger attempt: want 201 (token survived), got %d (%s)", ow.Code, ow.Body.String())
	}
}

// The admin-authority branch is fail-closed (501) in Foundation — a hand-crafted
// admin token cannot drive a System write until T4 wires it.
func TestConfirmAction_AdminAuthorityIsFailClosed(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	// A validly-signed token whose authority is admin (no mint path produces this in
	// Foundation; we forge the claims to prove the confirm branch rejects it).
	tok := mintActionToken(versionTestSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityAdmin, AdminSub: "admin-1", BookID: f.bookID,
		Descriptor: descBookDelete, Params: json.RawMessage(`{"level":"kind","code":"character"}`),
	}, time.Now())
	if w := f.confirm(t, tok); w.Code != http.StatusNotImplemented {
		t.Fatalf("admin-authority confirm: want 501 fail-closed, got %d (%s)", w.Code, w.Body.String())
	}
}

func TestConfirmAction_CreatesAttribute(t *testing.T) {
	pool := openTestDB(t)
	f := newActionFixture(t, pool)
	ctx := context.Background()
	k, err := f.srv.createKindFromParams(ctx, f.bookID, kindCreateParams{Code: "qa_new_kind", Name: "Power System"})
	if err != nil {
		t.Fatalf("seed kind: %v", err)
	}
	params, _ := json.Marshal(attrCreateParams{KindID: k.KindID, Code: "realm", Name: "Realm", FieldType: "text"})
	tok := mintActionToken(versionTestSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityGrant, UserID: f.ownerID, BookID: f.bookID,
		Descriptor: descSchemaCreateAttr, Params: params,
	}, time.Now())
	if w := f.confirm(t, tok); w.Code != http.StatusCreated {
		t.Fatalf("attr confirm: want 201, got %d (%s)", w.Code, w.Body.String())
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM book_attributes WHERE book_id=$1 AND kind_id=$2 AND code='realm'`, f.bookID, k.KindID).Scan(&n)
	if n != 1 {
		t.Errorf("attribute not created: count=%d", n)
	}
}
