package adminjwt

import (
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"fmt"
)

// ParseRSAPublicKeyPEM decodes an RSA public key from a PEM-wrapped SPKI/PKIX
// document — exactly the format AWS KMS GetPublicKey returns (DER) once
// PEM-armored with a "PUBLIC KEY" block.
//
// It deliberately REJECTS the PKCS#1 "RSA PUBLIC KEY" block type: accepting
// both formats silently is a footgun, and KMS only ever emits SPKI. Pinning the
// one accepted shape means a wrong-format export fails fast at load time.
func ParseRSAPublicKeyPEM(pemBytes []byte) (*rsa.PublicKey, error) {
	block, _ := pem.Decode(pemBytes)
	if block == nil {
		return nil, fmt.Errorf("%w: no PEM block found", ErrVerify)
	}
	if block.Type != "PUBLIC KEY" {
		return nil, fmt.Errorf("%w: expected PEM block %q (SPKI/PKIX), got %q", ErrVerify, "PUBLIC KEY", block.Type)
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("%w: parse PKIX: %v", ErrVerify, err)
	}
	rsaPub, ok := pub.(*rsa.PublicKey)
	if !ok {
		return nil, fmt.Errorf("%w: not an RSA public key (%T)", ErrVerify, pub)
	}
	return rsaPub, nil
}

// KeyFingerprint is the canonical key id (kid) for an admin-signing key: the
// hex-encoded SHA-256 of the key's PKIX/SPKI DER encoding. Both the signer
// (auth-service, over the KMS public key) and the verifier (admin-cli, over its
// configured public key) compute it the same way, so a mismatch proves the two
// sides hold different keys.
func KeyFingerprint(pub *rsa.PublicKey) (string, error) {
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		return "", fmt.Errorf("%w: marshal PKIX: %v", ErrVerify, err)
	}
	sum := sha256.Sum256(der)
	return hex.EncodeToString(sum[:]), nil
}
