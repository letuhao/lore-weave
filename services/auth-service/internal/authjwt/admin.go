package authjwt

import (
	"context"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"

	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	kmstypes "github.com/aws/aws-sdk-go-v2/service/kms/types"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/adminjwt"
)

// DigestSigner signs the SHA-256 digest of a JWT signing-input and returns a
// RAW RSASSA-PKCS1-v1_5 signature (the same shape AWS KMS Sign returns and the
// same shape crypto/rsa.SignPKCS1v15 returns). The token-assembly path in this
// file is identical regardless of which impl is used — only this one primitive
// differs — so a unit test with the in-process signer exercises the exact bytes
// the KMS signer produces in production.
type DigestSigner interface {
	// SignDigest returns the raw RSA signature over the given SHA-256 digest.
	SignDigest(ctx context.Context, sha256Digest []byte) ([]byte, error)
	// KID is the key id written into the JWT header (KeyFingerprint of the
	// signing key's public half), so a verifier can prove key identity.
	KID() string
	// PublicKey is the verifying half of the signing key. auth-service uses it
	// to verify admin tokens it previously issued (e.g. the two actor tokens at
	// break-glass mint time).
	PublicKey() *rsa.PublicKey
}

// Issued is the result of minting an admin/break-glass token.
type Issued struct {
	Token     string
	JTI       uuid.UUID
	IssuedAt  time.Time
	ExpiresAt time.Time
}

// jwtHeader is marshaled with a FIXED field order so the wire bytes are
// deterministic (golden-vector test depends on this). golang-jwt's verifier
// parses the header into a map and does not care about field order.
type jwtHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
	Kid string `json:"kid"`
}

// assembleRS256 builds and signs a standard RS256 JWS:
//
//	signingInput = base64url(header) "." base64url(claims)
//	jwt          = signingInput "." base64url( SignDigest(SHA256(signingInput)) )
//
// This is the single load-bearing wire contract shared by the KMS and in-process
// signers.
func assembleRS256(ctx context.Context, signer DigestSigner, claims adminjwt.AdminClaims) (string, error) {
	hb, err := json.Marshal(jwtHeader{Alg: "RS256", Typ: "JWT", Kid: signer.KID()})
	if err != nil {
		return "", fmt.Errorf("authjwt: marshal header: %w", err)
	}
	cb, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("authjwt: marshal claims: %w", err)
	}
	signingInput := base64.RawURLEncoding.EncodeToString(hb) + "." + base64.RawURLEncoding.EncodeToString(cb)
	sum := sha256.Sum256([]byte(signingInput))
	sig, err := signer.SignDigest(ctx, sum[:])
	if err != nil {
		return "", fmt.Errorf("authjwt: sign digest: %w", err)
	}
	return signingInput + "." + base64.RawURLEncoding.EncodeToString(sig), nil
}

func mint(ctx context.Context, signer DigestSigner, subject uuid.UUID, role string, scopes []string, breakGlass bool, ttl time.Duration) (Issued, error) {
	now := time.Now()
	jti, err := uuid.NewV7()
	if err != nil {
		return Issued{}, fmt.Errorf("authjwt: jti: %w", err)
	}
	exp := now.Add(ttl)
	claims := adminjwt.AdminClaims{
		Role:       role,
		Scopes:     scopes,
		BreakGlass: breakGlass,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   subject.String(),
			Issuer:    adminjwt.Issuer,
			Audience:  jwt.ClaimStrings{adminjwt.Audience},
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

// SignAdmin mints a normal admin token (break_glass=false).
func SignAdmin(ctx context.Context, signer DigestSigner, subject uuid.UUID, role string, scopes []string, ttl time.Duration) (Issued, error) {
	return mint(ctx, signer, subject, role, scopes, false, ttl)
}

// SignBreakGlass mints a break-glass token (break_glass=true). The caller MUST
// have already enforced adminjwt.ValidateBreakGlass (dual-actor, reason, ticket,
// ttl<=24h) before calling this.
func SignBreakGlass(ctx context.Context, signer DigestSigner, subject uuid.UUID, role string, scopes []string, ttl time.Duration) (Issued, error) {
	return mint(ctx, signer, subject, role, scopes, true, ttl)
}

// KMSSigner signs via AWS KMS asymmetric Sign — the RSA private key never leaves
// KMS. Production signer.
type KMSSigner struct {
	client *awskms.Client
	keyID  string
	kid    string
	pub    *rsa.PublicKey
}

// NewKMSSigner constructs a KMS signer and pins its kid by fetching the public
// key (GetPublicKey returns SPKI/PKIX DER) and fingerprinting it. Fails closed
// if the key is missing, unreachable, or not RSA.
func NewKMSSigner(ctx context.Context, client *awskms.Client, keyID string) (*KMSSigner, error) {
	out, err := client.GetPublicKey(ctx, &awskms.GetPublicKeyInput{KeyId: &keyID})
	if err != nil {
		return nil, fmt.Errorf("authjwt: kms GetPublicKey: %w", err)
	}
	pub, err := x509.ParsePKIXPublicKey(out.PublicKey)
	if err != nil {
		return nil, fmt.Errorf("authjwt: parse kms public key (PKIX): %w", err)
	}
	rsaPub, ok := pub.(*rsa.PublicKey)
	if !ok {
		return nil, fmt.Errorf("authjwt: kms key %s is not RSA (%T)", keyID, pub)
	}
	kid, err := adminjwt.KeyFingerprint(rsaPub)
	if err != nil {
		return nil, fmt.Errorf("authjwt: fingerprint kms key: %w", err)
	}
	return &KMSSigner{client: client, keyID: keyID, kid: kid, pub: rsaPub}, nil
}

// KID implements DigestSigner.
func (s *KMSSigner) KID() string { return s.kid }

// PublicKey implements DigestSigner.
func (s *KMSSigner) PublicKey() *rsa.PublicKey { return s.pub }

// SignDigest implements DigestSigner via kms.Sign with MessageType=DIGEST and
// RSASSA_PKCS1_V1_5_SHA_256 (= RS256). KMS returns the raw signature bytes.
func (s *KMSSigner) SignDigest(ctx context.Context, sha256Digest []byte) ([]byte, error) {
	out, err := s.client.Sign(ctx, &awskms.SignInput{
		KeyId:            &s.keyID,
		Message:          sha256Digest,
		MessageType:      kmstypes.MessageTypeDigest,
		SigningAlgorithm: kmstypes.SigningAlgorithmSpecRsassaPkcs1V15Sha256,
	})
	if err != nil {
		return nil, fmt.Errorf("authjwt: kms Sign: %w", err)
	}
	return out.Signature, nil
}
