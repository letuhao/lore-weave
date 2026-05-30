package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr             string
	DatabaseURL          string
	JWTSecret            string
	AuthServiceURL       string
	BookServiceURL       string
	KnowledgeServiceURL  string
	InternalServiceToken string
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
