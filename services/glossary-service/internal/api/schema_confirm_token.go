package api

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
)

// Tier-S (P4) server-minted confirm token — INV-9 / H8.
//
// The two-call schema-create protocol: an ownership-checked propose MCP tool
// MINTS one of these (no write); the human-confirm UI then calls the token-gated
// /v1 confirm endpoint, which is the ONLY path that creates schema. There is no
// MCP tool that creates schema, so a buggy/compromised consumer routing through
// the gateway can mint a token but never create a kind/attribute (threat S12).
//
// The token is a stateless HMAC over {user, book, op, params, exp}, keyed by the
// service JWT secret with a domain separator so it can never be confused with a
// real JWT (and is never fed to the JWT verifier). Forging one requires the JWT
// secret — i.e. a full service compromise, which is out of scope (game over for
// every /v1 write, not just this one).

const (
	schemaTokenDomain = "gloss-schema-confirm:v1|" // domain separator (never a JWT)
	schemaTokenTTL    = 10 * time.Minute           // human has time to read + confirm
	schemaOpKind      = "kind"
	schemaOpAttribute = "attribute"
)

var (
	ErrSchemaTokenInvalid = errors.New("schema confirm token is invalid")
	ErrSchemaTokenExpired = errors.New("schema confirm token has expired")
)

// schemaClaims is the signed payload. Params is the opaque create-spec captured
// at propose time (resolved kind_id for attributes, validated code/name, etc.) —
// the confirm step trusts it because it is inside the HMAC.
type schemaClaims struct {
	UserID uuid.UUID       `json:"u"`
	BookID uuid.UUID       `json:"b"`
	Op     string          `json:"op"` // schemaOpKind | schemaOpAttribute
	Params json.RawMessage `json:"p"`
	Exp    int64           `json:"exp"` // unix seconds
}

// mintSchemaToken signs a confirm token bound to user+book+op+params+expiry.
// secret is the service JWT secret (≥32 chars, env-provided); empty secret is a
// misconfiguration and yields an empty token (the caller treats that as "cannot
// mint" → fail closed).
func mintSchemaToken(secret string, userID, bookID uuid.UUID, op string, params json.RawMessage, now time.Time) string {
	if secret == "" {
		return ""
	}
	claims := schemaClaims{
		UserID: userID, BookID: bookID, Op: op, Params: params,
		Exp: now.Add(schemaTokenTTL).Unix(),
	}
	payload, err := json.Marshal(claims)
	if err != nil {
		return ""
	}
	payloadB64 := base64.RawURLEncoding.EncodeToString(payload)
	sig := schemaTokenSign(secret, payloadB64)
	return payloadB64 + "." + base64.RawURLEncoding.EncodeToString(sig)
}

// verifySchemaToken checks the signature (constant-time) and expiry, returning
// the claims. Signature/format problems → ErrSchemaTokenInvalid; a valid but
// stale token → ErrSchemaTokenExpired (distinct so the UI can say "re-propose").
func verifySchemaToken(secret, token string, now time.Time) (schemaClaims, error) {
	var zero schemaClaims
	if secret == "" {
		return zero, ErrSchemaTokenInvalid
	}
	parts := strings.Split(token, ".")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return zero, ErrSchemaTokenInvalid
	}
	sig, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return zero, ErrSchemaTokenInvalid
	}
	expected := schemaTokenSign(secret, parts[0])
	if subtle.ConstantTimeCompare(sig, expected) != 1 {
		return zero, ErrSchemaTokenInvalid
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return zero, ErrSchemaTokenInvalid
	}
	var claims schemaClaims
	if err := json.Unmarshal(payload, &claims); err != nil {
		return zero, ErrSchemaTokenInvalid
	}
	if claims.Op != schemaOpKind && claims.Op != schemaOpAttribute {
		return zero, ErrSchemaTokenInvalid
	}
	if now.Unix() >= claims.Exp {
		return zero, ErrSchemaTokenExpired
	}
	return claims, nil
}

func schemaTokenSign(secret, payloadB64 string) []byte {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(schemaTokenDomain))
	mac.Write([]byte(payloadB64))
	return mac.Sum(nil)
}
