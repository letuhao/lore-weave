package api

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/glossary-service/internal/config"
)

// T4 — System-tier admin MCP tools + the /mcp/admin transport gate + the RS256 admin
// confirm path. The headline is INV-T6: the admin surface is unreachable without a
// verified admin token (401 BEFORE tools/list), admin tools never appear on /mcp, and
// every System write is single-use human-confirmed. Requires GLOSSARY_TEST_DB_URL.

const adminMCPInternalToken = "admintok"

type adminMCPFixture struct {
	srv  *Server
	mint func(sub string) string // RS256 admin:write token for a given subject
}

func newAdminMCPFixture(t *testing.T, pool *pgxpool.Pool) *adminMCPFixture {
	t.Helper()
	runK2aMigrations(t, pool)
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("genkey: %v", err)
	}
	pubDER, _ := x509.MarshalPKIXPublicKey(&priv.PublicKey)
	pubPEM := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: pubDER})
	srv := NewServer(pool, &config.Config{
		JWTSecret: versionTestSecret, AdminJWTPublicKeyPEM: string(pubPEM), InternalServiceToken: adminMCPInternalToken,
	})
	if srv.adminPub == nil {
		t.Fatal("admin verification not enabled")
	}
	kid, _ := adminjwt.KeyFingerprint(&priv.PublicKey)
	mint := func(sub string) string {
		claims := adminjwt.AdminClaims{
			Role:   "admin",
			Scopes: []string{scopeAdminWrite},
			RegisteredClaims: jwt.RegisteredClaims{
				Issuer: adminjwt.Issuer, Audience: jwt.ClaimStrings{adminjwt.Audience},
				Subject: sub, ID: uuid.NewString(),
				ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)), IssuedAt: jwt.NewNumericDate(time.Now()),
			},
		}
		tok := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
		tok.Header["kid"] = kid
		signed, err := tok.SignedString(priv)
		if err != nil {
			t.Fatalf("sign: %v", err)
		}
		return signed
	}
	return &adminMCPFixture{srv: srv, mint: mint}
}

// adminMCP posts a JSON-RPC body to /mcp/admin with the given headers.
func (f *adminMCPFixture) adminMCP(t *testing.T, body string, internal, adminTok string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/mcp/admin", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	if internal != "" {
		req.Header.Set("X-Internal-Token", internal)
	}
	if adminTok != "" {
		req.Header.Set("X-Admin-Token", adminTok)
	}
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

// adminConfirm posts {confirm_token} to /v1/glossary/actions/admin/confirm with an
// RS256 admin Bearer token.
func (f *adminMCPFixture) adminConfirm(t *testing.T, path, token, adminBearer string) *httptest.ResponseRecorder {
	t.Helper()
	body, _ := json.Marshal(map[string]string{"confirm_token": token})
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if adminBearer != "" {
		req.Header.Set("Authorization", "Bearer "+adminBearer)
	}
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	return w
}

const toolsListBody = `{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}`

// INV-T6 barrier 1: /mcp/admin cannot even be ENUMERATED without a valid admin token.
func TestAdminMCP_TransportGateBlocksEnumeration(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)

	// no admin token → 401, no tools/list
	if w := f.adminMCP(t, toolsListBody, adminMCPInternalToken, ""); w.Code != http.StatusUnauthorized {
		t.Errorf("no admin token: want 401, got %d", w.Code)
	}
	// wrong internal token → 401
	if w := f.adminMCP(t, toolsListBody, "nope", f.mint(uuid.NewString())); w.Code != http.StatusUnauthorized {
		t.Errorf("wrong internal token: want 401, got %d", w.Code)
	}
	// a valid admin token → lists the admin tools
	w := f.adminMCP(t, toolsListBody, adminMCPInternalToken, f.mint(uuid.NewString()))
	if w.Code != http.StatusOK {
		t.Fatalf("valid admin token: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "glossary_admin_propose_create") {
		t.Errorf("admin tools/list should advertise the propose tools: %s", w.Body.String())
	}
}

// INV-T6 barrier 2: admin tools NEVER appear on the user /mcp catalog.
func TestAdminMCP_AbsentFromUserCatalog(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)
	req := httptest.NewRequest(http.MethodPost, "/mcp", bytes.NewBufferString(toolsListBody))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	req.Header.Set("X-Internal-Token", adminMCPInternalToken)
	req.Header.Set("X-User-Id", uuid.NewString())
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("user /mcp tools/list: want 200, got %d", w.Code)
	}
	if strings.Contains(w.Body.String(), "glossary_admin_") {
		t.Errorf("admin tool leaked into the user /mcp catalog: %s", w.Body.String())
	}
}

// callToolConfirmToken extracts result.structuredContent.confirm_token from a tools/call
// response (and fails if the tool returned isError).
func callToolConfirmToken(t *testing.T, body string) string {
	t.Helper()
	var resp struct {
		Result struct {
			IsError           bool `json:"isError"`
			StructuredContent struct {
				ConfirmToken string `json:"confirm_token"`
				Authority    string `json:"authority"`
			} `json:"structuredContent"`
		} `json:"result"`
	}
	if err := json.Unmarshal([]byte(body), &resp); err != nil {
		t.Fatalf("decode tools/call: %v (%s)", err, body)
	}
	if resp.Result.IsError || resp.Result.StructuredContent.ConfirmToken == "" {
		t.Fatalf("propose returned no confirm_token (isError=%v): %s", resp.Result.IsError, body)
	}
	if resp.Result.StructuredContent.Authority != authorityAdmin {
		t.Errorf("admin card authority: want admin, got %q", resp.Result.StructuredContent.Authority)
	}
	return resp.Result.StructuredContent.ConfirmToken
}

// End-to-end: admin proposes a System genre via /mcp/admin → confirms via the RS256
// admin endpoint → System row created → replay is single-use → a DIFFERENT admin can't
// confirm (asub bound) → an HS256 user token can't confirm at all.
func TestAdminMCP_ProposeConfirmRoundTripAndGuards(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)
	ctx := context.Background()
	sub := uuid.NewString()
	adminTok := f.mint(sub)
	code := "adm_live_" + uuid.NewString()[:8]
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, code) })

	call := `{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"glossary_admin_propose_create",` +
		`"arguments":{"level":"genre","name":"Admin Live","code":"` + code + `"}}}`
	w := f.adminMCP(t, call, adminMCPInternalToken, adminTok)
	if w.Code != http.StatusOK {
		t.Fatalf("propose: want 200, got %d (%s)", w.Code, w.Body.String())
	}
	confirmTok := callToolConfirmToken(t, w.Body.String())

	// preview (RS256-gated, NON-consuming) returns the card without writing or burning.
	if pw := f.adminConfirm(t, "/v1/glossary/actions/admin/preview", confirmTok, adminTok); pw.Code != http.StatusOK {
		t.Fatalf("admin preview: want 200, got %d (%s)", pw.Code, pw.Body.String())
	} else {
		var pv actionPreview
		json.Unmarshal(pw.Body.Bytes(), &pv)
		if pv.Descriptor != descSystemCreate || len(pv.PreviewRows) == 0 {
			t.Errorf("admin preview should render the card: %+v", pv)
		}
	}
	// a non-admin (HS256) cannot even preview
	if pw := f.adminConfirm(t, "/v1/glossary/actions/admin/preview", confirmTok, userHS256(t)); pw.Code == http.StatusOK {
		t.Error("HS256 user must not preview an admin action")
	}

	// a DIFFERENT admin (different sub) cannot confirm → 403, no burn
	if cw := f.adminConfirm(t, "/v1/glossary/actions/admin/confirm", confirmTok, f.mint(uuid.NewString())); cw.Code != http.StatusForbidden {
		t.Errorf("wrong-admin confirm: want 403, got %d (%s)", cw.Code, cw.Body.String())
	}
	// an HS256 user token is rejected at the admin gate (requireAdminScope) → 401
	if cw := f.adminConfirm(t, "/v1/glossary/actions/admin/confirm", confirmTok, userHS256(t)); cw.Code == http.StatusCreated {
		t.Error("an HS256 user token must NOT confirm a System write")
	}
	// the proposing admin confirms → 201 + the row exists
	if cw := f.adminConfirm(t, "/v1/glossary/actions/admin/confirm", confirmTok, adminTok); cw.Code != http.StatusCreated {
		t.Fatalf("admin confirm: want 201, got %d (%s)", cw.Code, cw.Body.String())
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM system_genres WHERE code=$1`, code).Scan(&n)
	if n != 1 {
		t.Fatalf("system genre not created: count=%d", n)
	}
	// replay → single-use 422
	if cw := f.adminConfirm(t, "/v1/glossary/actions/admin/confirm", confirmTok, adminTok); cw.Code != http.StatusUnprocessableEntity {
		t.Errorf("replay admin confirm: want 422 single-use, got %d", cw.Code)
	}
}

// A user-authority (HS256) confirm token can never drive a System write via the user
// /actions/confirm path — the authorityAdmin branch there stays fail-closed 501. And a
// hand-forged admin-authority token cannot ride the user endpoint.
func TestAdminMCP_UserConfirmPathRejectsAdminAuthority(t *testing.T) {
	pool := openTestDB(t)
	f := newAdminMCPFixture(t, pool)
	tok := mintActionToken(versionTestSecret, actionClaims{
		JTI: uuid.NewString(), Authority: authorityAdmin, AdminSub: "x", Descriptor: descSystemCreate,
		Params: json.RawMessage(`{"level":"genre","name":"X"}`),
	}, time.Now())
	// user endpoint requires a valid HS256 user (signed with the server's JWTSecret);
	// even with one, an authorityAdmin token → 501 fail-closed there.
	uclaims := jwt.RegisteredClaims{Subject: uuid.NewString(), ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour))}
	userTok, _ := jwt.NewWithClaims(jwt.SigningMethodHS256, uclaims).SignedString([]byte(versionTestSecret))
	body, _ := json.Marshal(map[string]string{"confirm_token": tok})
	req := httptest.NewRequest(http.MethodPost, "/v1/glossary/actions/confirm", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+userTok)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	f.srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusNotImplemented {
		t.Errorf("admin-authority on the user path: want 501 fail-closed, got %d (%s)", w.Code, w.Body.String())
	}
}

// Admin disabled (no key) → /mcp/admin fails closed even with the internal token.
func TestAdminMCP_FailClosedWhenDisabled(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv := NewServer(pool, &config.Config{JWTSecret: versionTestSecret, InternalServiceToken: adminMCPInternalToken})
	if srv.adminPub != nil {
		t.Fatal("expected admin disabled")
	}
	req := httptest.NewRequest(http.MethodPost, "/mcp/admin", bytes.NewBufferString(toolsListBody))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", adminMCPInternalToken)
	req.Header.Set("X-Admin-Token", "anything")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("admin disabled: want 401 fail-closed, got %d", w.Code)
	}
}

// External MCP discoverability audit #11 — every Patch* field on adminPatchToolIn is a
// pointer (nil = unchanged). Proposing a patch with NO fields supplied changes nothing;
// it must still mint (not an error) but must carry a warning. Calls the handler directly
// (no RSA/MCP transport needed — adminSubFromCtx just reads a context value).
func TestAdminTool_ProposePatchNoOpWarnsOnEmptyPayload(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv := NewServer(pool, &config.Config{JWTSecret: versionTestSecret, InternalServiceToken: adminMCPInternalToken})
	code := "adm_patch_noop_" + uuid.NewString()[:8]
	if _, err := pool.Exec(context.Background(),
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'AdmPatchNoop','g0')`, code); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, code) }) //nolint:errcheck

	ctx := context.WithValue(context.Background(), ctxKeyAdminSub, uuid.NewString())
	_, card, err := srv.toolAdminProposePatch(ctx, nil, adminPatchToolIn{Level: "genre", Code: code})
	if err != nil {
		t.Fatalf("propose patch with no fields: %v", err)
	}
	if card.ConfirmToken == "" {
		t.Fatal("a no-op patch must still mint a valid confirm_token (it is not an error)")
	}
	if card.Warning == "" {
		t.Fatalf("a patch with no fields supplied must carry a no-op warning, got card=%+v", card)
	}
	if !strings.Contains(card.Warning, "no fields") {
		t.Errorf("warning should state no fields were given, got %q", card.Warning)
	}
}

// A patch that actually supplies a field must NOT carry the no-op warning.
func TestAdminTool_ProposePatchWithFieldCarriesNoWarning(t *testing.T) {
	pool := openTestDB(t)
	runK2aMigrations(t, pool)
	srv := NewServer(pool, &config.Config{JWTSecret: versionTestSecret, InternalServiceToken: adminMCPInternalToken})
	code := "adm_patch_real_" + uuid.NewString()[:8]
	if _, err := pool.Exec(context.Background(),
		`INSERT INTO system_genres (code,name,content_hash) VALUES ($1,'AdmPatchReal','g0')`, code); err != nil {
		t.Fatalf("seed system genre: %v", err)
	}
	t.Cleanup(func() { pool.Exec(context.Background(), `DELETE FROM system_genres WHERE code=$1`, code) }) //nolint:errcheck

	ctx := context.WithValue(context.Background(), ctxKeyAdminSub, uuid.NewString())
	newName := "AdmPatchReal Renamed"
	_, card, err := srv.toolAdminProposePatch(ctx, nil, adminPatchToolIn{Level: "genre", Code: code, Name: &newName})
	if err != nil {
		t.Fatalf("propose patch: %v", err)
	}
	if card.Warning != "" {
		t.Errorf("a patch with a real field must not carry the no-op warning, got %q", card.Warning)
	}
}
