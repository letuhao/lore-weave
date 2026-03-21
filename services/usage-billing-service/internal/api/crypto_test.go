package api

import "testing"

func TestEncryptDecryptWithKeyRoundTrip(t *testing.T) {
	t.Parallel()

	key := []byte("12345678901234567890123456789012")
	plain := []byte("hello encrypted world")
	cipherText, err := encryptWithKey(key, plain)
	if err != nil {
		t.Fatalf("encryptWithKey failed: %v", err)
	}
	got, err := decryptWithKey(key, cipherText)
	if err != nil {
		t.Fatalf("decryptWithKey failed: %v", err)
	}
	if string(got) != string(plain) {
		t.Fatalf("round trip mismatch: got %q want %q", string(got), string(plain))
	}
}

func TestDecryptWithKeyRejectsInvalidCiphertext(t *testing.T) {
	t.Parallel()

	key := []byte("12345678901234567890123456789012")
	if _, err := decryptWithKey(key, "not-base64"); err == nil {
		t.Fatal("expected error for invalid ciphertext")
	}
}
