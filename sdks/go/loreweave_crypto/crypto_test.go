package loreweavecrypto

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"testing"
)

func mustKey(t *testing.T, secret string) []byte {
	t.Helper()
	k, err := DeriveKey(secret)
	if err != nil {
		t.Fatalf("DeriveKey(%q): %v", secret, err)
	}
	return k
}

func TestDEKRoundTripThroughEnvelope(t *testing.T) {
	ring := NewKeyring(mustKey(t, "kek-1"))
	dek, _ := NewDEK()
	uid := "alice"
	wrapped, ref, err := WrapDEK(ring, dek, uid)
	if err != nil {
		t.Fatal(err)
	}
	if ref != ring.ActiveRef() {
		t.Fatalf("key_ref mismatch: %q vs %q", ref, ring.ActiveRef())
	}
	got, err := UnwrapDEK(ring, wrapped, uid)
	if err != nil {
		t.Fatal(err)
	}
	if hex.EncodeToString(got) != hex.EncodeToString(dek) {
		t.Fatal("unwrapped DEK does not match")
	}
}

func TestContentRoundTripUnderUserDEK(t *testing.T) {
	dek, _ := NewDEK()
	pt := "diary: 今天很累 — meeting w/ Minh"
	ct, err := Encrypt(dek, pt, "chapter:1")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(ct, "Minh") {
		t.Fatal("ciphertext leaks plaintext")
	}
	got, err := Decrypt(dek, ct, "chapter:1")
	if err != nil {
		t.Fatal(err)
	}
	if got != pt {
		t.Fatalf("round-trip mismatch: %q", got)
	}
}

func TestWrongUserAADRefusesUnwrap(t *testing.T) {
	ring := NewKeyring(mustKey(t, "kek-1"))
	dek, _ := NewDEK()
	wrapped, _, _ := WrapDEK(ring, dek, "alice")
	if _, err := UnwrapDEK(ring, wrapped, "bob"); err == nil {
		t.Fatal("a wrapped DEK moved to another user's id must NOT unwrap (AAD binding)")
	}
}

func TestWrongContentAADRefusesDecrypt(t *testing.T) {
	dek, _ := NewDEK()
	ct, _ := Encrypt(dek, "secret", "chapter:1")
	if _, err := Decrypt(dek, ct, "chapter:2"); err == nil {
		t.Fatal("a ciphertext moved to another row's AAD must NOT decrypt")
	}
}

func TestTamperedCiphertextIsDetected(t *testing.T) {
	dek, _ := NewDEK()
	ct, _ := Encrypt(dek, "secret", "")
	// flip a char in the middle of the base64 blob
	b := []byte(ct)
	mid := len(b) / 2
	if b[mid] == 'A' {
		b[mid] = 'B'
	} else {
		b[mid] = 'A'
	}
	if _, err := Decrypt(dek, string(b), ""); err == nil {
		t.Fatal("tampered ciphertext must be DETECTED, not silently returned")
	}
}

func TestEncryptionIsNondeterministic(t *testing.T) {
	dek, _ := NewDEK()
	a, _ := Encrypt(dek, "same", "")
	b, _ := Encrypt(dek, "same", "")
	if a == b {
		t.Fatal("encryption must be nondeterministic (random nonce)")
	}
}

func TestKEKRotationDoesNotOrphanUser(t *testing.T) {
	old := NewKeyring(mustKey(t, "kek-1"))
	dek, _ := NewDEK()
	wrapped, _, _ := WrapDEK(old, dek, "alice")
	// rotate: kek-2 is active, kek-1 retired
	rotated := NewKeyring(mustKey(t, "kek-2"), mustKey(t, "kek-1"))
	got, err := UnwrapDEK(rotated, wrapped, "alice")
	if err != nil {
		t.Fatalf("rotation orphaned the user's DEK: %v", err)
	}
	if hex.EncodeToString(got) != hex.EncodeToString(dek) {
		t.Fatal("rotation unwrapped the wrong DEK")
	}
}

func TestDeriveKeyIsSHA256NotTruncation(t *testing.T) {
	got := mustKey(t, "abc")
	want := sha256.Sum256([]byte("abc"))
	if hex.EncodeToString(got) != hex.EncodeToString(want[:]) {
		t.Fatal("DeriveKey must be SHA-256 of the secret")
	}
	if _, err := DeriveKey(""); !errors.Is(err, ErrCrypto) {
		t.Fatal("empty key material must fail closed")
	}
}

// ── CROSS-LANGUAGE GOLDEN VECTORS ────────────────────────────────────────────
// Produced by sdks/python/loreweave_crypto (the Python SDK). This pins Go↔Python format parity: a
// drift in the cipher / key derivation / AAD / base64 would make one side's ciphertext unreadable by
// the other — a silent diary-data-loss class. Regenerate ONLY via the Python SDK if the format ever
// intentionally changes (and then it is a migration, not an edit).
const (
	goldenKEKSecret  = "golden-kek-secret-v1"
	goldenKEKRef     = "4e0daf803c4b3da5"
	goldenDEKHex     = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
	goldenUserID     = "11111111-1111-1111-1111-111111111111"
	goldenWrapped    = "PpD/hX8dfV0WRNUlmD0FF78IqcmCA6kSS7fF1H/EyCdZuk8wm6Ab+LIVa7UNuyR67mcnTpoSkHHWFQ4u"
	goldenContentAAD = "chapter:abc-123"
	goldenCiphertext = "pDSCzi5Wy4fM3/deGn37vrSfCWOLjAaypKMEypwdtl/qjSE/HB+mjJPIKhdU75ChZBf21dzhUts7B4cQ0rFwvYmORf+JQemIQ5OqYQE="
	goldenPlaintext  = "diary: 今天很累 déjà vu — meeting w/ Minh"
)

func TestGoldenVectors_PythonParity(t *testing.T) {
	ring := NewKeyring(mustKey(t, goldenKEKSecret))

	// key_ref parity (the rotation checklist reads this).
	if ring.ActiveRef() != goldenKEKRef {
		t.Fatalf("KeyRef drift: %q, python said %q", ring.ActiveRef(), goldenKEKRef)
	}

	// a DEK wrapped by Python must unwrap here.
	dek, err := UnwrapDEK(ring, goldenWrapped, goldenUserID)
	if err != nil {
		t.Fatalf("could not unwrap the Python-wrapped DEK: %v", err)
	}
	if hex.EncodeToString(dek) != goldenDEKHex {
		t.Fatalf("unwrapped DEK drift: %s vs %s", hex.EncodeToString(dek), goldenDEKHex)
	}

	// content encrypted by Python must decrypt here (same DEK + AAD).
	got, err := Decrypt(dek, goldenCiphertext, goldenContentAAD)
	if err != nil {
		t.Fatalf("could not decrypt the Python-encrypted content: %v", err)
	}
	if got != goldenPlaintext {
		t.Fatalf("decrypted content drift: %q vs %q", got, goldenPlaintext)
	}
}
