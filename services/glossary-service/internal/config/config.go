package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr            string
	DatabaseURL         string
	JWTSecret           string
	AuthServiceURL      string
	BookServiceURL      string
	KnowledgeServiceURL string
	// ProviderRegistryURL is optional. When set, the deep-research tool (S5) reaches the
	// BYOK web-search capability via provider-registry's /internal/web-search (the ONLY
	// place provider HTTP lives — provider-gateway invariant; this is just the service
	// URL, like BookServiceURL, NOT a model/key). Unset → glossary_deep_research returns a
	// clear "web search is not configured" error; the rest of the service is unaffected.
	ProviderRegistryURL  string
	InternalServiceToken string
	// RedisURL is optional. When set, glossary-service runs the revision-projection
	// consumer (VG-1) that materializes entity_revisions off the
	// loreweave:events:glossary stream. Unset → the consumer is disabled (dev/test
	// / no-broker run still boots; history is simply not captured).
	RedisURL string
	// AdminJWTPublicKeyPEM is the SPKI/PKIX PEM of the platform admin-signing key
	// (the public half of the auth-service KMS key). When set, the System-tier
	// admin write endpoints verify an RS256 admin JWT against it (D-GKA-SYSTEM-TIER-ADMIN).
	// Unset → those endpoints fail closed (503 admin-not-configured); the rest of
	// the service is unaffected. Distribution mirrors admin-cli: PEM via env.
	AdminJWTPublicKeyPEM string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:       getEnv("HTTP_ADDR", ":8088"),
		DatabaseURL:    os.Getenv("DATABASE_URL"),
		JWTSecret:      os.Getenv("JWT_SECRET"),
		AuthServiceURL: os.Getenv("AUTH_SERVICE_URL"),
		BookServiceURL: os.Getenv("BOOK_SERVICE_URL"),
		// C5 (D4-03): optional. The wiki-from-KG renderer reads an
		// entity's 1-hop neighborhood from knowledge-service. When unset
		// the renderer degrades gracefully to a minimal (attribute-only)
		// body — wiki generation never hard-depends on the KG being up.
		KnowledgeServiceURL:  os.Getenv("KNOWLEDGE_SERVICE_URL"),
		ProviderRegistryURL:  os.Getenv("PROVIDER_REGISTRY_URL"),
		InternalServiceToken: os.Getenv("INTERNAL_SERVICE_TOKEN"),
		RedisURL:             os.Getenv("REDIS_URL"),
		AdminJWTPublicKeyPEM: os.Getenv("ADMIN_JWT_PUBLIC_KEY_PEM"),
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
	if c.AuthServiceURL == "" {
		return nil, fmt.Errorf("AUTH_SERVICE_URL is required")
	}
	if c.BookServiceURL == "" {
		return nil, fmt.Errorf("BOOK_SERVICE_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
