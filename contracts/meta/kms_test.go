package meta

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
)

// fakePIIReader is a map-backed PIIReader for crypto-shred semantic tests.
type fakePIIReader struct {
	pii map[uuid.UUID]PIIRow
	kek map[uuid.UUID]KEKRow
}

func newFakePIIReader() *fakePIIReader {
	return &fakePIIReader{
		pii: make(map[uuid.UUID]PIIRow),
		kek: make(map[uuid.UUID]KEKRow),
	}
}

func (f *fakePIIReader) ReadPIIRow(_ context.Context, u uuid.UUID) (PIIRow, error) {
	r, ok := f.pii[u]
	if !ok {
		return PIIRow{}, ErrPIINotFound
	}
	return r, nil
}

func (f *fakePIIReader) ReadKEKRow(_ context.Context, k uuid.UUID) (KEKRow, error) {
	r, ok := f.kek[k]
	if !ok {
		return KEKRow{}, ErrPIINotFound
	}
	return r, nil
}

func uuidFromHexT(t *testing.T, s string) uuid.UUID {
	t.Helper()
	u, err := uuid.Parse(s)
	if err != nil {
		t.Fatalf("uuid.Parse(%q): %v", s, err)
	}
	return u
}

func seedHappyUser(t *testing.T) (*fakePIIReader, uuid.UUID, uuid.UUID) {
	t.Helper()
	user := uuidFromHexT(t, "11111111-1111-1111-1111-111111111111")
	kek := uuidFromHexT(t, "22222222-2222-2222-2222-222222222222")
	r := newFakePIIReader()
	// Note: tests use deterministic placeholder ciphertext envelope. NEVER real key bytes.
	// The bytes here are NOT real KMS ciphertext — they're a stand-in for the
	// DeterministicTestKMS which ignores the envelope content.
	r.pii[user] = PIIRow{
		UserRefID:     user,
		KEKID:         kek,
		EncryptedBlob: []byte("test-ciphertext-not-real-aes-gcm-envelope-XXX"),
		BlobSchemaVer: 1,
		LastRotatedAt: 1_700_000_000_000_000_000,
		ErasedAt:      nil,
	}
	r.kek[kek] = KEKRow{
		KEKID:       kek,
		UserRefID:   user,
		KeyMaterial: []byte("test-ciphertext-not-real-key-material"),
		KMSKeyRef:   "test-kms:fake-key-alias",
		DestroyedAt: nil,
	}
	return r, user, kek
}

// TestOpenPII_HappyPath verifies the green path returns plaintext.
func TestOpenPII_HappyPath(t *testing.T) {
	r, user, _ := seedHappyUser(t)
	kms := &DeterministicTestKMS{FixedPlaintext: []byte(`{"email":"test@example.com"}`)}

	rec, err := OpenPII(context.Background(), kms, r, user)
	if err != nil {
		t.Fatalf("OpenPII: %v", err)
	}
	if string(rec.Plaintext) != `{"email":"test@example.com"}` {
		t.Errorf("plaintext mismatch: %s", rec.Plaintext)
	}
	if rec.BlobSchemaVer != 1 {
		t.Errorf("schema ver: got %d want 1", rec.BlobSchemaVer)
	}
	if len(kms.Calls) != 1 {
		t.Fatalf("expected 1 KMS Decrypt call, got %d", len(kms.Calls))
	}
	// AAD must be user_ref_id || kek_id (32 bytes total)
	if len(kms.Calls[0].AAD) != 32 {
		t.Errorf("AAD length: got %d want 32", len(kms.Calls[0].AAD))
	}
	// 3-tier wiring (076 Slice B): OpenPII MUST pass the wrapped KEK
	// (kek.KeyMaterial) into DecryptInput.KeyMaterial — a real adapter
	// KMS-decrypts it to recover the KEK. The test KMS ignores it, so without
	// this assertion a regression dropping the field would fail-closed only in
	// production.
	if string(kms.Calls[0].KeyMaterial) != "test-ciphertext-not-real-key-material" {
		t.Errorf("OpenPII did not pass kek.KeyMaterial into DecryptInput.KeyMaterial; got %q", kms.Calls[0].KeyMaterial)
	}
}

// TestOpenPII_CryptoShred_KEKDestroyed verifies that nulling/destroying the
// KEK makes the blob unreadable — this is THE crypto-shred contract for
// L1.A-2 §2.2 (GDPR Art. 17 erasure). The KMS adapter MUST NOT be called
// because the destroyed_at check short-circuits before any KMS round-trip.
func TestOpenPII_CryptoShred_KEKDestroyed(t *testing.T) {
	r, user, kek := seedHappyUser(t)
	// Crypto-shred: set destroyed_at on the KEK.
	now := int64(1_700_000_100_000_000_000)
	row := r.kek[kek]
	row.DestroyedAt = &now
	r.kek[kek] = row

	kms := &DeterministicTestKMS{FixedPlaintext: []byte("should-never-be-returned")}
	rec, err := OpenPII(context.Background(), kms, r, user)

	if !errors.Is(err, ErrPIIErased) {
		t.Fatalf("want ErrPIIErased after KEK destroyed, got %v", err)
	}
	if rec != nil {
		t.Errorf("expected nil record, got %+v", rec)
	}
	// CRITICAL: KMS must NOT have been called — destroyed_at short-circuits.
	if len(kms.Calls) != 0 {
		t.Errorf("KMS was called %d times after crypto-shred — destroyed_at must short-circuit", len(kms.Calls))
	}
}

// TestOpenPII_RegistryErasedTombstone also returns ErrPIIErased even if the
// KEK row hasn't been destroyed yet (race between the erasure stages).
func TestOpenPII_RegistryErasedTombstone(t *testing.T) {
	r, user, _ := seedHappyUser(t)
	now := int64(1_700_000_100_000_000_000)
	row := r.pii[user]
	row.ErasedAt = &now
	r.pii[user] = row

	kms := &DeterministicTestKMS{FixedPlaintext: []byte("nope")}
	_, err := OpenPII(context.Background(), kms, r, user)
	if !errors.Is(err, ErrPIIErased) {
		t.Fatalf("want ErrPIIErased on erased_at tombstone, got %v", err)
	}
	if len(kms.Calls) != 0 {
		t.Errorf("KMS called %d times after registry tombstone — must short-circuit", len(kms.Calls))
	}
}

// TestOpenPII_UnknownUser surfaces ErrPIINotFound.
func TestOpenPII_UnknownUser(t *testing.T) {
	r := newFakePIIReader()
	kms := &DeterministicTestKMS{}
	user := uuidFromHexT(t, "99999999-9999-9999-9999-999999999999")
	_, err := OpenPII(context.Background(), kms, r, user)
	if !errors.Is(err, ErrPIINotFound) {
		t.Fatalf("want ErrPIINotFound, got %v", err)
	}
}

// TestOpenPII_KMSUnavailable bubbles up transient KMS errors.
func TestOpenPII_KMSUnavailable(t *testing.T) {
	r, user, _ := seedHappyUser(t)
	kms := &DeterministicTestKMS{FailWith: ErrKMSUnavailable}
	_, err := OpenPII(context.Background(), kms, r, user)
	if !errors.Is(err, ErrKMSUnavailable) {
		t.Fatalf("want ErrKMSUnavailable, got %v", err)
	}
}

// TestOpenPII_RequiresKMS guards against nil-injection.
func TestOpenPII_RequiresKMS(t *testing.T) {
	r := newFakePIIReader()
	u := uuidFromHexT(t, "11111111-1111-1111-1111-111111111111")
	_, err := OpenPII(context.Background(), nil, r, u)
	if err == nil || !errorContains(err, "OpenPII requires a KMSClient") {
		t.Errorf("want KMSClient required error, got %v", err)
	}
	_, err = OpenPII(context.Background(), &DeterministicTestKMS{}, nil, u)
	if err == nil || !errorContains(err, "OpenPII requires a PIIReader") {
		t.Errorf("want PIIReader required error, got %v", err)
	}
}

// TestOpenPII_KEKMissingButRegistryActive — defensive: registry points to a
// kek_id that doesn't exist (data drift / non-prod cleanup); surface
// ErrPIINotFound rather than silently decrypting against the wrong KEK.
func TestOpenPII_KEKMissingButRegistryActive(t *testing.T) {
	r, user, _ := seedHappyUser(t)
	// Remove the KEK row but leave registry pointing to it.
	for k := range r.kek {
		delete(r.kek, k)
	}
	kms := &DeterministicTestKMS{FixedPlaintext: []byte("nope")}
	_, err := OpenPII(context.Background(), kms, r, user)
	if !errors.Is(err, ErrPIINotFound) {
		t.Fatalf("want ErrPIINotFound when KEK gone, got %v", err)
	}
}
