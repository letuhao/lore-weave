package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/pashagolub/pgxmock/v4"

	"github.com/loreweave/agent-registry-service/internal/config"
)

// RFC 7636 Appendix B known-answer vector for S256.
func TestPKCES256_RFC7636Vector(t *testing.T) {
	verifier := "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
	want := "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
	if got := pkceS256Challenge(verifier); got != want {
		t.Errorf("S256 challenge = %q, want %q", got, want)
	}
}

func TestBuildAuthorizationURL(t *testing.T) {
	meta := oauthMeta{
		AuthorizationEndpoint: "https://as.example.com/authorize",
		ClientID:              "client-123",
		Scopes:                []string{"mcp.read", "mcp.tools"},
		Resource:              "https://mcp.example.com/mcp",
	}
	raw, err := buildAuthorizationURL(meta, "https://app/cb", "state-xyz", "chal-abc")
	if err != nil {
		t.Fatal(err)
	}
	u, _ := url.Parse(raw)
	q := u.Query()
	checks := map[string]string{
		"response_type":         "code",
		"client_id":             "client-123",
		"redirect_uri":          "https://app/cb",
		"state":                 "state-xyz",
		"code_challenge":        "chal-abc",
		"code_challenge_method": "S256",
		"scope":                 "mcp.read mcp.tools",
		"resource":              "https://mcp.example.com/mcp", // RFC 8707
	}
	for k, want := range checks {
		if q.Get(k) != want {
			t.Errorf("authz url %s = %q, want %q", k, q.Get(k), want)
		}
	}
}

func testServer(allowInternal bool) *Server {
	return NewServer(nil, &config.Config{
		JWTSecret:               "loreweave_local_dev_jwt_secret_change_me_32chars",
		VaultKey:                "loreweave_local_dev_jwt_secret_change_me_32chars",
		AllowInternalMcpTargets: allowInternal,
	})
}

func TestExchangeCode_AgainstFakeAS(t *testing.T) {
	var gotForm url.Values
	as := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		gotForm = r.Form
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": "at-1", "refresh_token": "rt-1", "token_type": "Bearer", "expires_in": 3600,
		})
	}))
	defer as.Close()
	s := testServer(true) // allowInternal → the httptest loopback AS is reachable
	meta := oauthMeta{TokenEndpoint: as.URL, ClientID: "c1", Resource: "https://mcp.example.com/mcp"}
	tok, err := s.exchangeCode(context.Background(), meta, "auth-code", "verifier-1", "https://app/cb")
	if err != nil {
		t.Fatalf("exchange failed: %v", err)
	}
	if tok.AccessToken != "at-1" || tok.RefreshToken != "rt-1" || tok.ExpiresIn != 3600 {
		t.Errorf("unexpected token: %+v", tok)
	}
	// exchange sent PKCE + grant + RFC 8707 resource
	if gotForm.Get("grant_type") != "authorization_code" || gotForm.Get("code") != "auth-code" ||
		gotForm.Get("code_verifier") != "verifier-1" || gotForm.Get("resource") != "https://mcp.example.com/mcp" {
		t.Errorf("token request missing PKCE/resource params: %v", gotForm)
	}
}

func TestRefreshToken_AgainstFakeAS(t *testing.T) {
	as := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		if r.Form.Get("grant_type") != "refresh_token" || r.Form.Get("refresh_token") != "old-rt" {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 1800})
	}))
	defer as.Close()
	s := testServer(true)
	tok, err := s.refreshToken(context.Background(), oauthMeta{TokenEndpoint: as.URL, ClientID: "c1"}, "old-rt")
	if err != nil || tok.AccessToken != "at-2" {
		t.Fatalf("refresh failed: tok=%+v err=%v", tok, err)
	}
}

// Full callback core: state consume → exchange → seal, with a mock pool + fake AS.
func TestCompleteOAuth_ConsumesStateAndSealsToken(t *testing.T) {
	as := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
	}))
	defer as.Close()

	mock, err := pgxmock.NewPool()
	if err != nil {
		t.Fatal(err)
	}
	defer mock.Close()
	s := NewServer(mock, &config.Config{
		JWTSecret: "loreweave_local_dev_jwt_secret_change_me_32chars", VaultKey: "loreweave_local_dev_jwt_secret_change_me_32chars",
		AllowInternalMcpTargets: true,
	})
	mid := uuid.New()
	owner := uuid.New()
	meta, _ := json.Marshal(oauthMeta{TokenEndpoint: as.URL, ClientID: "c1", Resource: "https://mcp.example.com/mcp"})

	mock.ExpectQuery("DELETE FROM oauth_flows").WithArgs("st").
		WillReturnRows(pgxmock.NewRows([]string{"mcp_server_id", "owner_user_id", "code_verifier", "redirect_uri"}).AddRow(mid, owner, "ver", "https://app/cb"))
	mock.ExpectQuery("SELECT oauth_meta FROM mcp_server_registrations").WithArgs(mid).
		WillReturnRows(pgxmock.NewRows([]string{"oauth_meta"}).AddRow(meta))
	// storeOAuthTokens seals AT+RT and writes them (ciphertext, not plaintext).
	mock.ExpectExec("UPDATE mcp_server_registrations").
		WithArgs(mid, pgxmock.AnyArg(), pgxmock.AnyArg(), pgxmock.AnyArg()).
		WillReturnResult(pgxmock.NewResult("UPDATE", 1))

	gotMid, gotOwner, err := s.completeOAuth(context.Background(), "st", "the-code")
	if err != nil {
		t.Fatalf("completeOAuth: %v", err)
	}
	if gotMid != mid || gotOwner != owner {
		t.Errorf("wrong ids: %v/%v", gotMid, gotOwner)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("unmet expectations: %v", err)
	}
}

func TestPostToken_SSRFBlocksLoopbackWhenNotAllowed(t *testing.T) {
	as := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	defer as.Close()
	s := testServer(false) // prod posture → loopback token endpoint blocked
	_, err := s.postToken(context.Background(), as.URL, url.Values{})
	if err == nil || !strings.Contains(err.Error(), "blocked") {
		t.Errorf("expected SSRF dial-block for a loopback token endpoint, got %v", err)
	}
}
