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

	"github.com/loreweave/notification-service/internal/api"
	"github.com/loreweave/notification-service/internal/config"
	"github.com/loreweave/notification-service/internal/consumer"
	"github.com/loreweave/notification-service/internal/migrate"
	"github.com/loreweave/notification-service/internal/push"
)

func main() {
	// P2·A1 — shared JSON slog logger that injects otel_trace_id from the active
	// span on ctx-carrying log calls (slog.*Context). Replaces the bare SetDefault.
	observability.SetupLogging("notification-service")

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config failed", "error", err)
		os.Exit(1)
	}

	// Phase 6c — OpenTelemetry tracing. No-op when OTEL_EXPORTER_OTLP_ENDPOINT
	// is unset, so a broker-less / collector-less dev run still boots.
	shutdownTracer, err := observability.InitTracer(context.Background(), "notification-service")
	if err != nil {
		slog.Error("tracer init", "error", err)
		os.Exit(1)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdownTracer(ctx)
	}()

	ctx := context.Background()
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
	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		slog.Error("db connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	if err := migrate.Up(ctx, pool); err != nil {
		slog.Error("migrate failed", "error", err)
		os.Exit(1)
	}

	srv := api.NewServer(pool, cfg)
	httpSrv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}

	// M5 (cold-review LOW-1) — the secondary GC: periodically drop push subscriptions that have been
	// failing without a 404/410 Gone (persistent 5xx/timeout). The 410-prune is the primary GC; this
	// sweeps the rest so fail_count rows don't accumulate forever. No-op when push isn't configured.
	pushSweeper := push.NewSender(pool, push.VAPIDConfig{
		PublicKey:  cfg.VAPIDPublicKey,
		PrivateKey: cfg.VAPIDPrivateKey,
		Subscriber: cfg.VAPIDSubscriber,
	}, slog.Default())
	go func() {
		ticker := time.NewTicker(24 * time.Hour)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if n, err := pushSweeper.SweepStale(ctx, 20); err == nil && n > 0 {
					slog.Info("pushed subscriptions swept (stale)", "count", n)
				}
			}
		}
	}()

	// Phase 2d — LLM-jobs consumer. Optional: empty RABBITMQ_URL skips
	// the subscription so dev-without-broker keeps working.
	consumerCtx, consumerCancel := context.WithCancel(context.Background())
	defer consumerCancel()
	var llmConsumer *consumer.Consumer
	if cfg.RabbitMQURL != "" {
		// M5 — the consumer fires a content-free push on a fresh llm_job insert. Shares the same
		// VAPID config as the HTTP path (a no-op when VAPID isn't configured).
		pushSender := push.NewSender(pool, push.VAPIDConfig{
			PublicKey:  cfg.VAPIDPublicKey,
			PrivateKey: cfg.VAPIDPrivateKey,
			Subscriber: cfg.VAPIDSubscriber,
		}, slog.Default())
		llmConsumer, err = consumer.Start(consumerCtx, cfg.RabbitMQURL, pool, slog.Default(), pushSender)
		if err != nil {
			slog.Error("llm-jobs consumer failed to start", "error", err)
			os.Exit(1)
		}
		defer func() { _ = llmConsumer.Close() }()
	}

	go func() {
		slog.Info("listening", "addr", cfg.HTTPAddr)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("listen failed", "error", err)
			os.Exit(1)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	consumerCancel() // stop consumer goroutine before HTTP shutdown
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		slog.Error("shutdown error", "error", err)
	}
}
