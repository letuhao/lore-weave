package config

import "testing"

// baseEnv sets the always-required env so a test can focus on the admin-issuance
// fields. Uses t.Setenv (auto-restored).
func baseEnv(t *testing.T) {
	t.Helper()
	t.Setenv("DATABASE_URL", "postgres://x/y")
	t.Setenv("JWT_SECRET", "0123456789012345678901234567890123") // >=32
	t.Setenv("INTERNAL_SERVICE_TOKEN", "internal-token-value-distinct-aaaa")
	// Clear admin envs so each case starts from "disabled".
	for _, k := range []string{"KMS_ADMIN_SIGNING_KEY_ID", "ADMIN_TOKEN_ISSUER_SECRET", "ADMIN_AUDIT_HMAC_KEY", "ADMIN_TOKEN_TTL_SECONDS", "KMS_ENDPOINT"} {
		t.Setenv(k, "")
	}
}

func TestLoad_AdminIssuanceDisabledByDefault(t *testing.T) {
	baseEnv(t)
	c, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if c.AdminIssuanceEnabled {
		t.Fatal("admin issuance must be OFF when KMS_ADMIN_SIGNING_KEY_ID is unset")
	}
}

func TestLoad_AdminIssuanceEnabled_Valid(t *testing.T) {
	baseEnv(t)
	t.Setenv("KMS_ADMIN_SIGNING_KEY_ID", "arn:aws:kms:...:key/abc")
	t.Setenv("ADMIN_TOKEN_ISSUER_SECRET", "issuer-secret-32-chars-minimum-aaaa")
	t.Setenv("ADMIN_AUDIT_HMAC_KEY", "audit-hmac-key-32-chars-minimum-bbbb")
	t.Setenv("ADMIN_TOKEN_TTL_SECONDS", "600")
	c, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if !c.AdminIssuanceEnabled {
		t.Fatal("admin issuance should be enabled")
	}
	if c.AdminTokenTTL.Seconds() != 600 {
		t.Errorf("AdminTokenTTL = %v, want 600s", c.AdminTokenTTL)
	}
}

func TestLoad_AdminIssuance_FailClosed(t *testing.T) {
	cases := map[string]func(t *testing.T){
		"issuer secret too short": func(t *testing.T) {
			t.Setenv("ADMIN_TOKEN_ISSUER_SECRET", "too-short")
			t.Setenv("ADMIN_AUDIT_HMAC_KEY", "audit-hmac-key-32-chars-minimum-bbbb")
		},
		"issuer secret equals internal token": func(t *testing.T) {
			t.Setenv("ADMIN_TOKEN_ISSUER_SECRET", "internal-token-value-distinct-aaaa") // == INTERNAL_SERVICE_TOKEN
			t.Setenv("ADMIN_AUDIT_HMAC_KEY", "audit-hmac-key-32-chars-minimum-bbbb")
		},
		"hmac key too short": func(t *testing.T) {
			t.Setenv("ADMIN_TOKEN_ISSUER_SECRET", "issuer-secret-32-chars-minimum-aaaa")
			t.Setenv("ADMIN_AUDIT_HMAC_KEY", "short")
		},
	}
	for name, setup := range cases {
		t.Run(name, func(t *testing.T) {
			baseEnv(t)
			t.Setenv("KMS_ADMIN_SIGNING_KEY_ID", "arn:aws:kms:...:key/abc")
			setup(t)
			if _, err := Load(); err == nil {
				t.Fatalf("%s: expected fail-closed error, got nil", name)
			}
		})
	}
}
