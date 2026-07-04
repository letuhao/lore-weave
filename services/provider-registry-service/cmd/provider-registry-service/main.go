package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/observability"
	"github.com/loreweave/provider-registry-service/internal/api"
	"github.com/loreweave/provider-registry-service/internal/config"
	"github.com/loreweave/provider-registry-service/internal/jobs"
	"github.com/loreweave/provider-registry-service/internal/migrate"
	"github.com/loreweave/provider-registry-service/internal/storage"
)

func main() {
	// P2·A1 — shared JSON slog logger that injects otel_trace_id from the active
	// span on ctx-carrying log calls (slog.*Context). Replaces the bare SetDefault.
	observability.SetupLogging("provider-registry-service")

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
		os.Exit(1)
	}

	// Phase 6c — OpenTelemetry tracing. No-op when OTEL_EXPORTER_OTLP_ENDPOINT
	// is unset, so a collector-less dev run still boots.
	shutdownTracer, err := observability.InitTracer(context.Background(), "provider-registry-service")
	if err != nil {
		slog.Error("tracer init", "error", err)
		os.Exit(1)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdownTracer(ctx)
	}()
	poolCfg, err := pgxpool.ParseConfig(cfg.DatabaseURL)
	if err != nil {
		slog.Error("db config parse failed", "error", err)
		os.Exit(1)
	}
	if poolCfg.MaxConns == 0 || poolCfg.MaxConns == 4 {
		poolCfg.MaxConns = 10
	}
	if poolCfg.MinConns == 0 {
		poolCfg.MinConns = 2
	}
	if poolCfg.MaxConnLifetime == 0 {
		poolCfg.MaxConnLifetime = 30 * time.Minute
	}
	if poolCfg.MaxConnIdleTime == 0 {
		poolCfg.MaxConnIdleTime = 5 * time.Minute
	}
	pool, err := pgxpool.NewWithConfig(context.Background(), poolCfg)
	if err != nil {
		slog.Error("db connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := migrate.Up(context.Background(), pool); err != nil {
		slog.Error("migrate", "error", err)
		os.Exit(1)
	}

	// Phase 2c — RabbitMQ notifier for async-job terminal events.
	// Optional: empty RABBITMQ_URL falls back to NoopNotifier so dev
	// runs without a broker keep working.
	var notifier jobs.Notifier = jobs.NoopNotifier{}
	if cfg.RabbitMQURL != "" {
		n, err := jobs.NewRabbitMQNotifier(cfg.RabbitMQURL, slog.Default())
		if err != nil {
			slog.Error("rabbitmq notifier init failed", "error", err)
			os.Exit(1)
		}
		notifier = n
		slog.Info("rabbitmq notifier connected", "exchange", "loreweave.events")
		defer func() { _ = notifier.Close() }()
	} else {
		// P2·C — NoopNotifier silently drops every terminal event. That is fine for a
		// broker-less dev run, but in a real deployment it means users never get their
		// "job completed/failed" notifications — a misconfiguration worth surfacing
		// loudly ONCE at startup rather than discovering via missing notifications.
		slog.Warn("RABBITMQ_URL unset — terminal-event notifications DISABLED (NoopNotifier); users will not receive job-completion notifications")
	}

	// Phase 5e-β.2 — bootstrap audio cache for audio_gen URL mode.
	// Optional: empty MINIO_ENDPOINT or MINIO_EXTERNAL_URL leaves audioCache
	// nil; gateway boots without URL-mode support but b64_json mode works.
	var audioCache *storage.AudioCache
	if cfg.MinioEndpoint != "" && cfg.MinioExternalURL != "" {
		ac, err := storage.NewAudioCache(context.Background(), storage.Config{
			Endpoint:    cfg.MinioEndpoint,
			AccessKey:   cfg.MinioAccessKey,
			SecretKey:   cfg.MinioSecretKey,
			UseSSL:      cfg.MinioUseSSL,
			Bucket:      cfg.AudioCacheBucket,
			ExternalURL: cfg.MinioExternalURL,
		}, slog.Default())
		if err != nil {
			slog.Error("audio_cache bootstrap failed; audio_gen url-mode disabled", "error", err)
		} else {
			audioCache = ac
			slog.Info("audio_cache ready", "bucket", ac.Bucket(), "external_url", cfg.MinioExternalURL)
		}
	}

	srv := api.NewServer(pool, cfg, notifier, audioCache)
	httpSrv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		slog.Info("listening", "addr", cfg.HTTPAddr)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("listen", "error", err)
			os.Exit(1)
		}
	}()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(ctx)
}
