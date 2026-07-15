package api

import (
	"bytes"
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"path"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/adminjwt"
	"github.com/loreweave/foundation/contracts/platformjwt"
	"github.com/loreweave/observability"
	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/config"
	"github.com/loreweave/provider-registry-service/internal/jobs"
	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
	"github.com/loreweave/provider-registry-service/internal/storage"
)

type Server struct {
	pool         *pgxpool.Pool
	cfg          *config.Config
	secret       []byte
	secretKey    []byte
	// adminPub verifies RS256 admin JWTs for the System-tier platform-model write
	// endpoints (D-JWT-ROLE-GATE, contracts/adminjwt). nil when
	// ADMIN_JWT_PUBLIC_KEY_PEM is unset → those endpoints fail closed.
	// adminKID = KeyFingerprint(adminPub).
	adminPub *rsa.PublicKey
	adminKID string
	client       *http.Client // short-timeout: sync/billing calls (15s)
	invokeClient *http.Client // no timeout: AI generation can take minutes

	// Phase 2b — async LLM job lifecycle. Both nil-safe so unit tests
	// that construct a router-only Server (no pool, no jobs subsystem)
	// keep working; handlers return 503 LLM_INTERNAL_ERROR when nil.
	jobsRepo     *jobs.Repo
	jobsWorker   *jobs.Worker
	jobsNotifier jobs.Notifier

	// Phase 5e-β.2 — audio_gen URL-mode staging. nil when MINIO_* config
	// is missing; URL mode falls back to LLM_INVALID_REQUEST at the
	// worker, b64_json mode still works.
	audioCache *storage.AudioCache

	// Phase 6a — USD spend guardrail. estimator computes the pre-flight
	// cost upper bound; guardrail is the usage-billing reserve/reconcile/
	// release client. Both are always constructed (stateless); doSubmitJob
	// gates on jobsRepo != nil before using them.
	estimator billing.Estimator
	guardrail *billing.GuardrailClient

	// Phase 0 (event-driven re-arch) — per-job cancellation. jobCancels maps an
	// in-flight async job to its worker-goroutine CancelFunc so DELETE actually
	// aborts the provider call + frees the governor slot (not just DB state).
	// jobWallclock (0 = disabled) is the optional runaway backstop.
	jobCancels   jobCancelRegistry
	jobWallclock time.Duration

	// Phase 1 Commit 3 (event-driven re-arch) — durable per-kind work queue.
	// nil ⇒ direct-goroutine dispatch (LLM_JOB_QUEUE_ENABLED off / no broker).
	// When set, doSubmitJob enqueues instead of spawning, and a consumer pool
	// (per-kind semaphore = governor.MaxFor) runs jobs — wait-not-fail.
	jobQueue *jobs.JobQueue
}

// NewServer constructs the HTTP server. notifier may be nil (router-only
// tests, dev runs without RabbitMQ); falls back to NoopNotifier so the
// jobs subsystem stays functional without a broker. audioCache may be
// nil; URL-mode audio_gen jobs fail with a clear message in that case.
func NewServer(pool *pgxpool.Pool, cfg *config.Config, notifier jobs.Notifier, audioCache *storage.AudioCache) *Server {
	key := []byte(cfg.JWTSecret)
	if len(key) > 32 {
		key = key[:32]
	}
	if len(key) < 32 {
		padded := make([]byte, 32)
		copy(padded, key)
		key = padded
	}
	s := &Server{
		pool:         pool,
		cfg:          cfg,
		secret:       []byte(cfg.JWTSecret),
		secretKey:    key,
		client:       &http.Client{Timeout: 15 * time.Second},
		invokeClient: &http.Client{}, // no Timeout — context deadline from request controls cancellation
	}
	if raw := strings.TrimSpace(cfg.AdminJWTPublicKeyPEM); raw != "" {
		if pub, err := adminjwt.ParseRSAPublicKeyPEM(pemOrBase64(raw)); err != nil {
			// Misconfigured key → leave admin disabled (fail closed) + log loudly.
			slog.Error("provider-registry: ADMIN_JWT_PUBLIC_KEY_PEM parse failed; platform-model admin endpoints DISABLED", "err", err)
		} else if kid, err := adminjwt.KeyFingerprint(pub); err != nil {
			slog.Error("provider-registry: admin key fingerprint failed; platform-model admin endpoints DISABLED", "err", err)
		} else {
			s.adminPub = pub
			s.adminKID = kid
			slog.Info("provider-registry: platform-model admin endpoints ENABLED", "kid", kid)
		}
	}
	if notifier == nil {
		notifier = jobs.NoopNotifier{}
	}
	s.jobsNotifier = notifier
	s.audioCache = audioCache
	// Phase 6a — spend-guardrail estimator + usage-billing client. The
	// guardrail client builds its own short-timeout http.Client (nil arg).
	s.estimator = billing.Estimator{
		MaxOutputTokensDefault:    cfg.MaxOutputTokensDefault,
		ExtractionOutputCeiling:   cfg.ExtractionOutputCeiling,
		SystemPromptTokenEstimate: cfg.SystemPromptTokenEstimate,
	}
	s.guardrail = billing.NewGuardrailClient(cfg.UsageBillingServiceURL, cfg.InternalServiceToken, nil)
	if cfg.LLMJobWallclockTimeoutS > 0 {
		s.jobWallclock = time.Duration(cfg.LLMJobWallclockTimeoutS) * time.Second
	}
	if pool != nil {
		s.jobsRepo = jobs.NewRepo(pool)
		s.jobsWorker = jobs.NewWorker(s.jobsRepo, s.resolveJobCreds, jobsAdapterFactory(s.invokeClient), notifier, nil, audioCache, s.guardrail, cfg.JobMaxRetries)
		// S3a (G5) — attach the per-provider governor + circuit-breaker when
		// REDIS_URL is configured. Untyped-nil interfaces stay in place when it
		// isn't, so Guard passes calls through (governance disabled).
		if cfg.RedisURL != "" {
			if opts, err := redis.ParseURL(cfg.RedisURL); err == nil {
				rdb := redis.NewClient(opts)
				gov := ratelimit.NewGovernor(rdb, ratelimit.GovernorConfig{
					Lease:          time.Duration(cfg.GovernorLeaseMs) * time.Millisecond,
					AcquireTimeout: time.Duration(cfg.GovernorAcquireTimeoutMs) * time.Millisecond,
				})
				brk := ratelimit.NewBreaker(rdb, ratelimit.BreakerConfig{
					Threshold: cfg.BreakerThreshold,
					Window:    time.Duration(cfg.BreakerWindowS) * time.Second,
					Cooldown:  time.Duration(cfg.BreakerCooldownS) * time.Second,
				})
				s.jobsWorker.WithGovernance(gov, brk)
				slog.Info("S3a governance enabled", "cloud_max", cfg.GovernorCloudMax, "breaker_threshold", cfg.BreakerThreshold)

				// S4b (decision C) — start the usage outbox relay on the same
				// Redis client. Drains usage_outbox → loreweave:events:usage (+
				// :campaign_usage for tagged rows). context.Background(): the
				// loop is idempotent/resumable, so process-exit stopping it is
				// safe (graceful stop → D-S4B-RELAY-SHUTDOWN).
				relay := jobs.NewUsageRelay(rdb, pool, jobs.RelayConfig{
					UsageStream:         cfg.UsageStream,
					CampaignUsageStream: cfg.CampaignUsageStream,
					UsageMaxLen:         int64(cfg.UsageStreamMaxLen),
					CampaignMaxLen:      int64(cfg.CampaignUsageStreamMaxLen),
					TerminalStream:      cfg.LLMJobTerminalStream,
					TerminalMaxLen:      int64(cfg.LLMJobTerminalStreamMaxLen),
					PollInterval:        time.Duration(cfg.UsageRelayPollMs) * time.Millisecond,
					BatchSize:           cfg.UsageRelayBatch,
				}, nil)
				go relay.Run(context.Background())
				slog.Info("S4b usage relay enabled", "usage_stream", cfg.UsageStream, "campaign_stream", cfg.CampaignUsageStream)
			} else {
				slog.Warn("S3a: REDIS_URL set but unparseable — governance disabled", "err", err)
			}
		}

		// Phase 1 §5.6 — stuck-`running` truth-sweeper. Periodically bulk-fails
		// jobs that crashed mid-Process (left running, no progress past the
		// timeout) + emits their terminal event so the caller resumes. Timeout 0
		// = disabled. Independent of Redis (the DB transition stands even if the
		// relay isn't shipping events).
		if cfg.LLMRunningSweepTimeoutS > 0 {
			timeout := time.Duration(cfg.LLMRunningSweepTimeoutS) * time.Second
			interval := time.Duration(cfg.LLMRunningSweepIntervalS) * time.Second
			repo := s.jobsRepo
			go func() {
				t := time.NewTicker(interval)
				defer t.Stop()
				for range t.C {
					if n, serr := repo.SweepStuckRunning(context.Background(), timeout); serr != nil {
						slog.Warn("stuck-running sweep failed", "err", serr)
					} else if n > 0 {
						slog.Info("stuck-running sweep", "swept", n)
					}
				}
			}()
			slog.Info("stuck-running sweeper enabled", "timeout_s", cfg.LLMRunningSweepTimeoutS, "interval_s", cfg.LLMRunningSweepIntervalS)
		}

		// P2·B2 — plaintext retention sweeper. DELETEs terminal llm_jobs past their
		// expires_at (7d default), purging the plaintext input/result JSONB; the
		// durable encrypted audit copy remains in usage_logs (readable post-P0-1) and
		// GET …/llm/jobs/{id} cleanly 404s a purged row. 0 = disabled. Drains the
		// backlog in bounded batches each tick so a first run after a long gap can't
		// take one giant table lock. Independent of Redis/the relay.
		if cfg.LLMRetentionSweepIntervalS > 0 {
			interval := time.Duration(cfg.LLMRetentionSweepIntervalS) * time.Second
			batch := cfg.LLMRetentionSweepBatch
			repo := s.jobsRepo
			outboxWindow := time.Duration(cfg.LLMOutboxRetentionHours) * time.Hour
			go func() {
				t := time.NewTicker(interval)
				defer t.Stop()
				for range t.C {
					for {
						n, serr := repo.PurgeExpiredJobs(context.Background(), batch)
						if serr != nil {
							slog.Warn("retention sweep failed", "err", serr)
							break
						}
						if n > 0 {
							slog.Info("retention sweep purged expired llm_jobs", "deleted", n)
						}
						if n < batch {
							break // backlog drained for this tick
						}
					}
					// Prune published (plaintext-carrying) outbox rows past their window.
					// 0 hours disables this half. published_at IS NOT NULL is enforced in
					// the repo query so an un-drained row is never dropped.
					if outboxWindow > 0 {
						for {
							n, serr := repo.PurgePublishedOutbox(context.Background(), outboxWindow, batch)
							if serr != nil {
								slog.Warn("outbox retention sweep failed", "err", serr)
								break
							}
							if n > 0 {
								slog.Info("retention sweep purged published outbox rows", "deleted", n)
							}
							if n == 0 {
								break // nothing older than the window remains
							}
						}
					}
				}
			}()
			slog.Info("retention sweeper enabled",
				"interval_s", cfg.LLMRetentionSweepIntervalS, "batch", cfg.LLMRetentionSweepBatch,
				"outbox_retention_h", cfg.LLMOutboxRetentionHours)
		}

		// Phase 1 Commit 3 — durable work queue. When enabled (+ broker set),
		// submit enqueues and this consumer pool runs jobs behind a per-kind
		// semaphore (= governor.MaxFor), so a slow local job DELAYS the queue
		// instead of failing everyone behind it on acquire (the incident class).
		if cfg.LLMJobQueueEnabled && cfg.RabbitMQURL != "" {
			if jq, qerr := jobs.NewJobQueue(cfg.RabbitMQURL, slog.Default()); qerr != nil {
				slog.Warn("LLM job queue: init failed — direct dispatch", "err", qerr)
			} else {
				s.jobQueue = jq
				// resolve: job_id → (credential concurrency class, its cap). The
				// cap is per-credential (NULL → unlimited); see ResolveConcurrency.
				// FAIL-OPEN on a transient lookup error (run ungoverned) rather than
				// fail-closed: returning ok=false makes handleDelivery ACK+DROP the
				// message, stranding a pending job forever (the truth-sweeper only
				// recovers stuck `running`, never `pending`). Only a genuinely-gone
				// model (ok=false, no error) is dropped. Mirrors Process's fail-open.
				resolve := func(ctx context.Context, jobID uuid.UUID) (string, int, bool) {
					d, lerr := s.jobsRepo.LoadForProcess(ctx, jobID)
					if lerr != nil {
						// Row truly gone → ErrNoRows; Process re-checks status anyway.
						// Run ungoverned so a transient load blip can't strand the job.
						return "ungoverned:" + jobID.String(), 0, true
					}
					key, limit, ok, rerr := s.jobsRepo.ResolveConcurrency(ctx, d.ModelSource, d.OwnerUserID, d.ModelRef)
					if rerr != nil {
						return "ungoverned:" + jobID.String(), 0, true // transient → fail open
					}
					if !ok {
						return "", 0, false // model genuinely gone → drop
					}
					return key, limit, true
				}
				// run: Phase-0 cancellable ctx + jobID→cancel registration, SYNC
				// (the consumer acks only after the job is terminal). DELETE still
				// aborts an in-flight queued job + frees its slot.
				run := func(ctx context.Context, jobID uuid.UUID) {
					wctx := observability.DetachedContext(ctx)
					var cancel context.CancelFunc
					if s.jobWallclock > 0 {
						wctx, cancel = context.WithTimeout(wctx, s.jobWallclock)
					} else {
						wctx, cancel = context.WithCancel(wctx)
					}
					s.jobCancels.register(jobID, cancel)
					defer s.jobCancels.remove(jobID)
					defer cancel()
					s.jobsWorker.ProcessJob(wctx, jobID)
				}
				workers := cfg.GovernorCloudMax * 2
				if workers < 4 {
					workers = 4
				}
				if cerr := s.jobQueue.StartConsumer(context.Background(), workers, resolve, run); cerr != nil {
					slog.Warn("LLM job queue: consumer start failed — direct dispatch", "err", cerr)
					s.jobQueue = nil
				} else {
					slog.Info("LLM job queue enabled", "workers", workers, "cloud_max", cfg.GovernorCloudMax)
				}
			}
		}
	}
	return s
}

// resolveJobCreds — adapter for jobs.Worker. Mirrors the inline
// credential-resolution logic in doProxy without dragging the
// http.Server through the jobs package. (invokeModel /
// internalInvokeModel handlers retired in Phase 4d.)
func (s *Server) resolveJobCreds(
	ctx context.Context,
	ownerUserID, modelRef uuid.UUID,
	modelSource string,
) (string, string, string, string, error) {
	if s.pool == nil {
		return "", "", "", "", fmt.Errorf("no DB pool")
	}
	var providerKind, providerModelName, endpointBaseURL, secret string
	if modelSource == "user_model" {
		var secretCipher string
		err := s.pool.QueryRow(ctx, `
SELECT um.provider_kind, um.provider_model_name,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, ownerUserID).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher)
		if err != nil {
			return "", "", "", "", err
		}
		if secretCipher != "" {
			secret, err = s.decryptSecret(secretCipher)
			if err != nil {
				return "", "", "", "", err
			}
		}
	} else if modelSource == "platform_model" {
		err := s.pool.QueryRow(ctx, `
SELECT provider_kind, provider_model_name
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&providerKind, &providerModelName)
		if err != nil {
			return "", "", "", "", err
		}
	} else {
		return "", "", "", "", fmt.Errorf("invalid model_source: %q", modelSource)
	}
	return providerKind, providerModelName, endpointBaseURL, secret, nil
}

// jobsAdapterFactory closes over the invoke http client so jobs.Worker
// can resolve adapters without importing the api package's dependency
// graph.
func jobsAdapterFactory(client *http.Client) jobs.AdapterFactory {
	return func(providerKind string) (provider.Adapter, error) {
		return provider.ResolveAdapter(providerKind, client)
	}
}

func (s *Server) requireInternalToken(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if s.cfg.InternalServiceToken != "" && r.Header.Get("X-Internal-Token") != s.cfg.InternalServiceToken {
			writeError(w, http.StatusUnauthorized, "INTERNAL_UNAUTHORIZED", "invalid internal token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	// Phase 6c — OpenTelemetry SERVER span. Before Recoverer so the span
	// survives (and is marked 500) when a handler panics.
	r.Use(observability.ChiMiddleware())
	r.Use(middleware.Recoverer)

	// D-K17.2a-01 — Prometheus metrics. Unauthed on purpose (same
	// convention as every other Go service's /metrics); scraper
	// must be in-cluster.
	r.Method(http.MethodGet, "/metrics", metricsHandler())

	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		if s.pool != nil {
			if err := s.pool.Ping(r.Context()); err != nil {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte("db ping failed"))
				return
			}
		}
		_, _ = w.Write([]byte("ok"))
	})
	r.Get("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if s.pool == nil {
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": "no db pool"})
			return
		}
		var n int
		if err := s.pool.QueryRow(r.Context(), "SELECT 1").Scan(&n); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready", "error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
	})

	r.Route("/v1/model-registry", func(r chi.Router) {
		r.Get("/providers", s.listProviderCredentials)
		r.Post("/providers", s.createProviderCredential)
		r.Patch("/providers/{provider_credential_id}", s.patchProviderCredential)
		r.Delete("/providers/{provider_credential_id}", s.deleteProviderCredential)
		r.Post("/providers/{provider_credential_id}/health", s.providerHealth)
		r.Get("/providers/{provider_credential_id}/models", s.listProviderInventory)

		r.Get("/user-models", s.listUserModels)
		r.Post("/user-models", s.createUserModel)
		r.Put("/user-models/reorder", s.reorderUserModels)
		r.Patch("/user-models/{user_model_id}", s.patchUserModel)
		r.Delete("/user-models/{user_model_id}", s.deleteUserModel)
		r.Patch("/user-models/{user_model_id}/activation", s.patchUserModelActivation)
		r.Patch("/user-models/{user_model_id}/favorite", s.patchUserModelFavorite)
		r.Put("/user-models/{user_model_id}/tags", s.putUserModelTags)
		r.Post("/user-models/{user_model_id}/verify", s.verifyUserModel)
		r.Get("/user-models/{user_model_id}/pricing/suggest", s.suggestUserModelPricing) // D-PRICING-REFRESH

		// Per-user default model per capability (rerank/embedding). Restores the
		// default-model UX (BYOK) — consumers resolve via /internal/default-models.
		r.Get("/default-models", s.getDefaultModels)
		r.Put("/default-models/{capability}", s.putDefaultModel)

		r.Get("/platform-models", s.listPlatformModels)
		r.Post("/platform-models", s.createPlatformModel)
		r.Patch("/platform-models/{platform_model_id}", s.patchPlatformModel)
		r.Delete("/platform-models/{platform_model_id}", s.deletePlatformModel)

		// Phase 4d: /v1/model-registry/invoke retired. All callers
		// migrated to /v1/llm/jobs (Phase 4a/b/c). Use the SDK's
		// submit_job + wait_terminal pattern instead.
		r.Get("/models/{model_ref}/context-window", s.getModelContextWindow)
		// Public proxy — forwards any content-type to provider with JWT auth.
		// Used for STT (multipart file upload) and TTS (binary response).
		r.HandleFunc("/proxy/*", s.publicProxy)
	})

	// S-SETTINGS (MCP fan-out) — settings MCP server (Tier R/A/W tools for
	// profile + model registry). Internal-token gated + X-User-Id → ctx by the
	// kit's stateless handler; the federation gateway connects here per call.
	r.Handle("/mcp", s.mcpHandler())
	r.Handle("/mcp/*", s.mcpHandler())

	// S-SETTINGS Tier-W (model_delete) confirm + preview — JWT-gated (the user's
	// browser token); the ONLY write path (INV-9). NET-NEW per provider.
	r.Post("/v1/settings/actions/preview", s.previewSettingsAction)
	r.Post("/v1/settings/actions/confirm", s.confirmSettingsAction)

	// Phase 1a (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN) — unified streaming
	// endpoint. SSE response, no timeout. JWT auth.
	r.Post("/v1/llm/stream", s.llmStream)

	// Phase 2b — async LLM job lifecycle (JWT auth).
	r.Post("/v1/llm/jobs", s.submitLlmJob)
	r.Get("/v1/llm/jobs/{job_id}", s.getLlmJob)
	r.Delete("/v1/llm/jobs/{job_id}", s.cancelLlmJob)

	// Internal service-to-service routes — NOT proxied by api-gateway-bff.
	// Protected by X-Internal-Token middleware instead of user JWT.
	r.Route("/internal", func(r chi.Router) {
		r.Use(s.requireInternalToken)
		r.Get("/credentials/{model_source}/{model_ref}", s.getInternalCredentials)
		// FD-27 — minimal model metadata (provider_model_name + kind, NO
		// secrets) so service callers (worker-ai extraction) can run a
		// reasoning-model capability advisory without holding credentials.
		r.Get("/models/{model_source}/{model_ref}/info", s.getInternalModelInfo)
		// Phase 4d: /internal/invoke retired. Service-to-service
		// callers use /internal/llm/jobs via the loreweave_llm SDK.
		// Transparent proxy — forwards any content-type (multipart, binary, JSON) to provider
		// with credential injection. Used for STT (file upload) and TTS (binary response).
		// Phase 4d: chat-completion paths through this proxy are
		// blocked at request time by doProxy (defense-in-depth);
		// audio paths (transcriptions, speech) pass through.
		r.HandleFunc("/proxy/*", s.internalProxy)
		r.Post("/embed", s.internalEmbed)
		r.Post("/rerank", s.internalRerank)                              // E5B — cross-encoder rerank (platform service)
		r.Post("/web-search", s.internalWebSearch)                       // S5 — BYOK web search (deep-research)
		r.Get("/default-models/{capability}", s.internalGetDefaultModel) // per-user default model fallback
		r.Get("/planner-model", s.internalResolvePlannerModel)           // MED-6 — planner model w/ chat fallback

		// S5a — campaign cost-estimate pricing oracle (token-count → USD).
		r.Post("/billing/estimate", s.internalBillingEstimate)
		// C6 / SD-C6 — price ONE STT/TTS invocation from the model's registered per_second/per_kchar rate.
		r.Post("/billing/price-voice", s.internalBillingPriceVoice)

		// Phase 1a — service-to-service streaming endpoint.
		r.Post("/llm/stream", s.internalLlmStream)

		// Phase 2b — service-to-service async LLM job lifecycle.
		r.Post("/llm/jobs", s.internalSubmitLlmJob)
		r.Get("/llm/jobs/{job_id}", s.internalGetLlmJob)
		// M3 — service-to-service stream cancel (chat disconnect → abort).
		r.Delete("/llm/jobs/{job_id}", s.internalCancelLlmJob)
	})

	return r
}

func (s *Server) getInternalCredentials(w http.ResponseWriter, r *http.Request) {
	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "user_id query param required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "invalid user_id")
		return
	}

	modelSource := chi.URLParam(r, "model_source")
	modelRefStr := chi.URLParam(r, "model_ref")
	modelRef, err := uuid.Parse(modelRefStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "invalid model_ref")
		return
	}

	type credResponse struct {
		ProviderKind      string          `json:"provider_kind"`
		ProviderModelName string          `json:"provider_model_name"`
		BaseURL           string          `json:"base_url"`
		APIKey            string          `json:"api_key"`
		ContextLength     *int            `json:"context_length"`
		Capabilities      map[string]bool `json:"capabilities"`
	}

	var out credResponse

	if modelSource == "user_model" {
		var secretCipher string
		var contextLength *int
		err = s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name, um.context_length,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&out.ProviderKind, &out.ProviderModelName, &contextLength, &out.BaseURL, &secretCipher)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "INTERNAL_MODEL_NOT_FOUND", "user model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_QUERY_FAILED", "failed to resolve user model")
			return
		}
		// D-PROXY-01 — early-fail when user_model's linked credential
		// row has a NULL/empty ciphertext. The COALESCE above and the
		// pc.status='active' JOIN both permit this invalid state;
		// returning empty secrets downstream produces cryptic 401s
		// from the upstream provider. Same guard pattern as doProxy.
		if secretCipher == "" {
			writeError(w, http.StatusInternalServerError,
				"INTERNAL_MISSING_CREDENTIAL",
				"user_model has no provider credential ciphertext")
			return
		}
		secret, err := s.decryptSecret(secretCipher)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_DECRYPT_FAILED", "failed to decrypt secret")
			return
		}
		out.APIKey = secret
		out.ContextLength = contextLength
	} else if modelSource == "platform_model" {
		err = s.pool.QueryRow(r.Context(), `
SELECT provider_kind, provider_model_name
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&out.ProviderKind, &out.ProviderModelName)
		if err == pgx.ErrNoRows {
			writeError(w, http.StatusNotFound, "INTERNAL_MODEL_NOT_FOUND", "platform model not found or inactive")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "INTERNAL_QUERY_FAILED", "failed to resolve platform model")
			return
		}
	} else {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "invalid model_source")
		return
	}

	// Context Budget / Provider Context Strategy §3 — surface the provider kind's
	// static caching capabilities so chat-service can pick a ContextStrategy and
	// label its caching-monitoring frame from a CAPABILITY, not `if kind == "..."`.
	out.Capabilities = provider.CapabilitiesFor(out.ProviderKind).AsMap()

	writeJSON(w, http.StatusOK, out)
}

// isDeprecatedProxyPath returns true for any path retired by the
// Phase 4d (chat-completion / embeddings) and Phase 5b (audio
// transcriptions / speech) retirements. All callers have been
// migrated to /v1/llm/jobs or /v1/llm/stream via the loreweave_llm
// SDK; the transparent proxy is effectively decommissioned for
// known LLM/audio paths after Phase 5b.
//
// Defense-in-depth normalization (caught by /review-impl on the
// initial Phase 4d implementation):
//   - leading slashes trimmed so "//v1/chat/..." can't bypass
//   - path.Clean collapses "./" and "../" so "v1/audio/../chat/completions"
//     can't bypass (Go net/http and chi do NOT normalize by default)
//   - lowercased before compare so "V1/CHAT/COMPLETIONS" can't bypass
//     against case-insensitive upstreams
func isDeprecatedProxyPath(targetPath string) bool {
	for len(targetPath) > 0 && targetPath[0] == '/' {
		targetPath = targetPath[1:]
	}
	if targetPath == "" {
		return false
	}
	// path.Clean operates on slash-paths and collapses .. / . / //.
	// It can re-introduce a leading "/" (e.g. ".//x" → "/x") so we
	// re-trim afterwards.
	cleaned := strings.ToLower(path.Clean(targetPath))
	for len(cleaned) > 0 && cleaned[0] == '/' {
		cleaned = cleaned[1:]
	}
	deprecated := []string{
		// Phase 4d retirements:
		"v1/chat/completions",
		"v1/completions",
		"v1/embeddings",
		// Phase 5b retirements — audio paths migrated to /v1/llm/jobs
		// (stt via multipart bytes-mode) and /v1/llm/stream (tts).
		"v1/audio/transcriptions",
		"v1/audio/speech",
	}
	for _, p := range deprecated {
		if cleaned == p {
			return true
		}
	}
	return false
}

// publicProxy is the JWT-authenticated version of the transparent proxy.
// Phase 4d retired chat-completion / completions / embeddings; Phase 5b
// retired audio/transcriptions and audio/speech. After Phase 5b the
// transparent proxy has no known supported public paths — all callers
// route through /v1/llm/* via the loreweave_llm SDK. The code remains
// alive (model-name rewrite + 4MiB cap + auth-header forwarding) as
// defense-in-depth and to enforce 410 on the retired paths.
func (s *Server) publicProxy(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		ProxyRequestsTotal.WithLabelValues(OutcomeAuthFailed).Inc()
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}

	modelSource := r.URL.Query().Get("model_source")
	modelRefStr := r.URL.Query().Get("model_ref")

	if modelSource == "" || modelRefStr == "" {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "PROXY_VALIDATION_ERROR", "model_source and model_ref query params required")
		return
	}

	// Delegate to shared proxy logic
	s.doProxy(w, r, userID, modelSource, modelRefStr)
}

// internalProxy is the X-Internal-Token authenticated version of the transparent proxy.
// URL pattern: /internal/proxy/{target_path...}?user_id=X&model_source=Y&model_ref=Z
func (s *Server) internalProxy(w http.ResponseWriter, r *http.Request) {
	userIDStr := r.URL.Query().Get("user_id")
	modelSource := r.URL.Query().Get("model_source")
	modelRefStr := r.URL.Query().Get("model_ref")

	if userIDStr == "" || modelSource == "" || modelRefStr == "" {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "PROXY_VALIDATION_ERROR", "user_id, model_source, and model_ref query params required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "PROXY_VALIDATION_ERROR", "invalid user_id")
		return
	}

	s.doProxy(w, r, userID, modelSource, modelRefStr)
}

// doProxy is the shared transparent proxy logic used by both publicProxy and internalProxy.
// Resolves provider credentials from (user_id, model_source, model_ref), rewrites the
// request body's "model" field for JSON bodies so callers don't need to know the upstream
// provider's model name (K17.2a), passes non-JSON bodies (multipart audio, etc.) through
// unchanged, injects the decrypted provider API key as Authorization, and streams the
// upstream response back.
func (s *Server) doProxy(w http.ResponseWriter, r *http.Request, userID uuid.UUID, modelSource string, modelRefStr string) {
	// Phase 4d + 5b defense-in-depth: deprecated LLM/audio paths
	// (chat-completions, completions, embeddings, audio/transcriptions,
	// audio/speech) are blocked here BEFORE any DB work so developers
	// mid-migration get a 410 with a clear "use /v1/llm/* via the SDK"
	// hint, rather than a misleading 404 from credential resolution if
	// their stale request happens to carry stale creds.
	// /review-impl LOW#6 follow-up.
	targetPath := chi.URLParam(r, "*")
	if targetPath == "" {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "PROXY_VALIDATION_ERROR", "target path required")
		return
	}
	if isDeprecatedProxyPath(targetPath) {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusGone, "PROXY_PATH_DEPRECATED",
			"this proxy path was retired in Phase 4d/5b — use /v1/llm/jobs (or /v1/llm/stream for SSE) via the loreweave_llm SDK instead")
		return
	}

	modelRef, err := uuid.Parse(modelRefStr)
	if err != nil {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "PROXY_VALIDATION_ERROR", "invalid model_ref")
		return
	}

	// PUB-12 (BYOK-only) — a public MCP key (X-Mcp-Key-Id header) may not draw a
	// platform_model through the transparent proxy either. Reject 402 before any
	// credential resolution / spend. Synchronous path → header is the carrier.
	if rejectPlatformDrawForPublicKey(w, modelSource, isPublicMcpKeyCall(r, nil)) {
		ProxyRequestsTotal.WithLabelValues(OutcomeByokRequired).Inc()
		return
	}

	// Resolve credentials
	var providerKind, providerModelName, endpointBaseURL, secretCipher string
	if modelSource == "user_model" {
		err = s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher)
	} else if modelSource == "platform_model" {
		err = s.pool.QueryRow(r.Context(), `
SELECT provider_kind, provider_model_name, '', ''
FROM platform_models
WHERE platform_model_id=$1 AND status='active'
`, modelRef).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher)
	} else {
		ProxyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "PROXY_VALIDATION_ERROR", "invalid model_source")
		return
	}

	if err == pgx.ErrNoRows {
		ProxyRequestsTotal.WithLabelValues(OutcomeModelNotFound).Inc()
		writeError(w, http.StatusNotFound, "PROXY_MODEL_NOT_FOUND", "model not found or inactive")
		return
	}
	if err != nil {
		ProxyRequestsTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "PROXY_QUERY_FAILED", "failed to resolve model")
		return
	}

	// providerKind drives per-provider request-body rewrites in the
	// JSON path below (see normalizeResponseFormatForKind for the
	// LM Studio response_format quirk discovered during C19 eval).
	// Other potential per-kind rewrites (Anthropic `system` handling,
	// Ollama `options` mapping) would read this field too.

	// K17.2a — defensive guard. provider_model_name is NOT NULL in the
	// schema and every live adapter populates it, but a bad migration
	// or hand-edited row could leave it empty. Fail unambiguously here
	// rather than silently forwarding an empty "model" field to the
	// upstream provider and getting a cryptic 400 back.
	if providerModelName == "" {
		ProxyRequestsTotal.WithLabelValues(OutcomeEmptyModel).Inc()
		writeError(w, http.StatusInternalServerError, "PROXY_MODEL_RESOLUTION_EMPTY",
			"resolved provider_model_name is empty")
		return
	}

	// K17.2a-R3 (C10) — early-fail for a user_model that somehow
	// has no credential ciphertext. The row shape allows it because
	// of the COALESCE at SELECT time, but a real user_model MUST
	// have a linked, active provider_credential — the JOIN already
	// enforces pc.status='active'. An empty cipher here means the
	// credential row exists with a NULL/empty ciphertext, which is
	// an invalid state. Proxying with no Authorization header would
	// hit the upstream and 401; better to return a loud 500 so the
	// bad state gets noticed.
	//
	// Platform models legitimately have no per-user secret (line 281
	// SELECTs empty strings), so this guard is scoped to user_model.
	if modelSource == "user_model" && secretCipher == "" {
		ProxyRequestsTotal.WithLabelValues(OutcomeMissingCredential).Inc()
		writeError(w, http.StatusInternalServerError, "PROXY_MISSING_CREDENTIAL",
			"user_model has no provider credential ciphertext")
		return
	}

	secret := ""
	if secretCipher != "" {
		secret, err = s.decryptSecret(secretCipher)
		if err != nil {
			ProxyRequestsTotal.WithLabelValues(OutcomeDecryptFailed).Inc()
			writeError(w, http.StatusInternalServerError, "PROXY_DECRYPT_FAILED", "failed to decrypt secret")
			return
		}
	}

	// Build target URL: {base_url}/{target_path}
	// (targetPath was extracted + Phase-4d-guarded at the top of doProxy.)
	targetURL := buildProxyTargetURL(providerKind, endpointBaseURL, targetPath)

	// K17.2a — transparent model rewrite for JSON bodies.
	//
	// Historically doProxy resolved provider_model_name from the DB but
	// discarded it and forwarded r.Body verbatim. That forced every
	// caller to know the upstream provider's model string, which
	// defeats the BYOK proxy's whole point. For JSON bodies we now
	// unmarshal, overwrite "model", and re-marshal. Non-JSON bodies
	// (multipart/form-data audio, etc.) still pass through unchanged.
	//
	// We intentionally overwrite even if the client set its own
	// "model" — callers MUST NOT try to bypass BYOK resolution by
	// supplying an arbitrary model string. The server's resolution
	// from (user_id, model_source, model_ref) is authoritative.
	//
	// Note: encoding/json sorts map keys alphabetically on marshal,
	// so the rewritten body's byte length typically differs from the
	// original even when semantically identical. That is why we
	// recompute Content-Length from len(rewritten) rather than
	// copying the client's header value.
	var bodyReader io.Reader = r.Body
	var bodyLen int64 = r.ContentLength

	contentType := r.Header.Get("Content-Type")
	isJSON := strings.HasPrefix(contentType, "application/json")
	if isJSON && r.ContentLength != 0 {
		// 4MiB cap — generous for chat completion bodies (even
		// context-stuffed calls are well under 1MB) but finite so
		// a malformed or hostile caller can't OOM the proxy.
		//
		// We fully drain r.Body here but do NOT explicitly close it.
		// Go's net/http server closes the inbound body when the
		// handler returns, so this is safe. The outbound proxyReq
		// below uses a fresh *bytes.Reader over the rewritten bytes.
		const maxJSONBodyBytes = 4 * 1024 * 1024
		raw, readErr := io.ReadAll(io.LimitReader(r.Body, maxJSONBodyBytes+1))
		if readErr != nil {
			writeError(w, http.StatusBadRequest, "PROXY_INVALID_JSON_BODY",
				"failed to read request body")
			return
		}
		if int64(len(raw)) > maxJSONBodyBytes {
			ProxyRequestsTotal.WithLabelValues(OutcomeTooLarge).Inc()
			writeError(w, http.StatusRequestEntityTooLarge, "PROXY_BODY_TOO_LARGE",
				"request body exceeds 4MiB JSON cap")
			return
		}
		var parsed map[string]any
		if err := json.Unmarshal(raw, &parsed); err != nil {
			ProxyRequestsTotal.WithLabelValues(OutcomeInvalidJSON).Inc()
			writeError(w, http.StatusBadRequest, "PROXY_INVALID_JSON_BODY",
				"request body is not valid JSON")
			return
		}
		// Per-kind rewrites applied to the parsed map BEFORE the final
		// marshal so all rewrites end up in a single re-marshaled body.
		normalizeResponseFormatForKind(parsed, providerKind)
		rewritten, err := rewriteJSONBodyModel(parsed, providerModelName)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "PROXY_REMARSHAL_FAILED",
				"failed to re-marshal body")
			return
		}
		bodyReader = bytes.NewReader(rewritten)
		bodyLen = int64(len(rewritten))
	}

	// Forward the (possibly rewritten) request body
	proxyReq, err := http.NewRequestWithContext(r.Context(), r.Method, targetURL, bodyReader)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "PROXY_REQUEST_FAILED", "failed to create proxy request")
		return
	}

	// Copy content-type header as-is. Content-Length is recomputed
	// from the (possibly rewritten) body above.
	if ct := contentType; ct != "" {
		proxyReq.Header.Set("Content-Type", ct)
	}
	if bodyLen > 0 {
		proxyReq.ContentLength = bodyLen
		proxyReq.Header.Set("Content-Length", strconv.FormatInt(bodyLen, 10))
	}

	// Set auth with decrypted provider API key
	if secret != "" {
		proxyReq.Header.Set("Authorization", "Bearer "+secret)
	}

	// Execute
	resp, err := s.invokeClient.Do(proxyReq)
	if err != nil {
		ProxyRequestsTotal.WithLabelValues(OutcomeProviderError).Inc()
		writeError(w, http.StatusBadGateway, "PROXY_UPSTREAM_ERROR", "provider request failed: "+err.Error())
		return
	}
	defer resp.Body.Close()

	// Stream response back as-is (headers + body). "ok" from the
	// proxy's perspective means we successfully forwarded and got a
	// response — even a 5xx from upstream counts as a successful
	// proxy. Business-level outcomes (4xx/5xx from provider) are
	// visible via the caller's own instrumentation.
	ProxyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
	for key, vals := range resp.Header {
		for _, val := range vals {
			w.Header().Add(key, val)
		}
	}
	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

// rewriteJSONBodyModel overwrites the "model" field of a parsed JSON
// chat-completion request body with the server-resolved provider model
// name, then marshals it back to bytes. K17.2a helper — isolated from
// doProxy so it can be unit-tested without a pgx pool or upstream.
//
// The input is a map[string]any rather than a typed struct because
// chat-completion bodies vary wildly across providers (OpenAI
// tool_calls, Anthropic system messages, Ollama options). Every field
// other than "model" must survive the round-trip unchanged.
//
// Returns the re-marshaled body or an error if marshaling fails (which,
// for a map populated via json.Unmarshal, can only happen on nested
// values that are not JSON-marshalable — i.e. never in practice).
func rewriteJSONBodyModel(parsed map[string]any, providerModelName string) ([]byte, error) {
	parsed["model"] = providerModelName
	return json.Marshal(parsed)
}

// normalizeResponseFormatForKind mutates parsed["response_format"] in place
// to work around per-provider quirks in the OpenAI-compat shim layer.
// Discovered during C19 quality eval: LM Studio (llama.cpp backend) rejects
// the OpenAI-standard {"type":"json_object"} with HTTP 400 — it only accepts
// "json_schema" (with explicit JSON schema spec) or "text" (no constraint
// at API level). Knowledge-service extractors universally send "json_object"
// because every other provider in the registry accepts it.
//
// Rewrite for lm_studio kind: {"type":"json_object"} → {"type":"text"}.
// "text" loosens API-level JSON validation but preserves intent — the
// extractor prompts already include explicit "Return only the JSON object"
// instructions, so the model still produces JSON. Pure-prompt JSON mode
// matches what OpenAI's json_object provides at the LLM behaviour layer
// even when the API-level validation differs.
//
// Why not json_schema: would require an explicit schema spec which the
// extractor doesn't have at the call site (each call uses a different
// shape). Why not drop the field entirely: keeping it makes intent
// explicit in the wire trace and is extensible to future LM Studio
// versions that may tighten validation.
//
// Other provider kinds (openai, anthropic, ollama, custom) are NOT
// touched: openai accepts json_object natively; anthropic doesn't use
// response_format at all (different field structure); ollama silently
// ignores it. Idempotent — repeated calls or unknown response_format
// values are no-ops.
func normalizeResponseFormatForKind(parsed map[string]any, kind string) {
	if kind != "lm_studio" {
		return
	}
	rf, ok := parsed["response_format"].(map[string]any)
	if !ok {
		return
	}
	if rfType, _ := rf["type"].(string); rfType == "json_object" {
		// Replace with a fresh map so any extra keys
		// (json_schema spec, etc.) don't leak through.
		parsed["response_format"] = map[string]any{"type": "text"}
	}
}

// buildProxyTargetURL joins the resolved provider's endpoint base URL with
// the per-request target path. For lm_studio it strips a trailing "/v1" off
// the base — users frequently store the full OpenAI-style URL like
// http://host:1234/v1, but doProxy receives a target path that already begins
// with "v1/...", so a naïve join would produce /v1/v1/chat/completions.
//
// The typed adapter Invoke() path was fixed in LM-STUDIO-URL-FIX (cycle
// 74da52c) but the transparent proxy was missed; this helper closes the gap.
func buildProxyTargetURL(providerKind, endpointBaseURL, targetPath string) string {
	var base string
	if providerKind == "lm_studio" {
		base = provider.NormalizeLmStudioBase(endpointBaseURL)
	} else {
		base = strings.TrimRight(endpointBaseURL, "/")
	}
	return base + "/" + targetPath
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorBody{Code: code, Message: message})
}

// auth verifies the platform-user HS256 JWT via the shared contracts/platformjwt
// verifier and returns the authenticated user id. It NO LONGER returns a role:
// the platform user token never carries one (D-JWT-ROLE-GATE) — admin authority
// is the RS256 admin token's job (see requireAdminScope).
func (s *Server) auth(r *http.Request) (uuid.UUID, bool) {
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		return uuid.Nil, false
	}
	claims, err := platformjwt.Verify(strings.TrimPrefix(auth, "Bearer "), s.secret)
	if err != nil {
		return uuid.Nil, false
	}
	id, err := claims.UserID()
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}

// scopeAdminWrite is the admin scope required to mutate System-tier platform
// models. Mirrors glossary-service's System-tier admin gate.
const scopeAdminWrite = "admin:write"

// requireAdminScope verifies the Bearer admin RS256 JWT and that it carries the
// required scope, writing the error + returning false on any failure. System-tier
// platform models are platform-owned: only an admin principal (never a regular
// user) may mutate them (CLAUDE.md › User Boundaries). Fail closed when the verify
// key is unconfigured. A regular HS256 user token never satisfies adminjwt.Verify
// (RS256 only), so this is not bypassable with a normal login.
func (s *Server) requireAdminScope(w http.ResponseWriter, r *http.Request, scope string) (adminjwt.AdminClaims, bool) {
	if s.adminPub == nil {
		writeError(w, http.StatusServiceUnavailable, "M03_ADMIN_UNAVAILABLE", "platform-model administration is not configured")
		return adminjwt.AdminClaims{}, false
	}
	auth := r.Header.Get("Authorization")
	if !strings.HasPrefix(auth, "Bearer ") {
		writeError(w, http.StatusUnauthorized, "M03_ADMIN_UNAUTHORIZED", "valid admin Bearer token required")
		return adminjwt.AdminClaims{}, false
	}
	claims, err := adminjwt.Verify(strings.TrimPrefix(auth, "Bearer "), s.adminPub, s.adminKID)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "M03_ADMIN_UNAUTHORIZED", "invalid admin token")
		return adminjwt.AdminClaims{}, false
	}
	if !slices.Contains(claims.Scopes, scope) {
		writeError(w, http.StatusForbidden, "M03_ADMIN_FORBIDDEN", "missing required admin scope")
		return adminjwt.AdminClaims{}, false
	}
	return claims, true
}

// pemOrBase64 accepts either a raw PEM ("BEGIN") or a base64-encoded PEM (an
// env-var-friendly single line).
func pemOrBase64(v string) []byte {
	if strings.Contains(v, "BEGIN") {
		return []byte(v)
	}
	if dec, err := base64.StdEncoding.DecodeString(strings.TrimSpace(v)); err == nil {
		return dec
	}
	return []byte(v)
}

func parseUUIDParam(w http.ResponseWriter, r *http.Request, name string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, name))
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid "+name)
		return uuid.Nil, false
	}
	return id, true
}

func (s *Server) encryptSecret(raw string) (string, string, error) {
	block, err := aes.NewCipher(s.secretKey)
	if err != nil {
		return "", "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", "", err
	}
	ciphertext := gcm.Seal(nil, nonce, []byte(raw), nil)
	joined := append(nonce, ciphertext...)
	return base64.StdEncoding.EncodeToString(joined), uuid.NewString(), nil
}

func (s *Server) decryptSecret(ciphertext string) (string, error) {
	if ciphertext == "" {
		return "", nil
	}
	block, err := aes.NewCipher(s.secretKey)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	joined, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}
	if len(joined) < gcm.NonceSize() {
		return "", fmt.Errorf("invalid ciphertext")
	}
	nonce := joined[:gcm.NonceSize()]
	body := joined[gcm.NonceSize():]
	plain, err := gcm.Open(nil, nonce, body, nil)
	if err != nil {
		return "", err
	}
	return string(plain), nil
}

func (s *Server) createProviderCredential(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		ProviderKind    string `json:"provider_kind"`
		DisplayName     string `json:"display_name"`
		Secret          string `json:"secret"`
		EndpointBaseURL string `json:"endpoint_base_url"`
		Active          *bool  `json:"active"`
		APIStandard     string `json:"api_standard"`    // openai_compatible, anthropic, ollama, lm_studio
		MaxConcurrency  *int   `json:"max_concurrency"` // nil/≤0 → unlimited (request-as-demand)
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	if strings.TrimSpace(in.ProviderKind) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "provider_kind is required")
		return
	}
	if strings.TrimSpace(in.DisplayName) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "display_name is required")
		return
	}
	// Default api_standard based on provider_kind
	apiStandard := in.APIStandard
	if apiStandard == "" {
		switch in.ProviderKind {
		case "anthropic":
			apiStandard = "anthropic"
		case "ollama":
			apiStandard = "ollama"
		case "lm_studio":
			apiStandard = "lm_studio"
		default:
			apiStandard = "openai_compatible"
		}
	}
	encryptedSecret, keyRef, err := s.encryptSecret(in.Secret)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_SECRET_ENCRYPT_FAILED", "failed to encrypt secret")
		return
	}
	status := "active"
	if in.Active != nil && !*in.Active {
		status = "disabled"
	}
	var out struct {
		ProviderCredentialID uuid.UUID `json:"provider_credential_id"`
		ProviderKind         string    `json:"provider_kind"`
		DisplayName          string    `json:"display_name"`
		EndpointBaseURL      *string   `json:"endpoint_base_url"`
		Status               string    `json:"status"`
		CreatedAt            time.Time `json:"created_at"`
		UpdatedAt            time.Time `json:"updated_at"`
		MaxConcurrency       *int      `json:"max_concurrency"`
	}
	err = s.pool.QueryRow(r.Context(), `
INSERT INTO provider_credentials(owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, secret_key_ref, status, api_standard, max_concurrency)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
RETURNING provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at, max_concurrency
`, userID, in.ProviderKind, in.DisplayName, nullableString(in.EndpointBaseURL), encryptedSecret, keyRef, status, apiStandard, nullableConcurrency(in.MaxConcurrency)).
		Scan(&out.ProviderCredentialID, &out.ProviderKind, &out.DisplayName, &out.EndpointBaseURL, &out.Status, &out.CreatedAt, &out.UpdatedAt, &out.MaxConcurrency)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_SAVE_FAILED", "failed to create provider credential")
		return
	}
	writeJSON(w, http.StatusCreated, out)
}

func nullableString(v string) any {
	if strings.TrimSpace(v) == "" {
		return nil
	}
	return v
}

// nullableConcurrency normalizes a max_concurrency input: nil or ≤0 → NULL
// (unlimited; the DB column's "no cap" sentinel), a positive value → that cap.
func nullableConcurrency(v *int) any {
	if v == nil || *v <= 0 {
		return nil
	}
	return *v
}

// optionalInt distinguishes "field absent from the JSON body" (Present=false →
// leave the column untouched on PATCH) from "field present, possibly null"
// (Present=true, Value=nil → clear to unlimited). A plain *int can't tell these
// apart — both decode to nil — which would make clearing-to-unlimited impossible.
type optionalInt struct {
	Present bool
	Value   *int
}

func (o *optionalInt) UnmarshalJSON(b []byte) error {
	o.Present = true
	if string(b) == "null" {
		o.Value = nil
		return nil
	}
	var v int
	if err := json.Unmarshal(b, &v); err != nil {
		return err
	}
	o.Value = &v
	return nil
}

func (s *Server) listProviderCredentials(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at,
       (secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret, api_standard, max_concurrency
FROM provider_credentials
WHERE owner_user_id=$1 AND status <> 'archived'
ORDER BY created_at DESC
`, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to list providers")
		return
	}
	defer rows.Close()
	type row struct {
		ProviderCredentialID uuid.UUID `json:"provider_credential_id"`
		ProviderKind         string    `json:"provider_kind"`
		DisplayName          string    `json:"display_name"`
		EndpointBaseURL      *string   `json:"endpoint_base_url"`
		Status               string    `json:"status"`
		CreatedAt            time.Time `json:"created_at"`
		UpdatedAt            time.Time `json:"updated_at"`
		HasSecret            bool      `json:"has_secret"`
		APIStandard          string    `json:"api_standard"`
		MaxConcurrency       *int      `json:"max_concurrency"`
	}
	items := make([]row, 0)
	for rows.Next() {
		var item row
		if err := rows.Scan(&item.ProviderCredentialID, &item.ProviderKind, &item.DisplayName, &item.EndpointBaseURL, &item.Status, &item.CreatedAt, &item.UpdatedAt, &item.HasSecret, &item.APIStandard, &item.MaxConcurrency); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to parse provider row")
			return
		}
		items = append(items, item)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) patchProviderCredential(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "provider_credential_id")
	if !ok {
		return
	}
	var in struct {
		DisplayName     *string     `json:"display_name"`
		Secret          *string     `json:"secret"`
		EndpointBaseURL *string     `json:"endpoint_base_url"`
		Active          *bool       `json:"active"`
		APIStandard     *string     `json:"api_standard"`
		MaxConcurrency  optionalInt `json:"max_concurrency"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	var encryptedSecret any
	var keyRef any
	if in.Secret != nil {
		cipherText, ref, err := s.encryptSecret(*in.Secret)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_SECRET_ENCRYPT_FAILED", "failed to encrypt secret")
			return
		}
		encryptedSecret = cipherText
		keyRef = ref
	}
	statusPatch := any(nil)
	if in.Active != nil {
		if *in.Active {
			statusPatch = "active"
		} else {
			statusPatch = "disabled"
		}
	}
	cmdTag, err := s.pool.Exec(r.Context(), `
UPDATE provider_credentials
SET
  display_name = COALESCE($3, display_name),
  endpoint_base_url = COALESCE($4, endpoint_base_url),
  secret_ciphertext = COALESCE($5, secret_ciphertext),
  secret_key_ref = COALESCE($6, secret_key_ref),
  status = COALESCE($7, status),
  api_standard = COALESCE($8, api_standard),
  -- present-aware: $9 true → set $10 (nil clears to unlimited); false → keep
  max_concurrency = CASE WHEN $9::bool THEN $10 ELSE max_concurrency END,
  updated_at = now()
WHERE provider_credential_id = $1 AND owner_user_id = $2 AND status <> 'archived'
`, id, userID, in.DisplayName, in.EndpointBaseURL, encryptedSecret, keyRef, statusPatch, in.APIStandard,
		in.MaxConcurrency.Present, nullableConcurrency(in.MaxConcurrency.Value))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_UPDATE_FAILED", "failed to update provider credential")
		return
	}
	if cmdTag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	s.getProviderCredentialByID(w, r, userID, id)
}

func (s *Server) getProviderCredentialByID(w http.ResponseWriter, r *http.Request, userID, id uuid.UUID) {
	var out struct {
		ProviderCredentialID uuid.UUID `json:"provider_credential_id"`
		ProviderKind         string    `json:"provider_kind"`
		DisplayName          string    `json:"display_name"`
		EndpointBaseURL      *string   `json:"endpoint_base_url"`
		Status               string    `json:"status"`
		CreatedAt            time.Time `json:"created_at"`
		UpdatedAt            time.Time `json:"updated_at"`
		HasSecret            bool      `json:"has_secret"`
		APIStandard          string    `json:"api_standard"`
		MaxConcurrency       *int      `json:"max_concurrency"`
	}
	err := s.pool.QueryRow(r.Context(), `
SELECT provider_credential_id, provider_kind, display_name, endpoint_base_url, status, created_at, updated_at,
       (secret_ciphertext IS NOT NULL AND secret_ciphertext <> '') AS has_secret, api_standard, max_concurrency
FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2
`, id, userID).Scan(&out.ProviderCredentialID, &out.ProviderKind, &out.DisplayName, &out.EndpointBaseURL, &out.Status, &out.CreatedAt, &out.UpdatedAt, &out.HasSecret, &out.APIStandard, &out.MaxConcurrency)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to fetch provider credential")
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) deleteProviderCredential(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "provider_credential_id")
	if !ok {
		return
	}
	cmdTag, err := s.pool.Exec(r.Context(), `
UPDATE provider_credentials
SET status='archived', updated_at=now()
WHERE provider_credential_id=$1 AND owner_user_id=$2
`, id, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_DELETE_FAILED", "failed to delete provider credential")
		return
	}
	if cmdTag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) providerHealth(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	cred, ok := s.getCredentialOwned(r.Context(), userID, w, r)
	if !ok {
		return
	}
	adapter, err := provider.ResolveAdapter(cred.ProviderKind, s.client)
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_PROVIDER_KIND_UNSUPPORTED", "unsupported provider kind")
		return
	}
	if err := adapter.HealthCheck(r.Context(), cred.EndpointBaseURL, cred.Secret); err != nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"provider_credential_id": cred.ProviderCredentialID,
			"healthy":                false,
			"message":                err.Error(),
		})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"provider_credential_id": cred.ProviderCredentialID,
		"healthy":                true,
		"message":                "ok",
	})
}

type credentialRow struct {
	ProviderCredentialID uuid.UUID
	ProviderKind         string
	EndpointBaseURL      string
	Secret               string
}

func (s *Server) getCredentialOwned(ctx context.Context, userID uuid.UUID, w http.ResponseWriter, r *http.Request) (*credentialRow, bool) {
	id, ok := parseUUIDParam(w, r, "provider_credential_id")
	if !ok {
		return nil, false
	}
	var out credentialRow
	var secretCipher string
	err := s.pool.QueryRow(ctx, `
SELECT provider_credential_id, provider_kind, COALESCE(endpoint_base_url,''), COALESCE(secret_ciphertext,'')
FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2 AND status='active'
`, id, userID).Scan(&out.ProviderCredentialID, &out.ProviderKind, &out.EndpointBaseURL, &secretCipher)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return nil, false
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to load provider credential")
		return nil, false
	}
	// D-PROXY-01 — providerHealth + listProviderInventory (the two
	// callers) both use cred.Secret to make upstream HTTP calls.
	// An empty cipher → empty Authorization → cryptic upstream 401.
	// Early-fail with a clear 500 so ops can spot the bad row.
	if secretCipher == "" {
		writeError(w, http.StatusInternalServerError,
			"M03_MISSING_CREDENTIAL",
			"provider credential has no ciphertext")
		return nil, false
	}
	secret, err := s.decryptSecret(secretCipher)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_SECRET_DECRYPT_FAILED", "failed to decrypt secret")
		return nil, false
	}
	out.Secret = secret
	return &out, true
}

func (s *Server) listProviderInventory(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	cred, ok := s.getCredentialOwned(r.Context(), userID, w, r)
	if !ok {
		return
	}
	refresh := r.URL.Query().Get("refresh") == "true"
	if refresh {
		if err := s.syncInventory(r.Context(), cred); err != nil {
			writeError(w, http.StatusBadGateway, "M03_PROVIDER_SYNC_FAILED", "failed to sync provider inventory")
			return
		}
	}
	rows, err := s.pool.Query(r.Context(), `
SELECT provider_model_name, context_length, capability_flags, synced_at
FROM provider_inventory_models
WHERE provider_credential_id=$1
ORDER BY provider_model_name ASC
`, cred.ProviderCredentialID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_INVENTORY_QUERY_FAILED", "failed to list provider inventory")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	var syncedAt *time.Time
	for rows.Next() {
		var modelName string
		var contextLength *int
		var flagsBytes []byte
		var rowSyncedAt time.Time
		if err := rows.Scan(&modelName, &contextLength, &flagsBytes, &rowSyncedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_INVENTORY_QUERY_FAILED", "failed to parse inventory row")
			return
		}
		flags := map[string]any{}
		_ = json.Unmarshal(flagsBytes, &flags)
		items = append(items, map[string]any{
			"provider_model_name": modelName,
			"context_length":      contextLength,
			"capability_flags":    flags,
		})
		syncedAt = &rowSyncedAt
	}
	if err := rows.Err(); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_INVENTORY_QUERY_FAILED", "failed to read inventory rows")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "synced_at": syncedAt})
}

func (s *Server) syncInventory(ctx context.Context, cred *credentialRow) error {
	adapter, err := provider.ResolveAdapter(cred.ProviderKind, s.client)
	if err != nil {
		return err
	}
	models, err := adapter.ListModels(ctx, cred.EndpointBaseURL, cred.Secret)
	if err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `DELETE FROM provider_inventory_models WHERE provider_credential_id=$1`, cred.ProviderCredentialID); err != nil {
		return err
	}
	for _, m := range models {
		flags, _ := json.Marshal(m.CapabilityFlags)
		if _, err := tx.Exec(ctx, `
INSERT INTO provider_inventory_models(provider_credential_id, provider_model_name, context_length, capability_flags, synced_at)
VALUES ($1,$2,$3,$4,now())
`, cred.ProviderCredentialID, m.ProviderModelName, m.ContextLength, flags); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

// parsePricingInput validates a caller-supplied `pricing` payload, shared by
// createUserModel and patchUserModel/D-PRICING-REFRESH so the two write paths
// can never drift on what counts as valid pricing. Returns (nil, nil) when
// `raw` is empty/absent/JSON-null (caller decides the fallback — a default-
// table pre-fill on create, "leave unchanged" on patch); returns a 400-shaped
// error on malformed JSON (would otherwise brick the model with a 500 at
// every job — an unmarshal failure in ModelPricing) or a negative rate
// (would otherwise silently disable the spend guardrail for that model).
func parsePricingInput(raw json.RawMessage) (json.RawMessage, error) {
	if len(raw) == 0 || string(raw) == "null" {
		return nil, nil
	}
	var p billing.Pricing
	if uErr := json.Unmarshal(raw, &p); uErr != nil {
		return nil, fmt.Errorf("invalid pricing: %w", uErr)
	}
	if vErr := p.Validate(); vErr != nil {
		return nil, vErr
	}
	return raw, nil
}

func (s *Server) createUserModel(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		ProviderCredentialID string          `json:"provider_credential_id"`
		ProviderModelName    string          `json:"provider_model_name"`
		ContextLength        *int            `json:"context_length"`
		Alias                string          `json:"alias"`
		CapabilityFlags      map[string]any  `json:"capability_flags"`
		Tags                 []modelTag      `json:"tags"`
		Notes                string          `json:"notes"`
		Pricing              json.RawMessage `json:"pricing,omitempty"` // Phase 6a
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	credentialID, err := uuid.Parse(in.ProviderCredentialID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid provider_credential_id")
		return
	}
	if strings.TrimSpace(in.ProviderModelName) == "" {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "provider_model_name is required")
		return
	}
	var providerKind string
	err = s.pool.QueryRow(r.Context(), `
SELECT provider_kind FROM provider_credentials
WHERE provider_credential_id=$1 AND owner_user_id=$2 AND status='active'
`, credentialID, userID).Scan(&providerKind)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_PROVIDER_NOT_FOUND", "provider credential not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PROVIDER_QUERY_FAILED", "failed to resolve provider")
		return
	}
	if (providerKind == "ollama" || providerKind == "lm_studio") && (in.ContextLength == nil || *in.ContextLength <= 0) {
		writeError(w, http.StatusBadRequest, "M03_MODEL_CONTEXT_REQUIRED", "context_length is required for ollama/lm_studio")
		return
	}
	// /review-impl HIGH: the check above only fires for ollama/lm_studio (where
	// context_length is required); any other provider could still supply an
	// explicit 0/negative context_length with no guard at all.
	if in.ContextLength != nil && *in.ContextLength <= 0 {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "context_length must be positive")
		return
	}
	flagsBytes, _ := json.Marshal(in.CapabilityFlags)

	// Phase 6a — pricing pre-fill. An explicit `pricing` from the caller
	// wins (validated by parsePricingInput, shared with patchUserModel/D-PRICING-
	// REFRESH so the two write paths can't drift on what's an acceptable rate);
	// otherwise the default price table seeds known cloud text models. An
	// unknown model is left empty ('{}') so the spend guardrail fails closed
	// (402) until the user prices it (design §3.2).
	pricingJSON, perr := parsePricingInput(in.Pricing)
	if perr != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", perr.Error())
		return
	}
	if pricingJSON == nil {
		pricingJSON = []byte("{}")
		if def, ok := billing.DefaultPricing(providerKind, in.ProviderModelName); ok {
			if b, mErr := json.Marshal(def); mErr == nil {
				pricingJSON = b
			}
		}
	}

	var out userModelRow
	err = s.pool.QueryRow(r.Context(), `
INSERT INTO user_models(owner_user_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, capability_flags, notes, pricing)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
RETURNING user_model_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, is_active, is_favorite, capability_flags, notes, created_at, updated_at
`, userID, credentialID, providerKind, in.ProviderModelName, in.ContextLength, nullableString(in.Alias), flagsBytes, in.Notes, pricingJSON).
		Scan(&out.UserModelID, &out.ProviderCredentialID, &out.ProviderKind, &out.ProviderModelName, &out.ContextLength, &out.Alias, &out.IsActive, &out.IsFavorite, &out.CapabilityFlags, &out.Notes, &out.CreatedAt, &out.UpdatedAt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_CREATE_FAILED", "failed to create user model")
		return
	}
	if err := s.replaceUserModelTags(r.Context(), out.UserModelID, in.Tags); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_TAGS_FAILED", "failed to save tags")
		return
	}
	s.writeUserModel(w, r, userID, out.UserModelID)
}

type modelTag struct {
	TagName string `json:"tag_name"`
	Note    string `json:"note"`
}

type userModelRow struct {
	UserModelID          uuid.UUID
	ProviderCredentialID uuid.UUID
	ProviderKind         string
	ProviderModelName    string
	ContextLength        *int
	Alias                *string
	IsActive             bool
	IsFavorite           bool
	CapabilityFlags      []byte
	Pricing              []byte
	Notes                string
	SortOrder            *int
	CreatedAt            time.Time
	UpdatedAt            time.Time
}

func (s *Server) listUserModels(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	includeInactive := r.URL.Query().Get("include_inactive") != "false"
	onlyFavorites := r.URL.Query().Get("only_favorites") == "true"
	providerFilter := r.URL.Query().Get("provider_kind")
	capabilityFilter := r.URL.Query().Get("capability")
	query := `
SELECT user_model_id FROM user_models WHERE owner_user_id=$1
`
	args := []any{userID}
	argPos := 2
	if !includeInactive {
		query += fmt.Sprintf(" AND is_active=$%d", argPos)
		args = append(args, true)
		argPos++
	}
	if onlyFavorites {
		query += fmt.Sprintf(" AND is_favorite=$%d", argPos)
		args = append(args, true)
		argPos++
	}
	if providerFilter != "" {
		query += fmt.Sprintf(" AND provider_kind=$%d", argPos)
		args = append(args, providerFilter)
		argPos++
	}
	if capabilityFilter != "" {
		// Validate: only lowercase letters and underscores (prevent JSON injection)
		valid := true
		for _, c := range capabilityFilter {
			if !((c >= 'a' && c <= 'z') || c == '_') {
				valid = false
				break
			}
		}
		if valid && len(capabilityFilter) <= 30 {
			// capability_flags exists in TWO historical schemas in the data (LW-PLAN F-4):
			//   canonical:  {"chat": true}            (boolean capability keys)
			//   legacy:     {"_capability": "chat"}   (single string key + metadata)
			// plus undeclared ('{}' / absent). Match BOTH schemas. Additionally, treat
			// undeclared as chat-capable by default: most BYOK/local (lm_studio) models
			// never self-declare and there's no UI to set flags, so requiring an explicit
			// chat flag would hide them from every chat/LLM picker (knowledge build,
			// regenerate-bio, change-model) even though they work in chat/translation/
			// extraction (which don't filter by capability). Non-chat caps (embedding, …)
			// stay strict — an undeclared model must NOT be silently offered there.
			boolArg := fmt.Sprintf(`{"%s": true}`, capabilityFilter)
			if capabilityFilter == "chat" {
				query += fmt.Sprintf(` AND (capability_flags @> $%d::jsonb OR capability_flags->>'_capability' = $%d OR capability_flags = '{}'::jsonb)`, argPos, argPos+1)
			} else {
				query += fmt.Sprintf(` AND (capability_flags @> $%d::jsonb OR capability_flags->>'_capability' = $%d)`, argPos, argPos+1)
			}
			args = append(args, boolArg, capabilityFilter)
			argPos += 2
		}
	}
	// A user-defined custom sort_order wins ((8)-residual): the drag-reorder in the
	// shared ModelPicker persists here. Un-ordered models (sort_order NULL) sort AFTER
	// the ordered ones, falling back to favorites-first / newest-first — so favorites
	// still get a pinned section for free whenever the user hasn't set an explicit order.
	query += " ORDER BY sort_order ASC NULLS LAST, is_favorite DESC, created_at DESC"
	rows, err := s.pool.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to list user models")
		return
	}
	defer rows.Close()
	items := make([]any, 0)
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to parse user model")
			return
		}
		model, err := s.readUserModel(r.Context(), userID, id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to fetch user model detail")
			return
		}
		if model != nil {
			items = append(items, model)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// reorderUserModels persists a user-defined custom sort order ((8)-residual). The
// body is {ordered_ids: [uuid,...]}; the ids the caller OWNS are assigned
// sort_order = index (0..N-1) in one transaction, and every OTHER model the caller
// owns has its sort_order reset to NULL — so a partial reorder is well-defined
// (only the listed ids are "ordered"; the rest fall back to favorites-first). Ids
// the caller does not own are silently ignored (owner-scoped UPDATE). Returns the
// updated list (same shape/order as GET /user-models).
func (s *Server) reorderUserModels(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	var in struct {
		OrderedIDs []uuid.UUID `json:"ordered_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	tx, err := s.pool.Begin(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_REORDER_FAILED", "failed to reorder user models")
		return
	}
	defer tx.Rollback(r.Context())
	// Clear any existing order for THIS user first, then stamp the new positions.
	// Both statements are owner-scoped so a caller can never touch another tenant's
	// rows (a foreign id in ordered_ids simply matches nothing).
	//
	// review-impl MED: the clear deliberately has NO `sort_order IS NOT NULL`
	// predicate. Under READ COMMITTED that predicate matches (and locks) NOTHING
	// when the rows start all-NULL (the common first-reorder case), so two
	// concurrent reorders would fail to serialize and merge into a corrupt order.
	// Updating every owner row forces a row lock on each, so a second concurrent
	// reorder blocks on the first's commit and then re-reads a consistent base.
	if _, err := tx.Exec(r.Context(),
		`UPDATE user_models SET sort_order=NULL, updated_at=now() WHERE owner_user_id=$1`,
		userID); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_REORDER_FAILED", "failed to reorder user models")
		return
	}
	// Dedupe defensively (a direct API caller could send repeats; the FE never
	// does) so a repeated id can't leave a gap / overwrite its own lead position.
	seen := make(map[uuid.UUID]bool, len(in.OrderedIDs))
	pos := 0
	for _, id := range in.OrderedIDs {
		if seen[id] {
			continue
		}
		seen[id] = true
		if _, err := tx.Exec(r.Context(),
			`UPDATE user_models SET sort_order=$3, updated_at=now() WHERE user_model_id=$1 AND owner_user_id=$2`,
			id, userID, pos); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_REORDER_FAILED", "failed to reorder user models")
			return
		}
		pos++
	}
	if err := tx.Commit(r.Context()); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_REORDER_FAILED", "failed to reorder user models")
		return
	}
	// Return the freshly-ordered list so the client can adopt server truth in one round-trip.
	s.listUserModels(w, r)
}

func (s *Server) readUserModel(ctx context.Context, userID, id uuid.UUID) (map[string]any, error) {
	var row userModelRow
	err := s.pool.QueryRow(ctx, `
SELECT user_model_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, is_active, is_favorite, capability_flags, pricing, notes, sort_order, created_at, updated_at
FROM user_models
WHERE user_model_id=$1 AND owner_user_id=$2
`, id, userID).Scan(&row.UserModelID, &row.ProviderCredentialID, &row.ProviderKind, &row.ProviderModelName, &row.ContextLength, &row.Alias, &row.IsActive, &row.IsFavorite, &row.CapabilityFlags, &row.Pricing, &row.Notes, &row.SortOrder, &row.CreatedAt, &row.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	flags := map[string]any{}
	_ = json.Unmarshal(row.CapabilityFlags, &flags)
	// pricing JSONB (input_per_mtok, output_per_mtok, per_image, …) — additive,
	// read-only here; the FE ModelPicker renders the "$0 local"/"$" hint from it.
	pricing := map[string]any{}
	_ = json.Unmarshal(row.Pricing, &pricing)
	tags, err := s.loadTags(ctx, row.UserModelID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"user_model_id":          row.UserModelID,
		"provider_credential_id": row.ProviderCredentialID,
		"provider_kind":          row.ProviderKind,
		"provider_model_name":    row.ProviderModelName,
		"context_length":         row.ContextLength,
		"alias":                  row.Alias,
		"is_active":              row.IsActive,
		"is_favorite":            row.IsFavorite,
		"capability_flags":       flags,
		"pricing":                pricing,
		"notes":                  row.Notes,
		"sort_order":             row.SortOrder,
		"tags":                   tags,
		"created_at":             row.CreatedAt,
		"updated_at":             row.UpdatedAt,
	}, nil
}

func (s *Server) loadTags(ctx context.Context, userModelID uuid.UUID) ([]modelTag, error) {
	rows, err := s.pool.Query(ctx, `SELECT tag_name, COALESCE(note,'') FROM user_model_tags WHERE user_model_id=$1 ORDER BY tag_name ASC`, userModelID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	tags := make([]modelTag, 0)
	for rows.Next() {
		var t modelTag
		if err := rows.Scan(&t.TagName, &t.Note); err != nil {
			return nil, err
		}
		tags = append(tags, t)
	}
	return tags, nil
}

func (s *Server) patchUserModel(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var in struct {
		Alias           *string         `json:"alias"`
		ContextLength   *int            `json:"context_length"`
		CapabilityFlags map[string]any  `json:"capability_flags"`
		Notes           *string         `json:"notes"`
		Pricing         json.RawMessage `json:"pricing,omitempty"` // D-PRICING-REFRESH
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	// /review-impl HIGH: createUserModel rejects a non-positive context_length
	// (for ollama/lm_studio, where it's required) but patch had no such guard at
	// all, so an edit-after-create could write 0/negative and every downstream
	// scale_by_window/clamp consumer would treat it as "resolved" — producing a
	// negative max_tokens sent straight to the LLM provider.
	if in.ContextLength != nil && *in.ContextLength <= 0 {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "context_length must be positive")
		return
	}
	// D-PRICING-REFRESH — until this fix, `pricing` was frozen at model-creation
	// time forever: patchUserModel had no field for it at all, so a user who
	// registered a paid model (e.g. gpt-4o) with a stale/wrong pre-filled rate
	// had no way to correct it. Validated by the SAME parsePricingInput as
	// create, before the UPDATE — an invalid rate never reaches the DB.
	pricingJSON, perr := parsePricingInput(in.Pricing)
	if perr != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", perr.Error())
		return
	}
	flagsBytes, _ := json.Marshal(in.CapabilityFlags)
	cmd, err := s.pool.Exec(r.Context(), `
UPDATE user_models
SET alias=COALESCE($3, alias),
    context_length=COALESCE($4, context_length),
    capability_flags=CASE WHEN $5::jsonb IS NULL THEN capability_flags ELSE $5 END,
    notes=COALESCE($6, notes),
    pricing=CASE WHEN $7::jsonb IS NULL THEN pricing ELSE $7 END,
    updated_at=now()
WHERE user_model_id=$1 AND owner_user_id=$2
`, id, userID, in.Alias, in.ContextLength, nullJSON(flagsBytes, in.CapabilityFlags != nil), in.Notes, nullJSON(pricingJSON, pricingJSON != nil))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_UPDATE_FAILED", "failed to patch user model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	s.writeUserModel(w, r, userID, id)
}

func nullJSON(b []byte, valid bool) any {
	if !valid {
		return nil
	}
	return b
}

// suggestUserModelPricing — D-PRICING-REFRESH: GET .../pricing/suggest returns
// a best-effort live-pricing suggestion from OpenRouter's public catalog for
// this model's (provider_kind, provider_model_name), for the user to review
// and optionally apply via the existing pricing PATCH. Never writes anything
// itself — `{"found": false}` (never an error) when the provider_kind has no
// OpenRouter mapping, the model isn't in OpenRouter's current catalog (e.g. a
// retired version), or OpenRouter is unreachable.
func (s *Server) suggestUserModelPricing(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var providerKind, modelName string
	err := s.pool.QueryRow(r.Context(), `
SELECT provider_kind, provider_model_name FROM user_models
WHERE user_model_id=$1 AND owner_user_id=$2
`, id, userID).Scan(&providerKind, &modelName)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to resolve user model")
		return
	}
	suggestion := billing.FetchOpenRouterPricing(r.Context(), s.client, providerKind, modelName)
	writeJSON(w, http.StatusOK, suggestion)
}

func (s *Server) deleteUserModel(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	cmd, err := s.pool.Exec(r.Context(), `DELETE FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2`, id, userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_DELETE_FAILED", "failed to delete user model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) patchUserModelActivation(w http.ResponseWriter, r *http.Request) {
	s.patchUserModelBoolField(w, r, "is_active", "M03_USER_MODEL_ACTIVATION_FAILED")
}

func (s *Server) patchUserModelFavorite(w http.ResponseWriter, r *http.Request) {
	s.patchUserModelBoolField(w, r, "is_favorite", "M03_USER_MODEL_FAVORITE_FAILED")
}

func (s *Server) patchUserModelBoolField(w http.ResponseWriter, r *http.Request, field, errorCode string) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var in map[string]bool
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	value, ok := in[field]
	if !ok {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", field+" is required")
		return
	}
	cmd, err := s.pool.Exec(r.Context(), fmt.Sprintf(`
UPDATE user_models SET %s=$3, updated_at=now()
WHERE user_model_id=$1 AND owner_user_id=$2
`, field), id, userID, value)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errorCode, "failed to patch user model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	s.writeUserModel(w, r, userID, id)
}

func (s *Server) putUserModelTags(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	id, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		return
	}
	var in struct {
		Tags []modelTag `json:"tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	var exists bool
	err := s.pool.QueryRow(r.Context(), `SELECT EXISTS(SELECT 1 FROM user_models WHERE user_model_id=$1 AND owner_user_id=$2)`, id, userID).Scan(&exists)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to check user model")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	if err := s.replaceUserModelTags(r.Context(), id, in.Tags); err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_TAGS_FAILED", "failed to save tags")
		return
	}
	s.writeUserModel(w, r, userID, id)
}

func (s *Server) replaceUserModelTags(ctx context.Context, userModelID uuid.UUID, tags []modelTag) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if _, err := tx.Exec(ctx, `DELETE FROM user_model_tags WHERE user_model_id=$1`, userModelID); err != nil {
		return err
	}
	for _, t := range tags {
		name := strings.TrimSpace(t.TagName)
		if name == "" {
			continue
		}
		if _, err := tx.Exec(ctx, `INSERT INTO user_model_tags(user_model_id, tag_name, note) VALUES ($1,$2,$3)`, userModelID, name, nullableString(t.Note)); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *Server) writeUserModel(w http.ResponseWriter, r *http.Request, userID, id uuid.UUID) {
	item, err := s.readUserModel(r.Context(), userID, id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_USER_MODEL_QUERY_FAILED", "failed to fetch user model")
		return
	}
	if item == nil {
		writeError(w, http.StatusNotFound, "M03_USER_MODEL_NOT_FOUND", "user model not found")
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (s *Server) createPlatformModel(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	var in struct {
		ProviderKind    string         `json:"provider_kind"`
		ProviderModel   string         `json:"provider_model_name"`
		DisplayName     string         `json:"display_name"`
		Status          string         `json:"status"`
		PricingPolicy   map[string]any `json:"pricing_policy"`
		QuotaPolicyRef  string         `json:"quota_policy_ref"`
		CapabilityFlags map[string]any `json:"capability_flags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	pricing, _ := json.Marshal(in.PricingPolicy)
	flags, _ := json.Marshal(in.CapabilityFlags)
	_, err := s.pool.Exec(r.Context(), `
INSERT INTO platform_models(provider_kind, provider_model_name, display_name, status, pricing_policy, quota_policy_ref, capability_flags)
VALUES ($1,$2,$3,$4,$5,$6,$7)
`, in.ProviderKind, in.ProviderModel, in.DisplayName, in.Status, pricing, nullableString(in.QuotaPolicyRef), flags)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_CREATE_FAILED", "failed to create platform model")
		return
	}
	s.writePlatformModelList(w, r)
}

func (s *Server) listPlatformModels(w http.ResponseWriter, r *http.Request) {
	_, ok := s.auth(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	s.writePlatformModelList(w, r)
}

func (s *Server) writePlatformModelList(w http.ResponseWriter, r *http.Request) {
	rows, err := s.pool.Query(r.Context(), `
SELECT platform_model_id, provider_kind, provider_model_name, display_name, status, pricing_policy, quota_policy_ref, capability_flags, created_at, updated_at
FROM platform_models
ORDER BY created_at DESC
`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_QUERY_FAILED", "failed to list platform models")
		return
	}
	defer rows.Close()
	items := make([]map[string]any, 0)
	for rows.Next() {
		var id uuid.UUID
		var kind, modelName, displayName, status string
		var pricingRaw []byte
		var quotaRef *string
		var flagsRaw []byte
		var createdAt, updatedAt time.Time
		if err := rows.Scan(&id, &kind, &modelName, &displayName, &status, &pricingRaw, &quotaRef, &flagsRaw, &createdAt, &updatedAt); err != nil {
			writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_QUERY_FAILED", "failed to parse platform model")
			return
		}
		pricing := map[string]any{}
		flags := map[string]any{}
		_ = json.Unmarshal(pricingRaw, &pricing)
		_ = json.Unmarshal(flagsRaw, &flags)
		items = append(items, map[string]any{
			"platform_model_id":   id,
			"provider_kind":       kind,
			"provider_model_name": modelName,
			"display_name":        displayName,
			"status":              status,
			"pricing_policy":      pricing,
			"quota_policy_ref":    quotaRef,
			"capability_flags":    flags,
			"created_at":          createdAt,
			"updated_at":          updatedAt,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *Server) patchPlatformModel(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	id, ok := parseUUIDParam(w, r, "platform_model_id")
	if !ok {
		return
	}
	var in struct {
		DisplayName     *string        `json:"display_name"`
		Status          *string        `json:"status"`
		PricingPolicy   map[string]any `json:"pricing_policy"`
		QuotaPolicyRef  *string        `json:"quota_policy_ref"`
		CapabilityFlags map[string]any `json:"capability_flags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "M03_VALIDATION_ERROR", "invalid payload")
		return
	}
	pricing, _ := json.Marshal(in.PricingPolicy)
	flags, _ := json.Marshal(in.CapabilityFlags)
	cmd, err := s.pool.Exec(r.Context(), `
UPDATE platform_models
SET
  display_name=COALESCE($2, display_name),
  status=COALESCE($3, status),
  pricing_policy=CASE WHEN $4::jsonb IS NULL THEN pricing_policy ELSE $4 END,
  quota_policy_ref=COALESCE($5, quota_policy_ref),
  capability_flags=CASE WHEN $6::jsonb IS NULL THEN capability_flags ELSE $6 END,
  updated_at=now()
WHERE platform_model_id=$1
`, id, in.DisplayName, in.Status, nullJSON(pricing, in.PricingPolicy != nil), in.QuotaPolicyRef, nullJSON(flags, in.CapabilityFlags != nil))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_UPDATE_FAILED", "failed to patch platform model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PLATFORM_MODEL_NOT_FOUND", "platform model not found")
		return
	}
	s.writePlatformModelList(w, r)
}

func (s *Server) deletePlatformModel(w http.ResponseWriter, r *http.Request) {
	if _, ok := s.requireAdminScope(w, r, scopeAdminWrite); !ok {
		return
	}
	id, ok := parseUUIDParam(w, r, "platform_model_id")
	if !ok {
		return
	}
	cmd, err := s.pool.Exec(r.Context(), `DELETE FROM platform_models WHERE platform_model_id=$1`, id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "M03_PLATFORM_MODEL_DELETE_FAILED", "failed to delete platform model")
		return
	}
	if cmd.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "M03_PLATFORM_MODEL_NOT_FOUND", "platform model not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) verifyUserModel(w http.ResponseWriter, r *http.Request) {
	userID, ok := s.auth(r)
	if !ok {
		VerifyRequestsTotal.WithLabelValues(OutcomeAuthFailed).Inc()
		writeError(w, http.StatusUnauthorized, "M03_UNAUTHORIZED", "unauthorized")
		return
	}
	modelID, ok := parseUUIDParam(w, r, "user_model_id")
	if !ok {
		VerifyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		return
	}

	var providerKind, providerModelName, endpointBaseURL, secretCipher string
	var capabilityFlagsJSON []byte
	err := s.pool.QueryRow(r.Context(), `
SELECT um.provider_kind, um.provider_model_name,
       COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,''),
       COALESCE(um.capability_flags, '{}')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelID, userID).Scan(&providerKind, &providerModelName, &endpointBaseURL, &secretCipher, &capabilityFlagsJSON)
	if err == pgx.ErrNoRows {
		VerifyRequestsTotal.WithLabelValues(OutcomeModelNotFound).Inc()
		writeError(w, http.StatusNotFound, "M03_MODEL_NOT_FOUND", "user model not found or inactive")
		return
	}
	if err != nil {
		VerifyRequestsTotal.WithLabelValues(OutcomeQueryFailed).Inc()
		writeError(w, http.StatusInternalServerError, "M03_MODEL_QUERY_FAILED", "failed to resolve user model")
		return
	}

	// web_search is an external SERVICE, not an LLM/model: it is verified by a real
	// /search "ping" and it TOLERATES a keyless backend (e.g. self-hosted SearXNG
	// with an empty secret). So handle it HERE, before the generic empty-secret
	// guard below — that guard legitimately rejects an empty secret for chat /
	// embedding / rerank, but a keyless web-search credential is valid.
	{
		var earlyCaps map[string]any
		_ = json.Unmarshal(capabilityFlagsJSON, &earlyCaps)
		if detectPrimaryCapability(earlyCaps) == "web_search" {
			wsSecret := ""
			if secretCipher != "" {
				dec, derr := s.decryptSecret(secretCipher)
				if derr != nil {
					VerifyRequestsTotal.WithLabelValues(OutcomeDecryptFailed).Inc()
					writeError(w, http.StatusInternalServerError, "M03_SECRET_DECRYPT_FAILED", "failed to decrypt provider secret")
					return
				}
				wsSecret = dec
			}
			wsCtx, wsCancel := context.WithTimeout(r.Context(), 30*time.Second)
			defer wsCancel()
			wsStart := time.Now()
			result := s.verifyWebSearch(wsCtx, endpointBaseURL, wsSecret)
			result["latency_ms"] = time.Since(wsStart).Milliseconds()
			result["capability"] = "web_search"
			VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
			writeJSON(w, http.StatusOK, result)
			return
		}
	}

	// D-PROXY-01 — invalid state guard. Verify endpoints pre-K17.2a
	// would decrypt empty → forward empty Authorization → get a
	// cryptic 401 from upstream. Early-fail with a clear code.
	if secretCipher == "" {
		VerifyRequestsTotal.WithLabelValues(OutcomeMissingCredential).Inc()
		writeError(w, http.StatusInternalServerError,
			"M03_MISSING_CREDENTIAL",
			"user_model has no provider credential ciphertext")
		return
	}

	secret, err := s.decryptSecret(secretCipher)
	if err != nil {
		VerifyRequestsTotal.WithLabelValues(OutcomeDecryptFailed).Inc()
		writeError(w, http.StatusInternalServerError, "M03_SECRET_DECRYPT_FAILED", "failed to decrypt provider secret")
		return
	}

	// Parse capability flags to determine verification strategy
	var caps map[string]any
	json.Unmarshal(capabilityFlagsJSON, &caps)

	capability := detectPrimaryCapability(caps)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	start := time.Now()

	switch capability {
	case "stt":
		// STT verify: send a tiny WAV with silence → expect JSON with "text" field
		result := s.verifySTT(ctx, endpointBaseURL, secret, providerModelName)
		result["latency_ms"] = time.Since(start).Milliseconds()
		result["capability"] = "stt"
		VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
		writeJSON(w, http.StatusOK, result)
		return

	case "tts":
		// TTS verify: send short text → expect audio bytes back
		result := s.verifyTTS(ctx, endpointBaseURL, secret, providerModelName)
		result["latency_ms"] = time.Since(start).Milliseconds()
		result["capability"] = "tts"
		VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
		writeJSON(w, http.StatusOK, result)
		return

	case "image_gen":
		// Image verify: just check models endpoint (generation is too slow/costly)
		result := s.verifyModelsEndpoint(ctx, endpointBaseURL, secret)
		result["latency_ms"] = time.Since(start).Milliseconds()
		result["capability"] = "image_gen"
		VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
		writeJSON(w, http.StatusOK, result)
		return

	case "video_gen":
		// Video verify: just check models endpoint
		result := s.verifyModelsEndpoint(ctx, endpointBaseURL, secret)
		result["latency_ms"] = time.Since(start).Milliseconds()
		result["capability"] = "video_gen"
		VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
		writeJSON(w, http.StatusOK, result)
		return

	case "rerank":
		// C3 (BL-10): real /v1/rerank round-trip via the user's BYOK credential —
		// proves the model actually ranks (a chat ping would not).
		result := s.verifyRerank(ctx, endpointBaseURL, secret, providerModelName)
		result["latency_ms"] = time.Since(start).Milliseconds()
		result["capability"] = "rerank"
		VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
		writeJSON(w, http.StatusOK, result)
		return

	default:
		// Chat / unknown: use existing adapter invoke with "Hi"
	}

	verifyClient := &http.Client{Timeout: 5 * time.Minute}
	adapter, err := provider.ResolveAdapter(providerKind, verifyClient)
	if err != nil {
		VerifyRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusConflict, "M03_PROVIDER_ROUTE_VIOLATION", "unsupported provider kind")
		return
	}

	pingInput := map[string]any{
		"messages": []map[string]any{
			{"role": "user", "content": "Hi"},
		},
	}

	output, _, invokeErr := adapter.Invoke(ctx, endpointBaseURL, secret, providerModelName, pingInput)

	latencyMs := time.Since(start).Milliseconds()

	if invokeErr != nil {
		// Verification completed with a negative answer. Counter-wise
		// this is a provider-side failure — the verify RPC did its job,
		// but the upstream provider rejected the ping.
		VerifyRequestsTotal.WithLabelValues(OutcomeProviderError).Inc()
		writeJSON(w, http.StatusOK, map[string]any{
			"verified":   false,
			"latency_ms": latencyMs,
			"capability": "chat",
			"error":      invokeErr.Error(),
		})
		return
	}

	preview := ""
	if content, ok := output["content"]; ok {
		preview = fmt.Sprintf("%v", content)
	} else if choices, ok := output["choices"]; ok {
		preview = fmt.Sprintf("%v", choices)
	}
	if len(preview) > 200 {
		preview = preview[:200] + "…"
	}

	VerifyRequestsTotal.WithLabelValues(OutcomeOK).Inc()
	writeJSON(w, http.StatusOK, map[string]any{
		"verified":         true,
		"latency_ms":       latencyMs,
		"capability":       "chat",
		"response_preview": preview,
	})
}

// canEmbed reports whether a user_model's capability_flags permit an embedding dispatch
// (K12.1). It is fail-OPEN: an empty/unknown flag set returns true (the upstream provider
// still rejects a non-embedding model with a 4xx — see internalEmbed), so a model whose
// flags were never populated is never wrongly blocked. It returns false ONLY when the
// flags DEFINITIVELY classify the model as some OTHER capability, letting the caller reject
// with a precise 400 before paying the provider round-trip. Mirrors the two historical
// capability_flags schemas: a boolean flag ({"embedding": true}) or the `_capability`
// metadata string ({"_capability": "embedding"}).
func canEmbed(caps map[string]any) bool {
	if len(caps) == 0 {
		return true // unknown — fail open
	}
	// Explicit positive: a boolean embedding flag, or the canonical _capability token.
	if b, ok := caps["embedding"].(bool); ok && b {
		return true
	}
	if c, _ := caps["_capability"].(string); c == "embedding" || c == "embed" {
		return true
	}
	// Reject ONLY on an AFFIRMATIVELY-detected non-embedding capability. "chat" is NOT
	// here on purpose: it is the discovery DEFAULT/fallback (classifyOpenAIModel returns
	// "chat" when the name matches no other heuristic), so a "chat" tag is NOT a reliable
	// embedding-exclusion — a BYOK embedding model whose name misses the "embed" heuristic
	// (e.g. a local "bge-m3") is tagged chat. Treat chat as fail-open so we never block a
	// legitimate embedding call; the upstream provider still rejects a true chat model
	// with a 4xx (mapped to EMBED_MODEL_INVALID).
	for _, other := range []string{"rerank", "stt", "tts", "image_gen", "video_gen"} {
		if b, ok := caps[other].(bool); ok && b {
			return false
		}
	}
	if c, _ := caps["_capability"].(string); c != "" && c != "chat" {
		return false
	}
	// No affirmative non-embedding signal → fail open.
	return true
}

// detectPrimaryCapability determines which verification strategy to use based on capability_flags.
// Priority: stt > tts > image_gen > video_gen > chat (default)
func detectPrimaryCapability(caps map[string]any) string {
	// C3 (BL-10): include rerank so its verify path does a real /v1/rerank
	// round-trip instead of falling through to the chat ping.
	for _, cap := range []string{"stt", "tts", "image_gen", "video_gen", "rerank", "web_search"} {
		if v, ok := caps[cap]; ok {
			if b, ok := v.(bool); ok && b {
				return cap
			}
		}
	}
	// Inventory-discovered rerank (C2) may carry the capability as the `_capability`
	// metadata string rather than a boolean flag — recognize that form too.
	if c, _ := caps["_capability"].(string); c == "rerank" || c == "web_search" {
		return c
	}
	return "chat"
}

// verifyRerank exercises a REAL /v1/rerank round-trip with a tiny fixed
// query+documents set and returns the ranked scores. This proves the model
// actually ranks (a generic chat ping would not). BYOK: baseURL+secret come from
// the user's resolved provider credential — no platform rerank config, no
// per-service URL/token env, no hardcoded model name. The call goes through the
// canonical provider-registry rerank path (provider.Rerank), the only place
// rerank HTTP lives.
func (s *Server) verifyRerank(ctx context.Context, baseURL, secret, modelName string) map[string]any {
	query := "What is the capital of France?"
	documents := []string{
		"Bananas are a good source of potassium.",
		"Paris is the capital of France.",
		"The Eiffel Tower is a landmark in Paris.",
	}
	client := &http.Client{Timeout: 60 * time.Second}
	results, err := provider.Rerank(ctx, client, baseURL, secret, modelName, query, documents)
	if err != nil {
		return map[string]any{"verified": false, "error": err.Error()}
	}
	// provider.Rerank already sorts descending by score.
	scores := make([]map[string]any, 0, len(results))
	for _, r := range results {
		scores = append(scores, map[string]any{
			"index":           r.Index,
			"relevance_score": r.Score,
		})
	}
	out := map[string]any{
		"verified": true,
		"scores":   scores,
	}
	if len(results) > 0 {
		out["top_index"] = results[0].Index
		out["top_score"] = results[0].Score
	}
	return out
}

// verifyWebSearch runs a minimal real /search "ping" through the canonical
// provider.WebSearch (the only place web-search HTTP lives) to prove the user's
// BYOK web-search backend is reachable and answering. A KEYLESS backend (empty
// secret, e.g. self-hosted SearXNG) is supported — provider.WebSearch omits the
// Authorization header when secret=="". This surfaces the common misconfig the
// generic chat-ping could not: an endpoint that resolves to nothing (e.g.
// `localhost` from inside a container instead of `host.docker.internal`).
func (s *Server) verifyWebSearch(ctx context.Context, baseURL, secret string) map[string]any {
	results, _, err := provider.WebSearch(ctx, s.invokeClient, baseURL, secret, "ping",
		provider.WebSearchOptions{MaxResults: 1})
	if err != nil {
		return map[string]any{"verified": false, "error": err.Error()}
	}
	return map[string]any{"verified": true, "result_count": len(results)}
}

// verifySTT sends a tiny silent WAV to the STT endpoint and checks for a text response.
func (s *Server) verifySTT(ctx context.Context, baseURL, secret, modelName string) map[string]any {
	base := strings.TrimRight(baseURL, "/")

	// Generate a 0.5s silent WAV (16kHz mono 16-bit)
	sampleRate := 16000
	nSamples := sampleRate / 2 // 0.5 seconds
	audioData := make([]byte, nSamples*2)
	dataSize := len(audioData)
	// WAV header
	header := make([]byte, 44)
	copy(header[0:4], "RIFF")
	putLE32(header[4:], uint32(36+dataSize))
	copy(header[8:12], "WAVE")
	copy(header[12:16], "fmt ")
	putLE32(header[16:], 16)
	putLE16(header[20:], 1) // PCM
	putLE16(header[22:], 1) // mono
	putLE32(header[24:], uint32(sampleRate))
	putLE32(header[28:], uint32(sampleRate*2))
	putLE16(header[32:], 2)  // block align
	putLE16(header[34:], 16) // bits per sample
	copy(header[36:40], "data")
	putLE32(header[40:], uint32(dataSize))

	wavData := append(header, audioData...)

	// Build multipart form
	var body bytes.Buffer
	boundary := "----LoreWeaveVerifyBoundary"
	body.WriteString("--" + boundary + "\r\n")
	body.WriteString("Content-Disposition: form-data; name=\"file\"; filename=\"verify.wav\"\r\n")
	body.WriteString("Content-Type: audio/wav\r\n\r\n")
	body.Write(wavData)
	body.WriteString("\r\n--" + boundary + "\r\n")
	body.WriteString("Content-Disposition: form-data; name=\"model\"\r\n\r\n")
	body.WriteString(modelName)
	body.WriteString("\r\n--" + boundary + "\r\n")
	body.WriteString("Content-Disposition: form-data; name=\"language\"\r\n\r\n")
	body.WriteString("en")
	body.WriteString("\r\n--" + boundary + "--\r\n")

	req, err := http.NewRequestWithContext(ctx, "POST", base+"/v1/audio/transcriptions", &body)
	if err != nil {
		return map[string]any{"verified": false, "error": "failed to create request: " + err.Error()}
	}
	req.Header.Set("Content-Type", "multipart/form-data; boundary="+boundary)
	if secret != "" {
		req.Header.Set("Authorization", "Bearer "+secret)
	}

	resp, err := s.invokeClient.Do(req)
	if err != nil {
		return map[string]any{"verified": false, "error": "request failed: " + err.Error()}
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != 200 {
		preview := string(respBody)
		if len(preview) > 200 {
			preview = preview[:200]
		}
		return map[string]any{"verified": false, "error": fmt.Sprintf("STT returned %d: %s", resp.StatusCode, preview)}
	}

	// Check response has "text" field
	var result map[string]any
	if err := json.Unmarshal(respBody, &result); err != nil {
		return map[string]any{"verified": false, "error": "response is not valid JSON"}
	}

	text, _ := result["text"].(string)
	return map[string]any{
		"verified":         true,
		"response_preview": text,
	}
}

// verifyTTS sends a short text to the TTS endpoint and checks for audio bytes.
// Fetches /v1/voices first to pick a valid voice name (avoids hardcoding "alloy").
func (s *Server) verifyTTS(ctx context.Context, baseURL, secret, modelName string) map[string]any {
	base := strings.TrimRight(baseURL, "/")

	// Try to fetch the first available voice
	voiceName := "alloy" // fallback
	voiceReq, _ := http.NewRequestWithContext(ctx, "GET", base+"/v1/voices", nil)
	if secret != "" {
		voiceReq.Header.Set("Authorization", "Bearer "+secret)
	}
	if voiceResp, err := s.client.Do(voiceReq); err == nil {
		defer voiceResp.Body.Close()
		var voiceData struct {
			Voices []struct {
				VoiceID string `json:"voice_id"`
			} `json:"voices"`
		}
		if voiceBody, _ := io.ReadAll(voiceResp.Body); json.Unmarshal(voiceBody, &voiceData) == nil && len(voiceData.Voices) > 0 {
			voiceName = voiceData.Voices[0].VoiceID
		}
	}

	payload, _ := json.Marshal(map[string]any{
		"model":           modelName,
		"voice":           voiceName,
		"input":           "Hello",
		"response_format": "wav",
	})

	req, err := http.NewRequestWithContext(ctx, "POST", base+"/v1/audio/speech", bytes.NewReader(payload))
	if err != nil {
		return map[string]any{"verified": false, "error": "failed to create request: " + err.Error()}
	}
	req.Header.Set("Content-Type", "application/json")
	if secret != "" {
		req.Header.Set("Authorization", "Bearer "+secret)
	}

	resp, err := s.invokeClient.Do(req)
	if err != nil {
		return map[string]any{"verified": false, "error": "request failed: " + err.Error()}
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != 200 {
		preview := string(respBody)
		if len(preview) > 200 {
			preview = preview[:200]
		}
		return map[string]any{"verified": false, "error": fmt.Sprintf("TTS returned %d: %s", resp.StatusCode, preview)}
	}

	contentType := resp.Header.Get("Content-Type")
	return map[string]any{
		"verified":         true,
		"response_preview": fmt.Sprintf("%d bytes audio (%s)", len(respBody), contentType),
	}
}

// verifyModelsEndpoint checks if the provider's /v1/models endpoint is reachable.
// Used for image_gen and video_gen where actual generation is too slow/costly for verification.
func (s *Server) verifyModelsEndpoint(ctx context.Context, baseURL, secret string) map[string]any {
	base := strings.TrimRight(baseURL, "/")

	// Try /v1/models first, then /health
	for _, path := range []string{"/v1/models", "/health"} {
		req, err := http.NewRequestWithContext(ctx, "GET", base+path, nil)
		if err != nil {
			continue
		}
		if secret != "" {
			req.Header.Set("Authorization", "Bearer "+secret)
		}

		resp, err := s.client.Do(req) // use short-timeout client
		if err != nil {
			continue
		}
		resp.Body.Close()

		if resp.StatusCode == 200 {
			return map[string]any{
				"verified":         true,
				"response_preview": fmt.Sprintf("%s returned 200", path),
			}
		}
	}

	return map[string]any{"verified": false, "error": "neither /v1/models nor /health returned 200"}
}

// WAV header helpers
func putLE16(b []byte, v uint16) { b[0] = byte(v); b[1] = byte(v >> 8) }
func putLE32(b []byte, v uint32) {
	b[0] = byte(v)
	b[1] = byte(v >> 8)
	b[2] = byte(v >> 16)
	b[3] = byte(v >> 24)
}

// getModelContextWindow returns the context window size (in tokens) for a given model, or
// `context_window: null` (`resolved: false`) when it genuinely cannot be determined. Called
// internally by the translation-worker before chunking a chapter. No auth required — internal
// only. IMPORTANT: this must never fabricate a number on failure — a guessed value (e.g. the
// historical flat 8192) is indistinguishable from a real one to the caller and silently drives
// real chunk-sizing math with the wrong window for any model whose real size differs (which is
// most of them). Callers decide their own conservative fallback for the genuinely-unknown case,
// same as chat-service's compute_target already does for context_length=None.
func (s *Server) getModelContextWindow(w http.ResponseWriter, r *http.Request) {
	unresolved := func() {
		writeJSON(w, http.StatusOK, map[string]any{"context_window": nil, "resolved": false})
	}
	resolved := func(n int) {
		writeJSON(w, http.StatusOK, map[string]any{"context_window": n, "resolved": true})
	}

	modelRefStr := chi.URLParam(r, "model_ref")
	modelRef, err := uuid.Parse(modelRefStr)
	if err != nil {
		unresolved()
		return
	}
	modelSource := r.URL.Query().Get("model_source")

	if modelSource == "platform_model" {
		var providerKind, providerModelName string
		err = s.pool.QueryRow(r.Context(),
			"SELECT provider_kind, provider_model_name FROM platform_models WHERE platform_model_id=$1 AND status='active'",
			modelRef,
		).Scan(&providerKind, &providerModelName)
		if err != nil {
			unresolved()
			return
		}
		adapter, err := provider.ResolveAdapter(providerKind, s.client)
		if err != nil {
			unresolved()
			return
		}
		models, err := adapter.ListModels(r.Context(), "", "")
		if err != nil {
			unresolved()
			return
		}
		for _, m := range models {
			if m.ProviderModelName == providerModelName && m.ContextLength != nil {
				resolved(*m.ContextLength)
				return
			}
		}
		unresolved()
		return
	}

	// user_model — look up context_length stored during inventory sync
	var contextLength *int
	err = s.pool.QueryRow(r.Context(),
		"SELECT context_length FROM user_models WHERE user_model_id=$1 AND is_active=true",
		modelRef,
	).Scan(&contextLength)
	if err != nil || contextLength == nil {
		unresolved()
		return
	}
	resolved(*contextLength)
}

// getInternalModelInfo resolves a model_ref to its provider_kind +
// provider_model_name (NO credentials). FD-27: worker-ai uses this to run a
// best-effort reasoning-model advisory before extraction (a reasoning model
// with thinking enabled silently swallows the JSON output → 0 entities/events).
// Mirrors getModelContextWindow's user_model / platform_model resolution.
func (s *Server) getInternalModelInfo(w http.ResponseWriter, r *http.Request) {
	modelRef, err := uuid.Parse(chi.URLParam(r, "model_ref"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "INTERNAL_VALIDATION_ERROR", "model_ref must be a uuid")
		return
	}
	modelSource := chi.URLParam(r, "model_source")

	var providerKind, providerModelName string
	if modelSource == "platform_model" {
		err = s.pool.QueryRow(r.Context(),
			"SELECT provider_kind, provider_model_name FROM platform_models WHERE platform_model_id=$1 AND status='active'",
			modelRef,
		).Scan(&providerKind, &providerModelName)
	} else { // user_model (default)
		err = s.pool.QueryRow(r.Context(),
			"SELECT provider_kind, provider_model_name FROM user_models WHERE user_model_id=$1 AND is_active=true",
			modelRef,
		).Scan(&providerKind, &providerModelName)
	}
	if err != nil {
		writeError(w, http.StatusNotFound, "MODEL_NOT_FOUND", "model not found or inactive")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"provider_kind":       providerKind,
		"provider_model_name": providerModelName,
	})
}

// recordSyncUsage logs a SYNCHRONOUS (non-streaming) model invocation to
// usage-billing's audit ledger via the shared billing.RecordUsage contract
// (P0-2 B4 — embed / rerank / web-search, which previously called no record path
// at all and were audit-invisible). Fire-and-forget on a detached context so it
// never adds latency to — nor is cancelled by — the caller's response; the
// GuardrailClient's own timeout bounds the goroutine. Nil-safe (router-only tests
// build no guardrail). Payloads are bounded (reference-first when huge), and a
// fresh uuidv7 request_id makes each call its own audit row. These sync paths are
// user_model-only (the handlers reject any other model_source before calling here).
// recordSyncUsage records one synchronous op (embed/rerank/web_search) to the
// ledger via the guardrail's RecordUsage HTTP path (Route A). costUSD is the
// authoritative per-model cost when the caller can compute it (embed: tokens ×
// pricing); nil leaves TotalCostUSD unset → usage-billing's flat fallback. rerank
// + web_search pass nil by design: they carry 0/0 tokens (a rerank scores docs;
// web_search is a per-call external service), so a per-token cost is meaningless —
// they need a per-call/per-request pricing dimension before a real cost lands
// (tracked D-B2-RERANK-WEBSEARCH-PRICING).
func (s *Server) recordSyncUsage(ctx context.Context, userID, modelRef uuid.UUID, operation, status string, inTok, outTok int, costUSD *float64, reqPayload, respPayload map[string]any) {
	if s.guardrail == nil {
		return
	}
	reqID, err := uuid.NewV7()
	if err != nil {
		return
	}
	if status == "" {
		status = "success"
	}
	detached := observability.DetachedContext(ctx)
	rec := billing.UsageRecord{
		RequestID:     reqID,
		OwnerUserID:   userID,
		ModelSource:   "user_model",
		ModelRef:      modelRef,
		Operation:     operation,
		InputTokens:   inTok,
		OutputTokens:  outTok,
		TotalCostUSD:  costUSD,
		RequestStatus: status,
		InputPayload:  boundedPayload(reqPayload),
		OutputPayload: boundedPayload(respPayload),
	}
	go func() {
		if err := s.guardrail.RecordUsage(detached, rec); err != nil {
			slog.Warn("sync usage record failed",
				"operation", operation, "request_id", reqID.String(), "err", err)
		}
	}()
}

// ── K12.1 — Embedding endpoint ──────────────────────────────────────────────

// internalRerank handles POST /internal/rerank — cross-encoder reranking for
// raw-search junk-rejection (E5B). BYOK (D-RERANK-NOT-BYOK): the rerank model is
// resolved per-user from provider-registry credentials exactly like
// /internal/embed — NO hardcoded model name and NO platform endpoint. The
// knowledge caller only calls this when the project has a rerank model set, and
// degrades to fusion order on any non-200, so rerank stays optional.
func (s *Server) internalRerank(w http.ResponseWriter, r *http.Request) {
	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "user_id query param required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "invalid user_id")
		return
	}
	var in struct {
		ModelSource string   `json:"model_source"`
		ModelRef    string   `json:"model_ref"`
		Query       string   `json:"query"`
		Documents   []string `json:"documents"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "invalid payload")
		return
	}
	if strings.TrimSpace(in.Query) == "" || len(in.Documents) == 0 {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "query and documents are required")
		return
	}
	if in.ModelRef == "" {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "model_ref required")
		return
	}
	modelRef, err := uuid.Parse(in.ModelRef)
	if err != nil {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "invalid model_ref")
		return
	}

	// Resolve the user's BYOK rerank credential — same tenant-isolated query as
	// internalEmbed (owner_user_id=$2 guarantees a user can only use their own model).
	var providerModelName, endpointBaseURL, secret string
	if in.ModelSource != "user_model" {
		writeError(w, http.StatusBadRequest, "RERANK_VALIDATION", "model_source must be user_model")
		return
	}
	var secretCipher string
	err = s.pool.QueryRow(r.Context(), `
SELECT um.provider_model_name, COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,'')
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(&providerModelName, &endpointBaseURL, &secretCipher)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "RERANK_MODEL_NOT_FOUND", "rerank model not found or inactive")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "RERANK_MODEL_QUERY_FAILED", "failed to resolve model")
		return
	}
	if secretCipher == "" {
		writeError(w, http.StatusInternalServerError, "RERANK_MISSING_CREDENTIAL", "user_model has no provider credential ciphertext")
		return
	}
	secret, err = s.decryptSecret(secretCipher)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "RERANK_SECRET_FAILED", "failed to decrypt secret")
		return
	}

	results, err := provider.Rerank(r.Context(), s.invokeClient, endpointBaseURL, secret, providerModelName, in.Query, in.Documents)
	if err != nil {
		// Upstream rerank failure ⇒ 502 so the caller degrades (not a client bug).
		// MED-1: record the FAILED call too — a provider error is exactly what you'd
		// want readable in the audit ledger; recording only successes recreates the
		// audit hole P0-2 closed on the streaming path.
		s.recordSyncUsage(r.Context(), userID, modelRef, "rerank", "provider_error", 0, 0, nil,
			map[string]any{"query": in.Query, "documents": in.Documents},
			map[string]any{"error": err.Error()})
		writeError(w, http.StatusBadGateway, "RERANK_UPSTREAM_ERROR", "rerank service error")
		return
	}
	// P0-2 (B4) — audit the rerank call: query + documents in, scored results out.
	// Rerank carries no token usage → tokens 0.
	s.recordSyncUsage(r.Context(), userID, modelRef, "rerank", "success", 0, 0, nil,
		map[string]any{"query": in.Query, "documents": in.Documents},
		map[string]any{"results": results})
	writeJSON(w, http.StatusOK, map[string]any{"model": providerModelName, "results": results})
}

// internalWebSearch handles POST /internal/web-search?user_id=...
// S5 — resolves the user's BYOK web_search model (capability_flags web_search) and runs
// a single web search via the provider adapter. The outward HTTP call lives ONLY in the
// provider package (provider-gateway invariant); this is the user-paid, BYOK resolution
// layer. INV-6 (Track D S-PRODUCER): provider.WebSearch already NEUTRALIZES every result
// (control/whitespace folding + caps) and DROPS unsafe/SSRF-y URLs, so everything written
// here is safe untrusted DATA — a consumer needs no further neutralization.
func (s *Server) internalWebSearch(w http.ResponseWriter, r *http.Request) {
	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		writeError(w, http.StatusBadRequest, "WEBSEARCH_VALIDATION", "user_id query param required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "WEBSEARCH_VALIDATION", "invalid user_id")
		return
	}
	var in struct {
		Query       string `json:"query"`
		MaxResults  int    `json:"max_results"`
		SearchDepth string `json:"search_depth"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeError(w, http.StatusBadRequest, "WEBSEARCH_VALIDATION", "invalid payload")
		return
	}
	if strings.TrimSpace(in.Query) == "" {
		writeError(w, http.StatusBadRequest, "WEBSEARCH_VALIDATION", "query is required")
		return
	}

	// The resolve → decrypt → search → audit pipeline lives in runWebSearch
	// (web_search_core.go), shared with the universal `web_search` MCP tool. This handler
	// is only the HTTP transport: map the sentinel errors onto status codes.
	out, err := s.runWebSearch(r.Context(), userID, in.Query, in.MaxResults, in.SearchDepth)
	switch {
	case errors.Is(err, errWebSearchNoModel):
		writeError(w, http.StatusNotFound, "WEBSEARCH_MODEL_NOT_FOUND",
			"no active web_search model configured — add a web-search provider credential in Settings")
		return
	case errors.Is(err, errWebSearchModelQuery):
		writeError(w, http.StatusInternalServerError, "WEBSEARCH_MODEL_QUERY_FAILED", "failed to resolve model")
		return
	case errors.Is(err, errWebSearchSecret):
		writeError(w, http.StatusInternalServerError, "WEBSEARCH_SECRET_FAILED", "failed to decrypt secret")
		return
	case errors.Is(err, errWebSearchUpstream):
		// Upstream provider failure ⇒ 502 so the caller degrades (not a client bug).
		writeError(w, http.StatusBadGateway, "WEBSEARCH_UPSTREAM_ERROR", "web search provider error")
		return
	case err != nil:
		writeError(w, http.StatusInternalServerError, "WEBSEARCH_FAILED", "web search failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"provider_model": out.ProviderModel,
		"answer":         out.Answer,
		"results":        out.Results,
	})
}

// internalEmbed handles POST /internal/embed.
// Resolves the user's embedding model via BYOK credentials and
// dispatches to the correct provider (OpenAI, Ollama, LM Studio).
func (s *Server) internalEmbed(w http.ResponseWriter, r *http.Request) {
	userIDStr := r.URL.Query().Get("user_id")
	if userIDStr == "" {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "user_id query param required")
		return
	}
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "invalid user_id")
		return
	}

	var in struct {
		ModelSource string   `json:"model_source"`
		ModelRef    string   `json:"model_ref"`
		Texts       []string `json:"texts"`
	}
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "invalid payload")
		return
	}
	if len(in.Texts) == 0 {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "texts must be non-empty")
		return
	}
	if in.ModelRef == "" {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "model_ref required")
		return
	}

	modelRef, err := uuid.Parse(in.ModelRef)
	if err != nil {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "invalid model_ref")
		return
	}

	// Resolve credentials — same pattern as doProxy (the
	// invokeModel / internalInvokeModel reference was retired in
	// Phase 4d alongside the handlers themselves).
	var providerKind, providerModelName, endpointBaseURL, secret string
	var pricingBytes []byte // P2·B2(c) — model pricing JSONB, for the authoritative embed cost
	if in.ModelSource == "user_model" {
		var secretCipher string
		// Scan capability_flags as raw bytes + json.Unmarshal — the established pattern
		// in this file (see the inventory + get-model scans). Do NOT scan jsonb directly
		// into a map[string]any.
		var capFlagsBytes []byte
		err = s.pool.QueryRow(r.Context(), `
SELECT um.user_model_id, um.provider_kind, um.provider_model_name, COALESCE(pc.endpoint_base_url,''), COALESCE(pc.secret_ciphertext,''), COALESCE(um.capability_flags,'{}'::jsonb), COALESCE(um.pricing,'{}'::jsonb)
FROM user_models um
JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.user_model_id=$1 AND um.owner_user_id=$2 AND um.is_active=true AND pc.status='active'
`, modelRef, userID).Scan(new(uuid.UUID), &providerKind, &providerModelName, &endpointBaseURL, &secretCipher, &capFlagsBytes, &pricingBytes)
		if err == pgx.ErrNoRows {
			EmbedRequestsTotal.WithLabelValues(OutcomeModelNotFound).Inc()
			writeError(w, http.StatusNotFound, "EMBED_MODEL_NOT_FOUND", "user model not found or inactive")
			return
		}
		if err != nil {
			EmbedRequestsTotal.WithLabelValues(OutcomeQueryFailed).Inc()
			writeError(w, http.StatusInternalServerError, "EMBED_MODEL_QUERY_FAILED", "failed to resolve model")
			return
		}
		// K12.1 — reject a model whose capability_flags definitively classify it as a
		// NON-embedding capability, before paying the provider round-trip. Fail-OPEN on an
		// empty/unknown flag set (the upstream provider still rejects a non-embedding model
		// with a 4xx → mapped to EMBED_MODEL_INVALID below), so this never breaks a model
		// whose flags were never populated.
		capFlags := map[string]any{}
		_ = json.Unmarshal(capFlagsBytes, &capFlags)
		if !canEmbed(capFlags) {
			EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
			writeError(w, http.StatusBadRequest, "EMBED_MODEL_NOT_EMBEDDING",
				"model is not classified as embedding-capable")
			return
		}
		// D-PROXY-01 — see doProxy comment.
		if secretCipher == "" {
			EmbedRequestsTotal.WithLabelValues(OutcomeMissingCredential).Inc()
			writeError(w, http.StatusInternalServerError,
				"EMBED_MISSING_CREDENTIAL",
				"user_model has no provider credential ciphertext")
			return
		}
		secret, err = s.decryptSecret(secretCipher)
		if err != nil {
			EmbedRequestsTotal.WithLabelValues(OutcomeDecryptFailed).Inc()
			writeError(w, http.StatusInternalServerError, "EMBED_SECRET_FAILED", "failed to decrypt secret")
			return
		}
	} else {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusBadRequest, "EMBED_VALIDATION", "model_source must be user_model")
		return
	}

	// Resolve adapter for the provider kind
	adapter, err := provider.ResolveAdapter(providerKind, s.invokeClient)
	if err != nil {
		EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
		writeError(w, http.StatusConflict, "EMBED_PROVIDER_ERROR", "failed to resolve adapter")
		return
	}

	// K12.1 — capability is validated above via canEmbed(capFlags): a model whose
	// capability_flags definitively classify it non-embedding is rejected before this
	// dispatch; an empty/unknown flag set falls through here and relies on the upstream
	// provider rejecting a non-embedding model with a 4xx (mapped to EMBED_MODEL_INVALID).

	// Dispatch embedding call — pass invokeClient (no fixed timeout,
	// request context controls cancellation)
	result, err := provider.Embed(r.Context(), adapter, s.invokeClient, endpointBaseURL, secret, providerModelName, in.Texts)
	if err != nil {
		errMsg := err.Error()
		// MED-1: audit the failed embed too (see internalRerank) — the texts that
		// triggered a provider error are the most useful thing to have in the ledger.
		s.recordSyncUsage(r.Context(), userID, modelRef, "embed", "provider_error", 0, 0, nil,
			map[string]any{"texts": in.Texts},
			map[string]any{"error": errMsg})
		// Map upstream 4xx (bad model, unsupported) to 400 so the caller
		// can distinguish "wrong model" from "provider down."
		if strings.Contains(errMsg, "provider error 4") || strings.Contains(errMsg, "does not support") {
			EmbedRequestsTotal.WithLabelValues(OutcomeValidationError).Inc()
			writeError(w, http.StatusBadRequest, "EMBED_MODEL_INVALID", errMsg)
			return
		}
		EmbedRequestsTotal.WithLabelValues(OutcomeProviderError).Inc()
		writeError(w, http.StatusBadGateway, "EMBED_PROVIDER_FAILED", errMsg)
		return
	}

	EmbedRequestsTotal.WithLabelValues(OutcomeOK).Inc()
	// P2·B2(c) — authoritative embed cost (D-REVIEW-EMBED-AUDIT-COST). Input-only,
	// via the shared billing.PriceEmbedding so the sync ledger cost matches the async
	// worker + S5a estimate math exactly. A missing/unpriced `pricing` → nil cost →
	// usage-billing's flat fallback (unchanged prior behavior), so an unpriced model
	// still records, just without an exact cost. Only reported prompt_tokens count.
	var embedCostPtr *float64
	if result.PromptTokens > 0 {
		var pricing billing.Pricing
		if uerr := json.Unmarshal(pricingBytes, &pricing); uerr == nil {
			if c, cerr := billing.PriceEmbedding(result.PromptTokens, pricing); cerr == nil {
				embedCostPtr = &c
			}
		}
	}
	// P0-2 (B4) — audit the embed call: the input texts in, vector count + dimension
	// out (NOT the vectors themselves — huge + useless in a ledger). input_tokens uses
	// the provider's reported prompt_tokens when present (0 → provider omitted it).
	s.recordSyncUsage(r.Context(), userID, modelRef, "embed", "success", result.PromptTokens, 0, embedCostPtr,
		map[string]any{"texts": in.Texts},
		map[string]any{"count": len(result.Embeddings), "dimension": result.Dimension, "model": result.Model})
	writeJSON(w, http.StatusOK, result)
}
