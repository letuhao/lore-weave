package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds the agent-registry-service runtime configuration. All secrets
// come from env; the service fails to start if a required one is missing
// (CLAUDE.md "No hardcoded secrets").
type Config struct {
	HTTPAddr             string
	DatabaseURL          string
	JWTSecret            string
	InternalServiceToken string

	// AdminJWTPublicKeyPEM (D-JWT-ROLE-GATE) — the RS256 public key that verifies
	// admin tokens for the System-tier write endpoints + the admin-only ingest routes
	// (contracts/adminjwt, glossary's requireAdminScope pattern). Optional: when unset
	// those admin paths fail closed (503). PEM or base64-PEM.
	AdminJWTPublicKeyPEM string

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

	// OfficialRegistryURL — base URL of the official MCP Registry (REG-P5-03 ingest).
	// The admin pull fetches `{base}/v0/servers`. Overridable (AGENT_REGISTRY_OFFICIAL_URL)
	// so the E2E-P5-C can point it at a stubbed upstream.
	OfficialRegistryURL string

	// IngestWorker — enable the background ingest maintenance loop (REG-P5 scheduled
	// worker): periodic re-pull + denylist/retroactive-removal sync + rug-pull rescan of
	// ingested System servers. DEFAULT OFF (AGENT_REGISTRY_INGEST_WORKER=1 to enable).
	IngestWorker bool
	// IngestIntervalSeconds — the worker tick interval (default 3600 = 1h; industry
	// aggregators pull "on a regular but infrequent basis"). Min 300 enforced at start.
	IngestIntervalSeconds int
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:             getEnv("HTTP_ADDR", ":8099"),
		DatabaseURL:          os.Getenv("DATABASE_URL"),
		JWTSecret:            os.Getenv("JWT_SECRET"),
		InternalServiceToken: os.Getenv("INTERNAL_SERVICE_TOKEN"),
		AdminJWTPublicKeyPEM: os.Getenv("ADMIN_JWT_PUBLIC_KEY_PEM"),
		VaultKey:             os.Getenv("AGENT_REGISTRY_VAULT_KEY"),
		BookServiceInternalURL: os.Getenv("BOOK_SERVICE_INTERNAL_URL"),
		AllowInternalMcpTargets: os.Getenv("AGENT_REGISTRY_ALLOW_INTERNAL_MCP") == "1",
		PublicBaseURL:           getEnv("AGENT_REGISTRY_PUBLIC_BASE_URL", "http://localhost:3123"),
		OfficialRegistryURL:     getEnv("AGENT_REGISTRY_OFFICIAL_URL", "https://registry.modelcontextprotocol.io"),
		IngestWorker:            os.Getenv("AGENT_REGISTRY_INGEST_WORKER") == "1",
		IngestIntervalSeconds:   atoiEnv("AGENT_REGISTRY_INGEST_INTERVAL", 3600),
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

func atoiEnv(k string, def int) int {
	if v := os.Getenv(k); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
