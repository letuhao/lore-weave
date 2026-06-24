// Package signertest provides an in-process DigestSigner for tests ONLY.
//
// It signs with a real crypto/rsa.SignPKCS1v15(SHA-256) key, producing the
// byte-identical raw RSASSA-PKCS1-v1_5 signature shape that AWS KMS returns —
// so a test that mints via this signer exercises the exact wire-assembly path
// production uses, with the only difference being WHERE the private key lives.
//
// PRODUCTION MUST NEVER IMPORT THIS PACKAGE. cmd/auth-service wires KMSSigner.
// (No build tag is used because non-test packages may legitimately import it
// from their own _test.go files; the invariant is enforced by review + the fact
// that main.go does not import it.)
package signertest

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"

	"github.com/loreweave/foundation/contracts/adminjwt"
)

// LocalRSASigner is a test DigestSigner backed by an in-memory RSA key.
type LocalRSASigner struct {
	key *rsa.PrivateKey
	kid string
}

// New builds a LocalRSASigner from an existing RSA private key.
func New(key *rsa.PrivateKey) (*LocalRSASigner, error) {
	kid, err := adminjwt.KeyFingerprint(&key.PublicKey)
	if err != nil {
		return nil, err
	}
	return &LocalRSASigner{key: key, kid: kid}, nil
}

// Generate builds a LocalRSASigner with a freshly generated key.
func Generate(bits int) (*LocalRSASigner, error) {
	key, err := rsa.GenerateKey(rand.Reader, bits)
	if err != nil {
		return nil, err
	}
	return New(key)
}

// PublicKey exposes the verifying key (tests verify with adminjwt.Verify).
func (s *LocalRSASigner) PublicKey() *rsa.PublicKey { return &s.key.PublicKey }

// KID implements authjwt.DigestSigner.
func (s *LocalRSASigner) KID() string { return s.kid }

// SignDigest implements authjwt.DigestSigner with real PKCS1v15 over the digest.
func (s *LocalRSASigner) SignDigest(_ context.Context, sha256Digest []byte) ([]byte, error) {
	return rsa.SignPKCS1v15(rand.Reader, s.key, crypto.SHA256, sha256Digest)
}
