package loreweave_mcp

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

// Confirm-token spine (Tier-S/W). A stateless HMAC over the claims, keyed by a
// per-service secret with a domain separator so the token can never be confused
// with a real JWT. Forging one requires the secret — i.e. a full service
// compromise, out of scope.
//
// The token binds INTENT (descriptor + payload) + IDENTITY (user) + RESOURCE +
// EXPIRY. The propose tool mints it (no write); the per-domain
// /v1/<domain>/actions/confirm route verifies it and is the ONLY write path
// (INV-9). The descriptor is the confused-deputy guard: confirm MUST check that
// the token's descriptor matches the action being confirmed, so a token minted
// for "book.delete" can never confirm "book.publish".
//
// Single-use, if required, is enforced at confirm time by the service (e.g.
// recording a hash of the token, or the (user,resource,descriptor,exp) tuple) —
// it is not in the stateless token itself.
//
// COMPOSE-A reconciliation note: this scheme is the canonical confirm spine
// shared with the Python kit (sdks/python/loreweave_mcp) at the API + claim
// level — same signature `(secret, user, resource, descriptor, payload, ttl)`,
// same claim fields, same domain separator. Tokens are minted AND verified
// inside one service (never across languages), so byte-level wire interop is
// deliberately not a contract; the alignment is conceptual.
const confirmTokenDomain = "lw-action-confirm:v1|"

var (
	// ErrConfirmTokenInvalid — bad signature, malformed, or empty secret.
	ErrConfirmTokenInvalid = errors.New("confirm token is invalid")
	// ErrConfirmTokenExpired — signature valid but past expiry (distinct so the
	// UI can say "re-propose" rather than "tampered").
	ErrConfirmTokenExpired = errors.New("confirm token has expired")
)

// ConfirmClaims is the verified payload of a confirm token. Payload is the opaque
// action-spec captured at propose time (resolved ids, validated values); confirm
// trusts it because it is inside the HMAC, but the service SHOULD still re-check
// user/resource against the live request and re-validate the payload against
// current state before executing.
type ConfirmClaims struct {
	UserID     uuid.UUID       `json:"u"`           // the proposing user (re-checked at confirm)
	ResourceID uuid.UUID       `json:"r"`           // the resource the action targets
	Descriptor string          `json:"d"`           // intent (e.g. "book.publish") — confirm MUST match this
	Payload    json.RawMessage `json:"p,omitempty"` // opaque action-spec
	Exp        int64           `json:"exp"`         // unix seconds
}

// MintConfirmToken signs a confirm token binding userID + resourceID + descriptor
// + payload, stamped with now+ttl. The secret is supplied by the caller (loaded
// from the service's own env — never a literal here); an empty secret fails
// closed with ErrConfirmTokenInvalid (the service must be configured to mint).
func MintConfirmToken(secret string, userID, resourceID uuid.UUID, descriptor string, payload any, ttl time.Duration) (string, error) {
	if secret == "" {
		return "", ErrConfirmTokenInvalid
	}
	var raw json.RawMessage
	if payload != nil {
		b, err := json.Marshal(payload)
		if err != nil {
			return "", ErrConfirmTokenInvalid
		}
		raw = b
	}
	claims := ConfirmClaims{
		UserID:     userID,
		ResourceID: resourceID,
		Descriptor: descriptor,
		Payload:    raw,
		Exp:        time.Now().Add(ttl).Unix(),
	}
	body, err := json.Marshal(claims)
	if err != nil {
		return "", ErrConfirmTokenInvalid
	}
	payloadB64 := base64.RawURLEncoding.EncodeToString(body)
	sig := confirmTokenSign(secret, payloadB64)
	return payloadB64 + "." + base64.RawURLEncoding.EncodeToString(sig), nil
}

// VerifyConfirmToken checks the HMAC signature (constant-time) then expiry, using
// the caller-supplied secret. A bad signature / format / empty secret →
// ErrConfirmTokenInvalid; a signature-valid but stale token →
// ErrConfirmTokenExpired. On success returns the bound claims; the caller MUST
// re-check user/resource against the live request, confirm the descriptor matches
// the action, and (if one-shot) record single-use.
func VerifyConfirmToken(secret, tok string) (ConfirmClaims, error) {
	var zero ConfirmClaims
	if secret == "" {
		return zero, ErrConfirmTokenInvalid
	}
	parts := strings.Split(tok, ".")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return zero, ErrConfirmTokenInvalid
	}
	sig, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return zero, ErrConfirmTokenInvalid
	}
	expected := confirmTokenSign(secret, parts[0])
	if subtle.ConstantTimeCompare(sig, expected) != 1 {
		return zero, ErrConfirmTokenInvalid
	}
	body, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return zero, ErrConfirmTokenInvalid
	}
	var claims ConfirmClaims
	if err := json.Unmarshal(body, &claims); err != nil {
		return zero, ErrConfirmTokenInvalid
	}
	if time.Now().Unix() >= claims.Exp {
		return zero, ErrConfirmTokenExpired
	}
	return claims, nil
}

func confirmTokenSign(secret, payloadB64 string) []byte {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(confirmTokenDomain))
	mac.Write([]byte(payloadB64))
	return mac.Sum(nil)
}
