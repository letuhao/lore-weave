package config

import (
	"fmt"
	"os"
)

// Config holds the agent-registry-service runtime configuration. All secrets
// come from env; the service fails to start if a required one is missing
// (CLAUDE.md "No hardcoded secrets").
type Config struct {
	HTTPAddr             string
	DatabaseURL          string
	JWTSecret            string
	InternalServiceToken string

	// VaultKey encrypts MCP-server credentials (OAuth tokens / bearer secrets)
	// at rest with AES-GCM (DECISION-1: agent-registry owns its own secret vault,
	// mirroring provider-registry, rather than reusing provider_credentials).
	// Defaults to JWTSecret-derived key when empty so a dev run boots; a distinct
	// AGENT_REGISTRY_VAULT_KEY is recommended in prod for blast-radius isolation.
	VaultKey string

	// BookServiceInternalURL — book-service base URL for E0 grant checks
	// (grantclient /internal/books/{id}/access). Optional: empty disables
	// book-tier writes (they 501), matching the pre-grant behavior. Set it to
	// enable book-tier plugins/skills + book-scope enablement (D-REG-BOOK-GRANT).
	BookServiceInternalURL string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:             getEnv("HTTP_ADDR", ":8099"),
		DatabaseURL:          os.Getenv("DATABASE_URL"),
		JWTSecret:            os.Getenv("JWT_SECRET"),
		InternalServiceToken: os.Getenv("INTERNAL_SERVICE_TOKEN"),
		VaultKey:             os.Getenv("AGENT_REGISTRY_VAULT_KEY"),
		BookServiceInternalURL: os.Getenv("BOOK_SERVICE_INTERNAL_URL"),
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
	if c.VaultKey == "" {
		c.VaultKey = c.JWTSecret
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
