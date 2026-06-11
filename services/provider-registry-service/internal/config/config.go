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
	AudioCacheBucket string // default "loreweave-audio-cache" when empty

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

	// Phase 0 (event-driven re-arch) — runaway backstop for the async job
	// path: a per-job wall-clock ceiling so a hung/runaway generation
	// self-cancels and frees its concurrency slot even if nobody issues a
	// DELETE. 0 (env unset / "0") = disabled (no ceiling). Set generously
	// when enabled — it is a backstop, not the long-run mechanism (a legit
	// multi-chunk job can run for many minutes). Env LLM_JOB_WALLCLOCK_TIMEOUT_S.
	LLMJobWallclockTimeoutS int

	// S3a (G5) — per-provider concurrency governor + circuit-breaker on the
	// jobs-worker path. RedisURL empty → governance disabled (Guard passes
	// calls through). Sized for the autonomous batch: bound cloud concurrency,
	// serialize local GPU (=1), and auto-pause a flapping provider.
	RedisURL                 string
	GovernorCloudMax         int // concurrency cap per cloud provider kind
	GovernorLeaseMs          int // per-acquisition lease TTL (> max call duration)
	GovernorAcquireTimeoutMs int // max wait for a slot before a transient error
	BreakerThreshold         int // windowed failures that trip the breaker
	BreakerWindowS           int // failure-count decay window
	BreakerCooldownS         int // open → half-open wait

	// E5B rerank is BYOK (D-RERANK-NOT-BYOK): /internal/rerank resolves the
	// user's rerank model from provider-registry like /internal/embed — there is
	// no platform rerank endpoint/model config here anymore.

	// S4b (decision C) — usage outbox relay → Redis streams. Active only when
	// RedisURL is set (reuses the S3a client). MAXLEN bounds each stream (G8).
	UsageStream               string
	CampaignUsageStream       string
	UsageStreamMaxLen         int
	CampaignUsageStreamMaxLen int
	UsageRelayPollMs          int
	UsageRelayBatch           int

	// LLM re-arch Phase 1 — durable terminal-event stream (job_event_outbox →
	// relay → here). A caller resumes on it keyed by job_id. Shares the S4b relay
	// loop + REDIS_URL gate.
	LLMJobTerminalStream       string
	LLMJobTerminalStreamMaxLen int

	// LLM re-arch Phase 1 Commit 3 — durable per-kind work queue. When true (AND
	// RABBITMQ_URL set), submit enqueues to llm.jobs.{kind} and a consumer pool
	// (size = governor.maxFor(kind)) runs the job — jobs WAIT in the queue instead
	// of failing acquire. Default false ⇒ today's direct-goroutine dispatch (zero
	// change). Env LLM_JOB_QUEUE_ENABLED.
	LLMJobQueueEnabled bool

	// LLM re-arch Phase 1 (§5.6) — stuck-`running` truth-sweeper. A job that
	// crashed mid-Process is left running (queue redelivery can't re-run it); this
	// periodic sweep bulk-fails any running job with no progress past the timeout.
	// Timeout generous (a legit long multi-chunk job keeps bumping last_progress_at).
	// 0 = disabled. Env LLM_RUNNING_SWEEP_TIMEOUT_S / LLM_RUNNING_SWEEP_INTERVAL_S.
	LLMRunningSweepTimeoutS  int
	LLMRunningSweepIntervalS int
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
	// Phase 0 — optional per-job wall-clock backstop; 0/unset = disabled.
	// getEnvInt rejects 0, so read it directly to allow the disabled sentinel.
	if v := os.Getenv("LLM_JOB_WALLCLOCK_TIMEOUT_S"); v != "" {
		n, convErr := strconv.Atoi(v)
		if convErr != nil || n < 0 {
			return nil, fmt.Errorf("LLM_JOB_WALLCLOCK_TIMEOUT_S must be a non-negative integer")
		}
		c.LLMJobWallclockTimeoutS = n
	}
	// S3a governor + breaker (all optional; RedisURL empty disables governance).
	c.RedisURL = os.Getenv("REDIS_URL")
	if c.GovernorCloudMax, err = getEnvInt("GOVERNOR_CLOUD_MAX", 8); err != nil {
		return nil, err
	}
	// Lease TTL ≥ the max provider-call duration (invoke_timeout_secs≈300s) so a
	// long stream's slot isn't reclaimed mid-call (which would over-admit — for a
	// local GPU, a 2nd concurrent call). A crashed worker's slot still frees when
	// this elapses.
	if c.GovernorLeaseMs, err = getEnvInt("GOVERNOR_LEASE_MS", 300000); err != nil {
		return nil, err
	}
	if c.GovernorAcquireTimeoutMs, err = getEnvInt("GOVERNOR_ACQUIRE_TIMEOUT_MS", 30000); err != nil {
		return nil, err
	}
	if c.BreakerThreshold, err = getEnvInt("BREAKER_THRESHOLD", 5); err != nil {
		return nil, err
	}
	if c.BreakerWindowS, err = getEnvInt("BREAKER_WINDOW_S", 60); err != nil {
		return nil, err
	}
	if c.BreakerCooldownS, err = getEnvInt("BREAKER_COOLDOWN_S", 30); err != nil {
		return nil, err
	}
	// S4b usage outbox relay (optional; active only when REDIS_URL is set).
	c.UsageStream = getEnv("USAGE_STREAM", "loreweave:events:usage")
	c.CampaignUsageStream = getEnv("CAMPAIGN_USAGE_STREAM", "loreweave:events:campaign_usage")
	if c.UsageStreamMaxLen, err = getEnvInt("USAGE_STREAM_MAXLEN", 100000); err != nil {
		return nil, err
	}
	if c.CampaignUsageStreamMaxLen, err = getEnvInt("CAMPAIGN_USAGE_STREAM_MAXLEN", 50000); err != nil {
		return nil, err
	}
	if c.UsageRelayPollMs, err = getEnvInt("USAGE_RELAY_POLL_MS", 500); err != nil {
		return nil, err
	}
	if c.UsageRelayBatch, err = getEnvInt("USAGE_RELAY_BATCH", 100); err != nil {
		return nil, err
	}
	// LLM re-arch Phase 1 — terminal-event stream (shares the S4b relay).
	c.LLMJobTerminalStream = getEnv("LLM_JOB_TERMINAL_STREAM", "loreweave:events:llm_job_terminal")
	if c.LLMJobTerminalStreamMaxLen, err = getEnvInt("LLM_JOB_TERMINAL_STREAM_MAXLEN", 100000); err != nil {
		return nil, err
	}
	c.LLMJobQueueEnabled = os.Getenv("LLM_JOB_QUEUE_ENABLED") == "true"
	// §5.6 stuck-running sweeper. Default 30min timeout / 60s interval; read
	// directly so 0 (disabled) is allowed (getEnvInt rejects 0).
	if v := os.Getenv("LLM_RUNNING_SWEEP_TIMEOUT_S"); v != "" {
		n, convErr := strconv.Atoi(v)
		if convErr != nil || n < 0 {
			return nil, fmt.Errorf("LLM_RUNNING_SWEEP_TIMEOUT_S must be a non-negative integer")
		}
		c.LLMRunningSweepTimeoutS = n
	} else {
		c.LLMRunningSweepTimeoutS = 1800
	}
	if c.LLMRunningSweepIntervalS, err = getEnvInt("LLM_RUNNING_SWEEP_INTERVAL_S", 60); err != nil {
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
