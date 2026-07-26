package authjwt_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"

	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/authjwt/signertest"
)

const (
	testOAuthIssuer   = "loreweave-mcp-oauth"
	testOAuthResource = "https://app.loreweave.dev/mcp"
)

func mintTestOAuth(t *testing.T, signer authjwt.DigestSigner, sub uuid.UUID, scope string) string {
	t.Helper()
	issued, err := authjwt.SignOAuthAccessToken(context.Background(), signer, authjwt.OAuthMintInput{
		Issuer:   testOAuthIssuer,
		Subject:  sub,
		Audience: testOAuthResource,
		ClientID: "client-abc",
		GrantID:  uuid.NewString(),
		Scope:    scope,
		TTL:      10 * time.Minute,
	})
	if err != nil {
		t.Fatalf("mint oauth: %v", err)
	}
	return issued.Token
}

func TestSignOAuthAccessToken_ClaimsAndShape(t *testing.T) {
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatal(err)
	}
	sub := uuid.New()
	tok := mintTestOAuth(t, signer, sub, "read domain:book")

	// Three RS256 segments.
	if got := len(strings.Split(tok, ".")); got != 3 {
		t.Fatalf("want 3 JWT segments, got %d", got)
	}

	// Parse with the matching public key + the OAuth claims type; assert the
	// distinct issuer + the resource audience + scopes.
	var claims authjwt.OAuthAccessClaims
	parsed, err := jwt.NewParser(
		jwt.WithValidMethods([]string{"RS256"}),
		jwt.WithIssuer(testOAuthIssuer),
		jwt.WithAudience(testOAuthResource),
		jwt.WithExpirationRequired(),
	).ParseWithClaims(tok, &claims, func(*jwt.Token) (any, error) { return signer.PublicKey(), nil })
	if err != nil || !parsed.Valid {
		t.Fatalf("parse oauth token: %v", err)
	}
	if claims.Subject != sub.String() {
		t.Errorf("sub = %q, want %q", claims.Subject, sub.String())
	}
	if claims.Scope != "read domain:book" {
		t.Errorf("scope = %q", claims.Scope)
	}
	if claims.ClientID != "client-abc" || claims.GrantID == "" {
		t.Errorf("client_id/grant_id not set: %+v", claims)
	}
}

// The load-bearing separation: an OAuth access token must NOT verify as an admin
// token (distinct issuer + audience), even though it is signed by the same key.
func TestOAuthToken_RejectedByAdminVerify(t *testing.T) {
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatal(err)
	}
	// Sanity: the OAuth issuer differs from the admin issuer constant.
	if testOAuthIssuer == adminjwt.Issuer {
		t.Fatal("test misconfig: OAuth issuer equals admin issuer")
	}
	tok := mintTestOAuth(t, signer, uuid.New(), "read")
	if _, err := adminjwt.Verify(tok, signer.PublicKey(), signer.KID()); err == nil {
		t.Fatal("an OAuth token MUST be rejected by adminjwt.Verify (issuer/audience separation)")
	}
}

// And the converse: an admin token must NOT verify as an OAuth token (the edge
// pins iss=OAuthIssuer + aud=resource; an admin token carries neither).
func TestAdminToken_RejectedByOAuthVerify(t *testing.T) {
	signer, err := signertest.Generate(2048)
	if err != nil {
		t.Fatal(err)
	}
	issued, err := authjwt.SignAdmin(context.Background(), signer, uuid.New(), "admin", []string{"*"}, 10*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	var claims authjwt.OAuthAccessClaims
	_, err = jwt.NewParser(
		jwt.WithValidMethods([]string{"RS256"}),
		jwt.WithIssuer(testOAuthIssuer),
		jwt.WithAudience(testOAuthResource),
		jwt.WithExpirationRequired(),
	).ParseWithClaims(issued.Token, &claims, func(*jwt.Token) (any, error) { return signer.PublicKey(), nil })
	if err == nil {
		t.Fatal("an admin token MUST be rejected by the OAuth (iss+aud) verify")
	}
}
