package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr                   string
	DatabaseURL                string
	JWTSecret                  string
	BookServiceInternalURL     string
	GlossaryServiceInternalURL string
	InternalServiceToken       string
	// DQ-T38 residue (owner 2026-09-02) — the book-lifecycle consumer that drops a sharing
	// policy whose book is gone. OPTIONAL on purpose: unset simply disables the consumer and
	// the service still starts, which is how GlossaryServiceInternalURL above already behaves.
	// A cleanup that refuses to boot without Redis would make this service harder to run than
	// it was before, for a feature that only tidies orphaned rows.
	RedisURL                   string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:               getEnv("HTTP_ADDR", ":8083"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		JWTSecret:              os.Getenv("JWT_SECRET"),
		BookServiceInternalURL: os.Getenv("BOOK_SERVICE_INTERNAL_URL"),
		// W11-M3 public lore route. Optional: a deploy that doesn't set it (or when
		// glossary is unreachable) makes the /unlisted/{token}/lore route degrade to
		// 503, but the service still starts. Default = the compose service URL.
		GlossaryServiceInternalURL: getEnv("GLOSSARY_SERVICE_INTERNAL_URL", "http://glossary-service:8088"),
		InternalServiceToken:       os.Getenv("INTERNAL_SERVICE_TOKEN"),
		RedisURL:                   os.Getenv("REDIS_URL"),
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
	if c.BookServiceInternalURL == "" {
		return nil, fmt.Errorf("BOOK_SERVICE_INTERNAL_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
