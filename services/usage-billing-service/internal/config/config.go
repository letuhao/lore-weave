package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	HTTPAddr             string
	DatabaseURL          string
	JWTSecret            string
	InternalServiceToken string

	// Phase 6a — spend-guardrail default limits (USD). Config-driven, no
	// hardcoded literal (billing ADR P5). Seeded into a user's
	// spend_guardrails row on first reserve.
	GuardrailDefaultDailyUSD   float64
	GuardrailDefaultMonthlyUSD float64

	// Phase 6a-β — Subsystem B platform free-tier allowance (USD). Required,
	// config-driven (ADR P5 — never a DDL default). Seeded into a user's
	// platform_balances row on first platform_model reserve.
	PlatformFreeTierUSD float64

	// Sweeper horizon for held reservations — MUST exceed the longest job
	// timeout (provider-registry VideoGenJobTimeout = 30m) so a normal job
	// is never swept mid-run. Code default 45m; override via RESERVATION_TTL.
	ReservationTTL time.Duration

	// S4c — usage audit stream consumer. Active only when RedisURL is set;
	// consumes the S4b loreweave:events:usage stream → usage_logs audit.
	RedisURL           string
	UsageStream        string
	UsageConsumerGroup string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:             getEnv("HTTP_ADDR", ":8086"),
		DatabaseURL:          os.Getenv("DATABASE_URL"),
		JWTSecret:            os.Getenv("JWT_SECRET"),
		InternalServiceToken: os.Getenv("INTERNAL_SERVICE_TOKEN"),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if len(c.JWTSecret) < 32 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 32 characters")
	}
	if c.InternalServiceToken == "" {
		return nil, fmt.Errorf("INTERNAL_SERVICE_TOKEN is required")
	}

	daily, err := requiredFloat("GUARDRAIL_DEFAULT_DAILY_USD")
	if err != nil {
		return nil, err
	}
	monthly, err := requiredFloat("GUARDRAIL_DEFAULT_MONTHLY_USD")
	if err != nil {
		return nil, err
	}
	c.GuardrailDefaultDailyUSD = daily
	c.GuardrailDefaultMonthlyUSD = monthly

	freeTier, err := requiredFloat("PLATFORM_FREE_TIER_USD")
	if err != nil {
		return nil, err
	}
	c.PlatformFreeTierUSD = freeTier

	c.ReservationTTL = 45 * time.Minute
	if v := os.Getenv("RESERVATION_TTL"); v != "" {
		d, perr := time.ParseDuration(v)
		if perr != nil {
			return nil, fmt.Errorf("RESERVATION_TTL invalid: %w", perr)
		}
		c.ReservationTTL = d
	}

	// S4c usage stream consumer (optional; active only when REDIS_URL is set).
	c.RedisURL = os.Getenv("REDIS_URL")
	c.UsageStream = getEnv("USAGE_STREAM", "loreweave:events:usage")
	c.UsageConsumerGroup = getEnv("USAGE_CONSUMER_GROUP", "usage-biller")

	return c, nil
}

// requiredFloat reads a required, strictly-positive float env var.
func requiredFloat(key string) (float64, error) {
	v := os.Getenv(key)
	if v == "" {
		return 0, fmt.Errorf("%s is required", key)
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil {
		return 0, fmt.Errorf("%s must be a number: %w", key, err)
	}
	if f <= 0 {
		return 0, fmt.Errorf("%s must be > 0", key)
	}
	return f, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
