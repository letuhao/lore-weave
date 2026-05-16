package config

import (
	"fmt"
	"os"
)

type Config struct {
	HTTPAddr               string
	DatabaseURL            string
	JWTSecret              string
	UsageBillingServiceURL string
	InternalServiceToken   string

	// Phase 2c — optional. Empty = NoopNotifier (terminal events not
	// published anywhere; caller can still poll). Set in production
	// docker-compose; tests + dev-without-RabbitMQ keep working.
	RabbitMQURL string

	// Phase 5e-β.2 — MinIO config for audio_gen URL-mode staging.
	// All five fields optional; if MinioEndpoint is empty, audio_gen
	// URL-mode is disabled (b64_json mode still works without MinIO).
	MinioEndpoint    string
	MinioAccessKey   string
	MinioSecretKey   string
	MinioUseSSL      bool
	MinioExternalURL string // public URL prefix (e.g. http://localhost:9123)
	AudioCacheBucket string // default "loreweave-audio-cache" when empty
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:               getEnv("HTTP_ADDR", ":8085"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),
		JWTSecret:              os.Getenv("JWT_SECRET"),
		UsageBillingServiceURL: os.Getenv("USAGE_BILLING_SERVICE_URL"),
		InternalServiceToken:   os.Getenv("INTERNAL_SERVICE_TOKEN"),
		RabbitMQURL:            os.Getenv("RABBITMQ_URL"),
		// Phase 5e-β.2 — audio_gen URL-mode staging.
		MinioEndpoint:    os.Getenv("MINIO_ENDPOINT"),
		MinioAccessKey:   os.Getenv("MINIO_ACCESS_KEY"),
		MinioSecretKey:   os.Getenv("MINIO_SECRET_KEY"),
		MinioUseSSL:      os.Getenv("MINIO_USE_SSL") == "true",
		MinioExternalURL: os.Getenv("MINIO_EXTERNAL_URL"),
		AudioCacheBucket: getEnv("AUDIO_CACHE_BUCKET", "loreweave-audio-cache"),
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
	if c.UsageBillingServiceURL == "" {
		return nil, fmt.Errorf("USAGE_BILLING_SERVICE_URL is required")
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
