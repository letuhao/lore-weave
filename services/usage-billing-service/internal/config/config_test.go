package config

import (
	"testing"
	"time"
)

// setValidEnv populates every required env var with a valid value via
// t.Setenv (which auto-restores on test end). Individual tests then override
// one var to exercise a failure path.
func setValidEnv(t *testing.T) {
	t.Helper()
	t.Setenv("DATABASE_URL", "postgres://localhost/usage_billing_test")
	t.Setenv("JWT_SECRET", "test_jwt_secret_at_least_32_characters_long")
	t.Setenv("LLM_PAYLOAD_ENCRYPTION_KEY", "test_payload_kek_at_least_32_characters_long")
	t.Setenv("INTERNAL_SERVICE_TOKEN", "internal-token")
	t.Setenv("GUARDRAIL_DEFAULT_DAILY_USD", "10")
	t.Setenv("GUARDRAIL_DEFAULT_MONTHLY_USD", "100")
	t.Setenv("PLATFORM_FREE_TIER_USD", "5000")
	t.Setenv("RESERVATION_TTL", "")
	t.Setenv("HTTP_ADDR", "")
}

func TestLoad_Valid_Defaults(t *testing.T) {
	setValidEnv(t)
	c, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if c.GuardrailDefaultDailyUSD != 10 || c.GuardrailDefaultMonthlyUSD != 100 {
		t.Fatalf("guardrail defaults wrong: daily=%v monthly=%v",
			c.GuardrailDefaultDailyUSD, c.GuardrailDefaultMonthlyUSD)
	}
	if c.PlatformFreeTierUSD != 5000 {
		t.Fatalf("PlatformFreeTierUSD: got %v want 5000", c.PlatformFreeTierUSD)
	}
	if c.ReservationTTL != 45*time.Minute {
		t.Fatalf("expected default ReservationTTL 45m, got %v", c.ReservationTTL)
	}
	if c.HTTPAddr != ":8086" {
		t.Fatalf("expected default HTTPAddr :8086, got %q", c.HTTPAddr)
	}
}

func TestLoad_MissingRequired(t *testing.T) {
	cases := []struct {
		name, key string
	}{
		{"DATABASE_URL", "DATABASE_URL"},
		{"LLM_PAYLOAD_ENCRYPTION_KEY", "LLM_PAYLOAD_ENCRYPTION_KEY"},
		{"INTERNAL_SERVICE_TOKEN", "INTERNAL_SERVICE_TOKEN"},
		{"GUARDRAIL_DEFAULT_DAILY_USD", "GUARDRAIL_DEFAULT_DAILY_USD"},
		{"GUARDRAIL_DEFAULT_MONTHLY_USD", "GUARDRAIL_DEFAULT_MONTHLY_USD"},
		{"PLATFORM_FREE_TIER_USD", "PLATFORM_FREE_TIER_USD"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			setValidEnv(t)
			t.Setenv(tc.key, "")
			if _, err := Load(); err == nil {
				t.Fatalf("expected error when %s is unset", tc.key)
			}
		})
	}
}

func TestLoad_ShortJWTSecret(t *testing.T) {
	setValidEnv(t)
	t.Setenv("JWT_SECRET", "too-short")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for short JWT_SECRET")
	}
}

func TestLoad_ShortPayloadKey(t *testing.T) {
	setValidEnv(t)
	t.Setenv("LLM_PAYLOAD_ENCRYPTION_KEY", "too-short")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for short LLM_PAYLOAD_ENCRYPTION_KEY")
	}
}

// LOG-5: the dedicated payload KEK must be distinct from JWT_SECRET so rotating
// or leaking the JWT secret never touches logged payloads.
func TestLoad_PayloadKeyMustDifferFromJWT(t *testing.T) {
	setValidEnv(t)
	shared := "identical_secret_used_for_both_32_chars_x"
	t.Setenv("JWT_SECRET", shared)
	t.Setenv("LLM_PAYLOAD_ENCRYPTION_KEY", shared)
	if _, err := Load(); err == nil {
		t.Fatal("expected error when LLM_PAYLOAD_ENCRYPTION_KEY equals JWT_SECRET")
	}
}

func TestLoad_GuardrailDefault_NonNumeric(t *testing.T) {
	setValidEnv(t)
	t.Setenv("GUARDRAIL_DEFAULT_DAILY_USD", "not-a-number")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for non-numeric GUARDRAIL_DEFAULT_DAILY_USD")
	}
}

func TestLoad_GuardrailDefault_NonPositive(t *testing.T) {
	for _, v := range []string{"0", "-5"} {
		t.Run(v, func(t *testing.T) {
			setValidEnv(t)
			t.Setenv("GUARDRAIL_DEFAULT_MONTHLY_USD", v)
			if _, err := Load(); err == nil {
				t.Fatalf("expected error for GUARDRAIL_DEFAULT_MONTHLY_USD=%q", v)
			}
		})
	}
}

func TestLoad_ReservationTTL_Override(t *testing.T) {
	setValidEnv(t)
	t.Setenv("RESERVATION_TTL", "90m")
	c, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if c.ReservationTTL != 90*time.Minute {
		t.Fatalf("expected ReservationTTL 90m, got %v", c.ReservationTTL)
	}
}

func TestLoad_ReservationTTL_Invalid(t *testing.T) {
	setValidEnv(t)
	t.Setenv("RESERVATION_TTL", "not-a-duration")
	if _, err := Load(); err == nil {
		t.Fatal("expected error for invalid RESERVATION_TTL")
	}
}
