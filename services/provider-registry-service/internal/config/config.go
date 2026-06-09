package config

import (
	"fmt"
	"os"
	"strconv"
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
	AudioCacheBucket      string // default "loreweave-audio-cache" when empty
	AudioCachePublicRead  bool
	AudioCachePresignTTL  int

	// Phase 6a Subsystem A — spend-guardrail estimator tuning knobs. These
	// are token-count estimation parameters (not money limits), so they
	// carry code defaults overridable via env — mirrors RESERVATION_TTL.
	// See docs/03_planning/LLM_PIPELINE_PHASE6A_DESIGN.md §3.3 / §3.6.
	//
	// MaxOutputTokensDefault   — output ceiling for a chat/completion job
	//                            that omits max_tokens.
	// ExtractionOutputCeiling  — per-op output-token estimate for the
	//                            extraction operations (bounded JSON list).
	// SystemPromptTokenEstimate — per-chunk system-prompt overhead; a
	//                            chunked job re-sends the prompt nchunks×.
	MaxOutputTokensDefault    int
	ExtractionOutputCeiling   int
	SystemPromptTokenEstimate int

	// Phase 6b — job-level transient-retry budget: the number of retries a
	// worker attempts on a transient upstream error before failing the job.
	// Config-driven (env JOB_MAX_RETRIES), code default 3.
	JobMaxRetries int

	// E5B — cross-encoder rerank service (raw-search junk-rejection). A single
	// PLATFORM service (not per-user BYOK), so it's configured here rather than
	// resolved from a provider_credential. Empty RerankURL ⇒ /internal/rerank
	// returns 503 RERANK_UNAVAILABLE (the knowledge caller degrades to fusion
	// order). RerankServiceToken is sent as a Bearer header.
	RerankURL          string
	RerankServiceToken string
	RerankModel        string
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
		AudioCacheBucket:     getEnv("AUDIO_CACHE_BUCKET", "loreweave-audio-cache"),
		AudioCachePublicRead: getEnv("AUDIO_CACHE_PUBLIC_READ", "true") == "true",
		// E5B — rerank service (all optional; empty URL disables rerank).
		RerankURL:          os.Getenv("RERANK_URL"),
		RerankServiceToken: os.Getenv("RERANK_SERVICE_TOKEN"),
		RerankModel:        getEnv("RERANK_MODEL", "bge-reranker-v2-m3"),
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

	var err error
	if c.MaxOutputTokensDefault, err = getEnvInt("MAX_OUTPUT_TOKENS_DEFAULT", 4096); err != nil {
		return nil, err
	}
	if c.ExtractionOutputCeiling, err = getEnvInt("EXTRACTION_OUTPUT_CEILING", 8192); err != nil {
		return nil, err
	}
	if c.SystemPromptTokenEstimate, err = getEnvInt("SYSTEM_PROMPT_TOKEN_ESTIMATE", 1024); err != nil {
		return nil, err
	}
	if c.JobMaxRetries, err = getEnvInt("JOB_MAX_RETRIES", 3); err != nil {
		return nil, err
	}
	if c.AudioCachePresignTTL, err = getEnvInt("AUDIO_CACHE_PRESIGN_TTL_SECONDS", 3600); err != nil {
		return nil, err
	}
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// getEnvInt reads a strictly-positive int env var, falling back to def when
// unset. A present-but-invalid or non-positive value is a hard error.
func getEnvInt(k string, def int) (int, error) {
	v := os.Getenv(k)
	if v == "" {
		return def, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, fmt.Errorf("%s must be an integer: %w", k, err)
	}
	if n <= 0 {
		return 0, fmt.Errorf("%s must be > 0", k)
	}
	return n, nil
}
