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

	// AllowInternalMcpTargets — dev-only SSRF escape hatch. When true, a user may
	// register an MCP endpoint that resolves to an internal/loopback address (used
	// to keep the P3 overlay/scan/egress paths live-smokeable against an in-cluster
	// MCP server). DEFAULT FALSE — in prod every user-supplied URL is SSRF-guarded
	// to public hosts only. Set AGENT_REGISTRY_ALLOW_INTERNAL_MCP=1 to enable.
	AllowInternalMcpTargets bool

	// PublicBaseURL — the externally-reachable base (through the BFF) used to build
	// the OAuth redirect_uri (`{base}/v1/agent-registry/oauth/callback`). The AS
	// redirects the user's browser here after consent. Defaults to the dev BFF.
	PublicBaseURL string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:             getEnv("HTTP_ADDR", ":8099"),
		DatabaseURL:          os.Getenv("DATABASE_URL"),
		JWTSecret:            os.Getenv("JWT_SECRET"),
		InternalServiceToken: os.Getenv("INTERNAL_SERVICE_TOKEN"),
		VaultKey:             os.Getenv("AGENT_REGISTRY_VAULT_KEY"),
		BookServiceInternalURL: os.Getenv("BOOK_SERVICE_INTERNAL_URL"),
		AllowInternalMcpTargets: os.Getenv("AGENT_REGISTRY_ALLOW_INTERNAL_MCP") == "1",
		PublicBaseURL:           getEnv("AGENT_REGISTRY_PUBLIC_BASE_URL", "http://localhost:3123"),
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
