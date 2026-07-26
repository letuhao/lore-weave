package authjwt

import (
	"context"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// OAuthAccessClaims is the wire contract for a P5 public-MCP OAuth 2.1 access
// token. It is RS256-signed by the SAME DigestSigner as admin tokens (so the edge
// verifies both with the same JWKS key) but carries a DISTINCT issuer + audience
// so it can NEVER be replayed as an admin token and vice-versa:
//   - the public MCP edge accepts ONLY {iss: cfg.OAuthIssuer, aud: cfg.OAuthResource}
//   - ai-gateway /mcp/admin (+ glossary) accept ONLY the admin iss/aud
//
// `aud` is the canonical MCP resource URL (RFC 8707 resource indicator). The edge
// verifies aud == its configured resource to reject audience-confused tokens (S9).
//
// JSON tags are load-bearing wire names shared by signer (here) and the edge
// verifier (token-verifier.ts) — do not rename without bumping both sides.
type OAuthAccessClaims struct {
	Scope    string `json:"scope"` // space-delimited OAuth scopes (RFC 6749 §3.3)
	ClientID string `json:"client_id"`
	GrantID  string `json:"grant_id"` // the mcp_oauth_grants id; rides x-mcp-key-id at the edge
	jwt.RegisteredClaims
}

// OAuthMintInput carries the per-token fields for SignOAuthAccessToken.
type OAuthMintInput struct {
	Issuer   string
	Subject  uuid.UUID // the LoreWeave user the token acts on-behalf-of ("sub")
	Audience string    // the MCP resource URL (RFC 8707) → "aud"
	ClientID string
	GrantID  string
	Scope    string // space-delimited
	TTL      time.Duration
}

// SignOAuthAccessToken mints an RS256 OAuth access token via the shared
// assembleRS256 path (byte-identical wire shape to admin tokens; only the claims
// differ). The caller supplies a distinct issuer + the resource audience.
func SignOAuthAccessToken(ctx context.Context, signer DigestSigner, in OAuthMintInput) (Issued, error) {
	now := time.Now()
	jti, err := uuid.NewV7()
	if err != nil {
		return Issued{}, fmt.Errorf("authjwt: oauth jti: %w", err)
	}
	exp := now.Add(in.TTL)
	claims := OAuthAccessClaims{
		Scope:    in.Scope,
		ClientID: in.ClientID,
		GrantID:  in.GrantID,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   in.Subject.String(),
			Issuer:    in.Issuer,
			Audience:  jwt.ClaimStrings{in.Audience},
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(exp),
			ID:        jti.String(),
		},
	}
	tok, err := assembleRS256(ctx, signer, claims)
	if err != nil {
		return Issued{}, err
	}
	return Issued{Token: tok, JTI: jti, IssuedAt: now, ExpiresAt: exp}, nil
}
