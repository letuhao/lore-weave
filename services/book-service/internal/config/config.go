package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	HTTPAddr           string
	DatabaseURL        string
	JWTSecret          string
	BooksStorageBucket string
	QuotaBytesDefault  int64
	SharingInternalURL string
	MinioEndpoint      string
	MinioAccessKey     string
	MinioSecretKey     string
	MinioUseSSL        bool
	MinioExternalURL   string // URL prefix for browser-accessible media (e.g. http://localhost:9123)
	// When false (prod), bucket policy is not public-read; media URLs use authenticated API routes.
	MediaPublicRead bool
	// Phase 5e-β.2 — `ProviderRegistryURL` field dropped; audio.go was
	// its last consumer (now migrated to use llmgw SDK via LLMGatewayInternalURL).
	LLMGatewayInternalURL  string
	UsageBillingServiceURL string
	InternalServiceToken   string

	// P1 (2026-05-23) — knowledge-service /internal/parse for structural
	// decomposition on the synchronous .txt import branch. EPUB/DOCX go
	// through worker-infra; .txt stays sync per existing UX (small files).
	KnowledgeServiceURL string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:               getEnv("HTTP_ADDR", ":8082"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		JWTSecret:              os.Getenv("JWT_SECRET"),
		BooksStorageBucket:     getEnv("BOOKS_STORAGE_BUCKET", "loreweave-dev-books"),
		QuotaBytesDefault:      getInt64("QUOTA_BYTES_DEFAULT", 100*1024*1024),
		SharingInternalURL:     os.Getenv("SHARING_INTERNAL_URL"),
		MinioEndpoint:          getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:         getEnv("MINIO_ACCESS_KEY", "loreweave"),
		MinioSecretKey:         os.Getenv("MINIO_SECRET_KEY"),
		MinioUseSSL:            getEnv("MINIO_USE_SSL", "false") == "true",
		MinioExternalURL:       strings.TrimRight(os.Getenv("MINIO_EXTERNAL_URL"), "/"),
		MediaPublicRead:        getBool("BOOKS_MEDIA_PUBLIC_READ", true),
		LLMGatewayInternalURL:  os.Getenv("LLM_GATEWAY_INTERNAL_URL"),
		UsageBillingServiceURL: getEnv("USAGE_BILLING_SERVICE_URL", ""),
		InternalServiceToken:   os.Getenv("INTERNAL_SERVICE_TOKEN"),
		KnowledgeServiceURL:    getEnv("KNOWLEDGE_SERVICE_URL", "http://knowledge-service:8092"),
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
	if c.MinioSecretKey == "" {
		return nil, fmt.Errorf("MINIO_SECRET_KEY is required")
	}
	if c.MinioExternalURL == "" {
		return nil, fmt.Errorf("MINIO_EXTERNAL_URL is required")
	}
	if c.SharingInternalURL == "" {
		return nil, fmt.Errorf("SHARING_INTERNAL_URL is required")
	}
	if c.LLMGatewayInternalURL == "" {
		return nil, fmt.Errorf("LLM_GATEWAY_INTERNAL_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func getBool(k string, def bool) bool {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}

func getInt64(k string, def int64) int64 {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.ParseInt(v, 10, 64)
	if err != nil {
		return def
	}
	return n
}
