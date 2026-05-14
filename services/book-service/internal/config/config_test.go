package config

import "testing"

func TestLoadValidation(t *testing.T) {
	t.Setenv("HTTP_ADDR", ":8082")
	t.Setenv("BOOKS_STORAGE_BUCKET", "bkt")
	t.Setenv("QUOTA_BYTES_DEFAULT", "123")
	t.Setenv("DATABASE_URL", "postgres://user:pw@localhost:5432/db?sslmode=disable")
	t.Setenv("JWT_SECRET", "12345678901234567890123456789012")
	t.Setenv("INTERNAL_SERVICE_TOKEN", "tok")
	t.Setenv("MINIO_SECRET_KEY", "msk")
	t.Setenv("MINIO_EXTERNAL_URL", "http://localhost:9123")
	t.Setenv("SHARING_INTERNAL_URL", "http://sharing-service:8083")
	// Phase 5e-β.1 — required env for media.go's unified gateway path.
	// Phase 5e-β.2 — also covers audio.go (PROVIDER_REGISTRY_SERVICE_URL dropped).
	t.Setenv("LLM_GATEWAY_INTERNAL_URL", "http://provider-registry-service:8085")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error: %v", err)
	}
	if cfg.QuotaBytesDefault != 123 {
		t.Fatalf("expected quota 123, got %d", cfg.QuotaBytesDefault)
	}
	if cfg.LLMGatewayInternalURL == "" {
		t.Fatal("LLMGatewayInternalURL not loaded")
	}
}

func TestLoadRequiresDatabaseURL(t *testing.T) {
	t.Setenv("DATABASE_URL", "")
	t.Setenv("JWT_SECRET", "12345678901234567890123456789012")
	_, err := Load()
	if err == nil {
		t.Fatal("expected DATABASE_URL validation error")
	}
}

func TestLoadRequiresJWTLength(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://ok")
	t.Setenv("JWT_SECRET", "short")
	_, err := Load()
	if err == nil {
		t.Fatal("expected JWT length validation error")
	}
}
