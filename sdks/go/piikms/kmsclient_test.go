package piikms

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"testing"

	kmstypes "github.com/aws/aws-sdk-go-v2/service/kms/types"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/contracts/pii"
)

// TestIsAlreadyPendingDeletion covers the D-PIIKMS-DESTROY-TOCTOU predicate that
// makes a concurrent co-tenant double-schedule benign — including against the
// REAL aws-sdk KMSInvalidStateException type + wrapping + case, which the
// PG-gated concurrent test (local-only, timing-dependent) does not guarantee.
func TestIsAlreadyPendingDeletion(t *testing.T) {
	msg := "arn:aws:kms:us-east-1:111122223333:key/abcd is pending deletion."
	awsTyped := &kmstypes.KMSInvalidStateException{Message: &msg}

	cases := []struct {
		name string
		err  error
		want bool
	}{
		{"nil", nil, false},
		{"real aws KMSInvalidStateException", awsTyped, true},
		{"wrapped aws typed error", fmt.Errorf("schedule deletion: %w", awsTyped), true},
		{"plain string match", errors.New("KMSInvalidStateException: ... is pending deletion"), true},
		{"case-insensitive", errors.New("Key Is Pending Deletion"), true},
		{"unrelated KMS error", errors.New("KMSInvalidStateException: key disabled"), false},
		{"throttling", errors.New("ThrottlingException: rate exceeded"), false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := isAlreadyPendingDeletion(c.err); got != c.want {
				t.Errorf("isAlreadyPendingDeletion(%v) = %v, want %v", c.err, got, c.want)
			}
		})
	}
}

// Compile-time: the adapters satisfy the cycle-3 contracts.
var (
	_ meta.KMSClient = (*AWSKMSClient)(nil)
	_ pii.KEKManager = (*PgKEKManager)(nil)
)

const testKeyRef = "aws-kms:test-key-1234"

func roundTripSetup(t *testing.T) (*AWSKMSClient, []byte, []byte, []byte) {
	t.Helper()
	c := NewAWSKMSClient(newFakeKMS())
	kek, keyMaterial, err := c.ProvisionKEK(context.Background(), testKeyRef)
	if err != nil {
		t.Fatalf("ProvisionKEK: %v", err)
	}
	if len(kek) != kekLen {
		t.Fatalf("KEK len = %d, want %d", len(kek), kekLen)
	}
	aad := meta.PIIAAD(uuid.New(), uuid.New())
	return c, kek, keyMaterial, aad
}

func TestRoundTrip_ProvisionEncryptDecrypt(t *testing.T) {
	c, kek, keyMaterial, aad := roundTripSetup(t)
	payload := []byte(`{"email":"alice@example.com","name":"Alice"}`)

	env, err := c.Encrypt(kek, payload, aad)
	if err != nil {
		t.Fatalf("Encrypt: %v", err)
	}
	if env[0] != envelopeVersion {
		t.Errorf("envelope version = %d", env[0])
	}
	out, err := c.Decrypt(context.Background(), meta.DecryptInput{
		KMSKeyRef: testKeyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: aad,
	})
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if !bytes.Equal(out.Plaintext, payload) {
		t.Errorf("round-trip mismatch: got %q", out.Plaintext)
	}
}

func TestDecrypt_AADMismatchRejected(t *testing.T) {
	c, kek, keyMaterial, aad := roundTripSetup(t)
	env, _ := c.Encrypt(kek, []byte("secret"), aad)
	wrongAAD := meta.PIIAAD(uuid.New(), uuid.New()) // different user/kek
	_, err := c.Decrypt(context.Background(), meta.DecryptInput{
		KMSKeyRef: testKeyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: wrongAAD,
	})
	if err == nil {
		t.Fatal("expected AAD mismatch to fail the GCM tag")
	}
}

func TestDecrypt_TamperRejected(t *testing.T) {
	c, kek, keyMaterial, aad := roundTripSetup(t)
	env, _ := c.Encrypt(kek, []byte("secret-payload"), aad)
	env[len(env)-1] ^= 0xFF // flip a ciphertext/tag bit
	_, err := c.Decrypt(context.Background(), meta.DecryptInput{
		KMSKeyRef: testKeyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: aad,
	})
	if err == nil {
		t.Fatal("expected tampered ciphertext to fail")
	}
}

func TestDecrypt_BadEnvelopeRejected(t *testing.T) {
	c, _, keyMaterial, aad := roundTripSetup(t)
	for name, env := range map[string][]byte{
		"too short":   {0x01, 0x02},
		"bad version": append([]byte{0x09}, make([]byte, nonceLen+16)...),
	} {
		_, err := c.Decrypt(context.Background(), meta.DecryptInput{
			KMSKeyRef: testKeyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: aad,
		})
		if err == nil {
			t.Errorf("%s: expected rejection", name)
		}
	}
}

func TestEncrypt_FreshNoncePerCall(t *testing.T) {
	c, kek, _, aad := roundTripSetup(t)
	a, _ := c.Encrypt(kek, []byte("same payload"), aad)
	b, _ := c.Encrypt(kek, []byte("same payload"), aad)
	// Same KEK + same plaintext must NOT produce identical envelopes (nonce
	// reuse under a fixed GCM key is catastrophic).
	if bytes.Equal(a[1:1+nonceLen], b[1:1+nonceLen]) {
		t.Fatal("nonce reused across Encrypt calls under the same KEK")
	}
	if bytes.Equal(a, b) {
		t.Fatal("identical envelopes for same KEK+plaintext (nonce not fresh)")
	}
}

func TestDecrypt_ErrorMapping(t *testing.T) {
	cases := map[string]struct {
		injected error
		want     error
	}{
		"pending-deletion → erased": {&kmstypes.KMSInvalidStateException{}, meta.ErrPIIErased},
		"not-found → erased":        {&kmstypes.NotFoundException{}, meta.ErrPIIErased},
		"disabled → erased":         {&kmstypes.DisabledException{}, meta.ErrPIIErased},
		"unavailable → transient":   {&kmstypes.KeyUnavailableException{}, meta.ErrKMSUnavailable},
		"throttling → transient":    {&kmstypes.LimitExceededException{}, meta.ErrKMSUnavailable},
		"unknown → transient":       {errors.New("boom"), meta.ErrKMSUnavailable},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			fk := newFakeKMS()
			fk.decryptErr = tc.injected
			c := NewAWSKMSClient(fk)
			_, err := c.Decrypt(context.Background(), meta.DecryptInput{
				KMSKeyRef: testKeyRef, KeyMaterial: []byte("x"), Ciphertext: make([]byte, 32), AAD: nil,
			})
			if !errors.Is(err, tc.want) {
				t.Errorf("%s: err=%v, want wrap of %v", name, err, tc.want)
			}
		})
	}
}

func TestDecrypt_EmptyKeyMaterialRejected(t *testing.T) {
	c := NewAWSKMSClient(newFakeKMS())
	_, err := c.Decrypt(context.Background(), meta.DecryptInput{KMSKeyRef: testKeyRef, Ciphertext: make([]byte, 32)})
	if err == nil {
		t.Fatal("expected empty KeyMaterial to be rejected")
	}
}

func TestVersionedAAD_BindsVersion(t *testing.T) {
	aad := []byte("user-kek-aad")
	got := versionedAAD(envelopeVersion, aad)
	if got[0] != envelopeVersion || !bytes.Equal(got[1:], aad) {
		t.Fatalf("versionedAAD = %v, want [%d]+aad", got, envelopeVersion)
	}
	// Different versions MUST yield different AAD (so a future multi-version
	// openEnvelope can't be downgraded — the AEAD tag would differ).
	if bytes.Equal(versionedAAD(1, aad), versionedAAD(2, aad)) {
		t.Fatal("versionedAAD does not differentiate versions")
	}
	// Must not alias/mutate the caller's slice.
	if &got[1] == &aad[0] {
		t.Fatal("versionedAAD aliases the caller aad")
	}
}

// TestContract_AADMustMatchKEKID locks the integration contract a future
// provisioner MUST follow (review-impl #4): the AAD's kek_id must match between
// Encrypt and Decrypt. Sealing under PIIAAD(user, kekA) and opening under
// PIIAAD(user, kekB) fails — so a provisioner that computes AAD with the wrong
// kek_id produces permanently-unreadable blobs (caught here, not in prod).
func TestContract_AADMustMatchKEKID(t *testing.T) {
	c, kek, keyMaterial, _ := roundTripSetup(t)
	user := uuid.New()
	kekA, kekB := uuid.New(), uuid.New()
	env, _ := c.Encrypt(kek, []byte("pii"), meta.PIIAAD(user, kekA))

	if _, err := c.Decrypt(context.Background(), meta.DecryptInput{
		KMSKeyRef: testKeyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: meta.PIIAAD(user, kekA),
	}); err != nil {
		t.Fatalf("matching kek_id should open: %v", err)
	}
	if _, err := c.Decrypt(context.Background(), meta.DecryptInput{
		KMSKeyRef: testKeyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: meta.PIIAAD(user, kekB),
	}); err == nil {
		t.Fatal("mismatched kek_id in AAD must fail to open")
	}
}

func TestArn_PrefixStripping(t *testing.T) {
	got, err := arn("aws-kms:arn:aws:kms:us-east-1:111:key/abc")
	if err != nil || got != "arn:aws:kms:us-east-1:111:key/abc" {
		t.Errorf("arn = %q, err=%v", got, err)
	}
	if _, err := arn("vault:secret/x"); err == nil {
		t.Error("expected non-aws-kms provider to be rejected")
	}
	if _, err := arn("aws-kms:"); err == nil {
		t.Error("expected empty key id to be rejected")
	}
}
