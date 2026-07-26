package api

import (
	"testing"

	"github.com/loreweave/agent-registry-service/internal/config"
)

func testCfg() *config.Config {
	return &config.Config{
		HTTPAddr:             ":8099",
		JWTSecret:            "test_jwt_secret_at_least_32_chars_long!!",
		InternalServiceToken: "test_internal_token",
		VaultKey:             "test_vault_key_at_least_32_chars_long!!!",
	}
}

func TestVault_Roundtrip(t *testing.T) {
	s := NewServer(nil, testCfg())
	secret := "oauth-refresh-token-super-sensitive"
	ct, keyRef, err := s.encryptSecret(secret)
	if err != nil {
		t.Fatalf("encrypt: %v", err)
	}
	if ct == secret {
		t.Fatal("ciphertext equals plaintext")
	}
	if keyRef == "" {
		t.Fatal("empty keyRef")
	}
	got, err := s.decryptSecret(ct)
	if err != nil {
		t.Fatalf("decrypt: %v", err)
	}
	if got != secret {
		t.Fatalf("roundtrip mismatch: %q != %q", got, secret)
	}
	// distinct nonce per write ⇒ different ciphertext for the same input
	ct2, _, _ := s.encryptSecret(secret)
	if ct2 == ct {
		t.Fatal("nonce reuse — identical ciphertext for repeated encrypt")
	}
}

func TestVault_EmptyDecrypt(t *testing.T) {
	s := NewServer(nil, testCfg())
	got, err := s.decryptSecret("")
	if err != nil || got != "" {
		t.Fatalf("empty ciphertext should decrypt to empty, got %q err %v", got, err)
	}
}

func TestPluginNameRegex(t *testing.T) {
	valid := []string{"io.github.user/pack", "dev.loreweave/core-tools", "a.b/c", "x1/y2"}
	invalid := []string{"", "no-slash", "UPPER/case", "/leading", "trailing/", "a//b", "a/b/c", "空/名"}
	for _, v := range valid {
		if !pluginNameRe.MatchString(v) {
			t.Errorf("expected valid: %q", v)
		}
	}
	for _, v := range invalid {
		if pluginNameRe.MatchString(v) {
			t.Errorf("expected invalid: %q", v)
		}
	}
}

func TestClampLimit(t *testing.T) {
	cases := map[string]int{"": 20, "0": 20, "-5": 20, "10": 10, "100": 100, "500": 100, "abc": 20}
	for in, want := range cases {
		if got := clampLimit(in); got != want {
			t.Errorf("clampLimit(%q) = %d, want %d", in, got, want)
		}
	}
}

func TestDeriveKey_Always32(t *testing.T) {
	for _, s := range []string{"", "short", "test_vault_key_at_least_32_chars_long!!!", "way-too-long-key-way-too-long-key-way-too-long"} {
		if len(deriveKey(s)) != 32 {
			t.Errorf("deriveKey(%q) not 32 bytes", s)
		}
	}
}
