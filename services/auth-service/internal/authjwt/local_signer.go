package authjwt

import (
	"bytes"
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"fmt"
	"strings"

	"github.com/loreweave/foundation/contracts/adminjwt"
)

// LocalKeySigner is a DigestSigner backed by an in-process RSA private key loaded
// from a configured PEM. It is the DEV / SELF-HOSTED admin-signing path for stacks
// without AWS KMS — production should still use KMSSigner (the key never leaves
// KMS). The wire-assembly path (assembleRS256) is identical to KMS; only WHERE the
// private key lives differs. Unlike signertest.LocalRSASigner (test-only, ephemeral
// key), this loads a STABLE configured key so verifiers (glossary) can be given the
// matching public PEM.
type LocalKeySigner struct {
	key *rsa.PrivateKey
	kid string
}

// NewLocalKeySigner parses an RSA private key from a PKCS#8 ("PRIVATE KEY") or
// PKCS#1 ("RSA PRIVATE KEY") PEM block and pins its kid (KeyFingerprint of the
// public half — the same id the verifier computes).
func NewLocalKeySigner(pemBytes []byte) (*LocalKeySigner, error) {
	// Accept a single-line base64-encoded PEM too (convenient through env/compose).
	if !bytes.Contains(pemBytes, []byte("BEGIN")) {
		if dec, err := base64.StdEncoding.DecodeString(strings.TrimSpace(string(pemBytes))); err == nil {
			pemBytes = dec
		}
	}
	block, _ := pem.Decode(pemBytes)
	if block == nil {
		return nil, fmt.Errorf("authjwt: no PEM block in ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM")
	}
	var key *rsa.PrivateKey
	switch block.Type {
	case "RSA PRIVATE KEY": // PKCS#1
		k, err := x509.ParsePKCS1PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("authjwt: parse PKCS1 local key: %w", err)
		}
		key = k
	case "PRIVATE KEY": // PKCS#8
		k, err := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("authjwt: parse PKCS8 local key: %w", err)
		}
		rk, ok := k.(*rsa.PrivateKey)
		if !ok {
			return nil, fmt.Errorf("authjwt: local key is not RSA (%T)", k)
		}
		key = rk
	default:
		return nil, fmt.Errorf("authjwt: unexpected PEM block %q (want RSA PRIVATE KEY or PRIVATE KEY)", block.Type)
	}
	kid, err := adminjwt.KeyFingerprint(&key.PublicKey)
	if err != nil {
		return nil, fmt.Errorf("authjwt: fingerprint local key: %w", err)
	}
	return &LocalKeySigner{key: key, kid: kid}, nil
}

// KID implements DigestSigner.
func (s *LocalKeySigner) KID() string { return s.kid }

// PublicKey implements DigestSigner.
func (s *LocalKeySigner) PublicKey() *rsa.PublicKey { return &s.key.PublicKey }

// SignDigest implements DigestSigner — raw RSASSA-PKCS1-v1_5 over the SHA-256
// digest, byte-identical to the KMS signer's output shape.
func (s *LocalKeySigner) SignDigest(_ context.Context, sha256Digest []byte) ([]byte, error) {
	return rsa.SignPKCS1v15(rand.Reader, s.key, crypto.SHA256, sha256Digest)
}
