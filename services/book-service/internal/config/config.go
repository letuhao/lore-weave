package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Config struct {
	HTTPAddr    string
	DatabaseURL string
	JWTSecret   string
	// ConfirmTokenSigningSecret signs/verifies the Tier-W confirm token
	// (MintConfirmToken/VerifyConfirmToken). Deliberately a DISTINCT secret from
	// JWTSecret — JWTSecret gates the route auth (the user's browser JWT), so
	// key-splitting prevents a leak of one secret from forging the other. Same
	// fail-closed min-length (32) as JWTSecret.
	ConfirmTokenSigningSecret string
	BooksStorageBucket        string
	QuotaBytesDefault         int64
	SharingInternalURL        string
	MinioEndpoint             string
	MinioAccessKey            string
	MinioSecretKey            string
	MinioUseSSL               bool
	MinioExternalURL          string // URL prefix for browser-accessible media (e.g. http://localhost:9123)
	// Phase 5e-β.2 — `ProviderRegistryURL` field dropped; audio.go was
	// its last consumer (now migrated to use llmgw SDK via LLMGatewayInternalURL).
	LLMGatewayInternalURL  string
	UsageBillingServiceURL string
	InternalServiceToken   string

	// P1 (2026-05-23) — knowledge-service /internal/parse for structural
	// decomposition on the synchronous .txt import branch. EPUB/DOCX go
	// through worker-infra; .txt stays sync per existing UX (small files).
	KnowledgeServiceURL string

	// E0-5 — auth-service /internal/users lookup for the collaborators panel
	// (resolve invite email → user_id; resolve user_id → display_name for the list).
	AuthServiceInternalURL string

	// C5 / SD-C5 (P-12) — diary encryption-at-rest. `DiaryEncryptionKey` is the KEK that unwraps a
	// user's per-user DEK (fetched from auth-service); diary chapter prose is AES-GCM encrypted under
	// that DEK. A DEDICATED key — NEVER JWT_SECRET (key-splitting: a JWT leak must not read diaries).
	// OPTIONAL: unset ⇒ diary encryption is OFF (new writes stay plaintext) + a LOUD startup warning,
	// so DEPLOYING the key is what flips encryption on — never a silent half-migration. `...Retired`
	// is the comma-separated previous KEKs tried on the read path so a rotation doesn't orphan diaries.
	DiaryEncryptionKey         string
	DiaryEncryptionKeysRetired string

	// P2·F — tenant-boundary audit coalescing window (seconds). A cross-tenant
	// access (a collaborator reading a book owned by another user) emits at most
	// ONE audit row per (actor, book, outcome) per window — "first-access-per-
	// window" — so a collaborator paging chapters can't flood the audit table
	// (authBook runs on every per-book route with no request-scoped memoization).
	// Default 1h; 0 would make every cross-tenant read emit (volume hazard) so the
	// loader floors it to 1s.
	TenantAuditCoalesceWindowSeconds int64

	// 26 IX-3 (OQ-8) — the index-freshness sweeper. A background goroutine
	// re-parses any published chapter whose last_parsed_revision_id IS DISTINCT
	// FROM published_revision_id (the producer's own predicate) and backfills the
	// legacy corpus on first run. Both knobs are deploy-time infra ceilings, NOT
	// per-user settings (settings-and-config: platform infra). Interval <= 0
	// disables the sweeper (e.g. a one-off migration container).
	ReparseSweepIntervalSeconds int64 // default 300 (5 min)
	ReparseSweepBatchSize       int   // default 20 chapters/batch; floored to 1
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:                         getEnv("HTTP_ADDR", ":8082"),
		DatabaseURL:                      os.Getenv("DATABASE_URL"),
		JWTSecret:                        os.Getenv("JWT_SECRET"),
		ConfirmTokenSigningSecret:        os.Getenv("CONFIRM_TOKEN_SIGNING_SECRET"),
		BooksStorageBucket:               getEnv("BOOKS_STORAGE_BUCKET", "loreweave-dev-books"),
		QuotaBytesDefault:                getInt64("QUOTA_BYTES_DEFAULT", 100*1024*1024),
		SharingInternalURL:               os.Getenv("SHARING_INTERNAL_URL"),
		MinioEndpoint:                    getEnv("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:                   getEnv("MINIO_ACCESS_KEY", "loreweave"),
		MinioSecretKey:                   os.Getenv("MINIO_SECRET_KEY"),
		MinioUseSSL:                      getEnv("MINIO_USE_SSL", "false") == "true",
		MinioExternalURL:                 strings.TrimRight(os.Getenv("MINIO_EXTERNAL_URL"), "/"),
		LLMGatewayInternalURL:            os.Getenv("LLM_GATEWAY_INTERNAL_URL"),
		UsageBillingServiceURL:           getEnv("USAGE_BILLING_SERVICE_URL", ""),
		InternalServiceToken:             os.Getenv("INTERNAL_SERVICE_TOKEN"),
		KnowledgeServiceURL:              getEnv("KNOWLEDGE_SERVICE_URL", "http://knowledge-service:8092"),
		AuthServiceInternalURL:           getEnv("AUTH_SERVICE_INTERNAL_URL", "http://auth-service:8081"),
		DiaryEncryptionKey:               os.Getenv("DIARY_ENCRYPTION_KEY"),
		DiaryEncryptionKeysRetired:       os.Getenv("DIARY_ENCRYPTION_KEYS_RETIRED"),
		TenantAuditCoalesceWindowSeconds: getInt64("TENANT_AUDIT_COALESCE_WINDOW_S", 3600),
		ReparseSweepIntervalSeconds:      getInt64("REPARSE_SWEEP_INTERVAL_S", 300),
		ReparseSweepBatchSize:            int(getInt64("REPARSE_SWEEP_BATCH", 20)),
	}
	if c.TenantAuditCoalesceWindowSeconds < 1 {
		c.TenantAuditCoalesceWindowSeconds = 1 // floor: 0/negative would emit every read
	}
	if c.ReparseSweepBatchSize < 1 {
		c.ReparseSweepBatchSize = 1 // floor: a zero/negative batch would sweep nothing
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if len(c.JWTSecret) < 32 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 32 characters")
	}
	if len(c.ConfirmTokenSigningSecret) < 32 {
		return nil, fmt.Errorf("CONFIRM_TOKEN_SIGNING_SECRET must be at least 32 characters")
	}
	if c.InternalServiceToken == "" {
		return nil, fmt.Errorf("INTERNAL_SERVICE_TOKEN is required")
	}
	// C5 — a diary key, when set, must be DEDICATED: never reuse JWT_SECRET (a JWT-secret leak must
	// not also unlock every diary). Fail closed on this misconfiguration rather than silently accept
	// a shared secret. (Unset is allowed — encryption is simply off until the key is deployed.)
	if c.DiaryEncryptionKey != "" {
		if c.DiaryEncryptionKey == c.JWTSecret {
			return nil, fmt.Errorf("DIARY_ENCRYPTION_KEY must NOT equal JWT_SECRET (use a dedicated key)")
		}
		// Match auth-service's floor: it MUST be the SAME KEK auth wraps under, so the same minimum.
		if len(c.DiaryEncryptionKey) < 32 {
			return nil, fmt.Errorf("DIARY_ENCRYPTION_KEY must be at least 32 characters when set")
		}
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
