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

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"

	"github.com/loreweave/auth-service/internal/adminprincipal"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/authjwt/signertest"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/ratelimit"
)

const (
	testIssuerSecret = "test-admin-issuer-secret-32characters!!"
	testHMACKey      = "test-admin-audit-hmac-key-32characters!"
	testProfileToken = "test-internal-service-token-distinct-val" // simulates InternalServiceToken (different secret)
)

type fakeStore struct {
	principals map[uuid.UUID]adminprincipal.Principal
	audits     []adminprincipal.IssuanceAuditRow
	failLookup bool
	failAudit  bool
}

func (f *fakeStore) Lookup(_ context.Context, id uuid.UUID) (adminprincipal.Principal, bool, error) {
	if f.failLookup {
		return adminprincipal.Principal{}, false, errors.New("boom")
	}
	p, ok := f.principals[id]
	return p, ok, nil
}

func (f *fakeStore) InsertAudit(_ context.Context, row adminprincipal.IssuanceAuditRow) error {
	f.audits = append(f.audits, row)
	if f.failAudit {
		return errors.New("audit insert boom")
	}
	return nil
}

func (f *fakeStore) lastAudit(t *testing.T) adminprincipal.IssuanceAuditRow {
	t.Helper()
	if len(f.audits) == 0 {
		t.Fatal("expected an audit row, got none")
	}
	return f.audits[len(f.audits)-1]
}

func newAdminTestServer(t *testing.T) (*Server, *fakeStore, *signertest.LocalRSASigner) {
	t.Helper()
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatalf("generate signer: %v", err)
	}
	store := &fakeStore{principals: map[uuid.UUID]adminprincipal.Principal{}}
	srv := &Server{cfg: &config.Config{}, rl: ratelimit.New(time.Minute, 1000)}
	srv.EnableAdminIssuance(signer, store, testIssuerSecret, testHMACKey, 15*time.Minute)
	return srv, store, signer
}

func addPrincipal(store *fakeStore, id uuid.UUID, role string, scopes []string, active bool) {
	store.principals[id] = adminprincipal.Principal{
		UserID: id, Handle: id.String() + "@example.test", Role: role, Scopes: scopes, Active: active,
	}
}

func postAdmin(t *testing.T, ts *httptest.Server, path, issuerToken string, body any) *http.Response {
	t.Helper()
	b, _ := json.Marshal(body)
	req, _ := http.NewRequest(http.MethodPost, ts.URL+path, bytes.NewReader(b))
	if issuerToken != "" {
		req.Header.Set("X-Internal-Token", issuerToken)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	return resp
}

func TestAdminEndpoints_AbsentWhenDisabled(t *testing.T) {
	// No EnableAdminIssuance => s.admin nil => routes not mounted => 404.
	srv := &Server{cfg: &config.Config{}, rl: ratelimit.New(time.Minute, 1000)}
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	for _, path := range []string{"/internal/admin/token", "/internal/admin/break-glass-token"} {
		resp := postAdmin(t, ts, path, testIssuerSecret, map[string]string{})
		if resp.StatusCode != http.StatusNotFound {
			t.Errorf("%s with admin disabled: status = %d, want 404", path, resp.StatusCode)
		}
		resp.Body.Close()
	}
}

func TestAdminToken_Happy(t *testing.T) {
	srv, store, signer := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	uid := uuid.New()
	addPrincipal(store, uid, "admin", []string{"admin:read", "admin:write"}, true)

	resp := postAdmin(t, ts, "/internal/admin/token", testIssuerSecret, adminTokenReq{UserID: uid.String()})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var out adminTokenResp
	_ = json.NewDecoder(resp.Body).Decode(&out)

	claims, err := adminjwt.Verify(out.Token, signer.PublicKey(), signer.KID())
	if err != nil {
		t.Fatalf("issued token failed verify: %v", err)
	}
	if claims.Subject != uid.String() || claims.Role != "admin" || claims.BreakGlass {
		t.Errorf("unexpected claims: %+v", claims)
	}
	if a := store.lastAudit(t); a.Outcome != "success" || a.TokenKind != "admin" || a.JTI == nil {
		t.Errorf("audit row wrong: %+v", a)
	}
}

func TestAdminToken_NotPrincipalDenied(t *testing.T) {
	srv, store, _ := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	resp := postAdmin(t, ts, "/internal/admin/token", testIssuerSecret, adminTokenReq{UserID: uuid.New().String()})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status = %d, want 403", resp.StatusCode)
	}
	if a := store.lastAudit(t); a.Outcome != "deny" {
		t.Errorf("expected deny audit, got %+v", a)
	}
}

func TestAdminToken_InactiveDenied(t *testing.T) {
	srv, store, _ := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	uid := uuid.New()
	addPrincipal(store, uid, "admin", []string{"admin:read"}, false) // inactive
	resp := postAdmin(t, ts, "/internal/admin/token", testIssuerSecret, adminTokenReq{UserID: uid.String()})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status = %d, want 403", resp.StatusCode)
	}
}

func TestAdminToken_BadIssuerTokenNoAudit(t *testing.T) {
	srv, store, _ := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	uid := uuid.New()
	addPrincipal(store, uid, "admin", []string{"admin:read"}, true)

	// Wrong token and the profile-read token (secret separation) both 401 with no audit.
	for _, tok := range []string{"", "totally-wrong", testProfileToken} {
		resp := postAdmin(t, ts, "/internal/admin/token", tok, adminTokenReq{UserID: uid.String()})
		if resp.StatusCode != http.StatusUnauthorized {
			t.Errorf("token %q: status = %d, want 401", tok, resp.StatusCode)
		}
		resp.Body.Close()
	}
	if len(store.audits) != 0 {
		t.Errorf("unauthenticated calls must not write audit rows; got %d", len(store.audits))
	}
}

func TestAdminToken_LookupErrorAudited(t *testing.T) {
	srv, store, _ := newAdminTestServer(t)
	store.failLookup = true
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	resp := postAdmin(t, ts, "/internal/admin/token", testIssuerSecret, adminTokenReq{UserID: uuid.New().String()})
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", resp.StatusCode)
	}
	if a := store.lastAudit(t); a.Outcome != "error" {
		t.Errorf("expected error audit, got %+v", a)
	}
}

// mintActorToken issues an admin token for use as a break-glass actor credential.
func mintActorToken(t *testing.T, signer *signertest.LocalRSASigner, subject uuid.UUID) string {
	t.Helper()
	issued, err := authjwt.SignAdmin(context.Background(), signer, subject, "admin", []string{"admin:destructive"}, 15*time.Minute)
	if err != nil {
		t.Fatalf("mint actor token: %v", err)
	}
	return issued.Token
}

func TestAdminToken_AuditFailureBlocksIssuance(t *testing.T) {
	srv, store, _ := newAdminTestServer(t)
	store.failAudit = true
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	uid := uuid.New()
	addPrincipal(store, uid, "admin", []string{"admin:read"}, true)
	resp := postAdmin(t, ts, "/internal/admin/token", testIssuerSecret, adminTokenReq{UserID: uid.String()})
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500 (no durable audit => no token)", resp.StatusCode)
	}
	var out adminTokenResp
	_ = json.NewDecoder(resp.Body).Decode(&out)
	if out.Token != "" {
		t.Error("token must NOT be returned when the audit write failed")
	}
}

func TestBreakGlass_RejectsBreakGlassActorToken(t *testing.T) {
	srv, store, signer := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	a, b := uuid.New(), uuid.New()
	addPrincipal(store, a, "admin", []string{"admin:destructive"}, true)
	addPrincipal(store, b, "sre", []string{"admin:destructive"}, true)

	// Primary presents a BREAK-GLASS token (not a normal admin token).
	bgIssued, err := authjwt.SignBreakGlass(context.Background(), signer, a, "admin", []string{"admin:destructive"}, time.Hour)
	if err != nil {
		t.Fatalf("mint break-glass actor token: %v", err)
	}
	body := breakGlassReq{
		PrimaryActorToken:   bgIssued.Token,
		SecondaryActorToken: mintActorToken(t, signer, b),
		Reason:              strings.Repeat("x", 120),
		IncidentTicket:      "INC-9",
		RequestedTTLSeconds: 60,
	}
	resp := postAdmin(t, ts, "/internal/admin/break-glass-token", testIssuerSecret, body)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 (break-glass token rejected as approver)", resp.StatusCode)
	}
}

func TestBreakGlass_Happy(t *testing.T) {
	srv, store, signer := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	a, b := uuid.New(), uuid.New()
	addPrincipal(store, a, "admin", []string{"admin:destructive"}, true)
	addPrincipal(store, b, "sre", []string{"admin:destructive"}, true)

	body := breakGlassReq{
		PrimaryActorToken:   mintActorToken(t, signer, a),
		SecondaryActorToken: mintActorToken(t, signer, b),
		Reason:              strings.Repeat("x", 120),
		IncidentTicket:      "INC-42",
		RequestedTTLSeconds: 3600,
	}
	resp := postAdmin(t, ts, "/internal/admin/break-glass-token", testIssuerSecret, body)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var out adminTokenResp
	_ = json.NewDecoder(resp.Body).Decode(&out)
	claims, err := adminjwt.Verify(out.Token, signer.PublicKey(), signer.KID())
	if err != nil {
		t.Fatalf("break-glass token failed verify: %v", err)
	}
	if !claims.BreakGlass {
		t.Error("break_glass claim must be true")
	}
	au := store.lastAudit(t)
	if au.Outcome != "success" || au.TokenKind != "break_glass" || !au.BreakGlass {
		t.Errorf("audit wrong: %+v", au)
	}
	if au.ReasonHMAC == nil || au.ReasonLen == nil || *au.ReasonLen != 120 {
		t.Errorf("reason audit fields wrong: hmac=%v len=%v", au.ReasonHMAC, au.ReasonLen)
	}
	if au.SecondActorID == nil || *au.SecondActorID != b {
		t.Errorf("second actor not recorded: %+v", au.SecondActorID)
	}
}

func TestBreakGlass_PolicyRejections(t *testing.T) {
	srv, store, signer := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	a, b := uuid.New(), uuid.New()
	addPrincipal(store, a, "admin", []string{"admin:destructive"}, true)
	addPrincipal(store, b, "sre", []string{"admin:destructive"}, true)
	tokA := mintActorToken(t, signer, a)
	tokB := mintActorToken(t, signer, b)
	good := strings.Repeat("x", 120)

	cases := map[string]breakGlassReq{
		"same actor":   {PrimaryActorToken: tokA, SecondaryActorToken: tokA, Reason: good, IncidentTicket: "INC-1", RequestedTTLSeconds: 60},
		"short reason": {PrimaryActorToken: tokA, SecondaryActorToken: tokB, Reason: "too short", IncidentTicket: "INC-1", RequestedTTLSeconds: 60},
		"no ticket":    {PrimaryActorToken: tokA, SecondaryActorToken: tokB, Reason: good, IncidentTicket: "", RequestedTTLSeconds: 60},
		"ttl too long": {PrimaryActorToken: tokA, SecondaryActorToken: tokB, Reason: good, IncidentTicket: "INC-1", RequestedTTLSeconds: 25 * 3600},
		"zero ttl":     {PrimaryActorToken: tokA, SecondaryActorToken: tokB, Reason: good, IncidentTicket: "INC-1", RequestedTTLSeconds: 0},
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			resp := postAdmin(t, ts, "/internal/admin/break-glass-token", testIssuerSecret, body)
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusBadRequest {
				t.Errorf("%s: status = %d, want 400", name, resp.StatusCode)
			}
		})
	}
}

func TestBreakGlass_InvalidActorToken(t *testing.T) {
	srv, store, signer := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	a := uuid.New()
	addPrincipal(store, a, "admin", []string{"admin:destructive"}, true)

	body := breakGlassReq{
		PrimaryActorToken:   mintActorToken(t, signer, a),
		SecondaryActorToken: "garbage.not.a.jwt",
		Reason:              strings.Repeat("x", 120),
		IncidentTicket:      "INC-1",
		RequestedTTLSeconds: 60,
	}
	resp := postAdmin(t, ts, "/internal/admin/break-glass-token", testIssuerSecret, body)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", resp.StatusCode)
	}
}

func TestBreakGlass_ActorNotPrincipal(t *testing.T) {
	srv, store, signer := newAdminTestServer(t)
	ts := httptest.NewServer(srv.Router())
	defer ts.Close()

	a, b := uuid.New(), uuid.New()
	addPrincipal(store, a, "admin", []string{"admin:destructive"}, true)
	// b has a valid token but is NOT a principal.

	body := breakGlassReq{
		PrimaryActorToken:   mintActorToken(t, signer, a),
		SecondaryActorToken: mintActorToken(t, signer, b),
		Reason:              strings.Repeat("x", 120),
		IncidentTicket:      "INC-1",
		RequestedTTLSeconds: 60,
	}
	resp := postAdmin(t, ts, "/internal/admin/break-glass-token", testIssuerSecret, body)
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusForbidden {
		t.Fatalf("status = %d, want 403", resp.StatusCode)
	}
}
