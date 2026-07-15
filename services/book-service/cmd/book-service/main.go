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

	"github.com/loreweave/book-service/internal/api"
	"github.com/loreweave/book-service/internal/config"
	"github.com/loreweave/book-service/internal/migrate"
)

func main() {
	// P2·A1 — shared JSON slog logger that injects otel_trace_id from the active
	// span on ctx-carrying log calls (slog.*Context). Replaces the bare SetDefault.
	observability.SetupLogging("book-service")

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
		os.Exit(1)
	}

	// Phase 6c — OpenTelemetry tracing. No-op when OTEL_EXPORTER_OTLP_ENDPOINT
	// is unset, so a broker-less / collector-less dev run still boots.
	shutdownTracer, err := observability.InitTracer(context.Background(), "book-service")
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
		slog.Error("migrate", "error", err)
		os.Exit(1)
	}

	srv := api.NewServer(pool, cfg)
	httpSrv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}

	// 26 IX-3 — the index-freshness sweeper. Runs on a shutdown-scoped context so
	// a SIGTERM stops it cleanly. interval <= 0 disables it (RunReparseSweeper).
	sweepCtx, sweepCancel := context.WithCancel(context.Background())
	go srv.RunReparseSweeper(
		sweepCtx,
		time.Duration(cfg.ReparseSweepIntervalSeconds)*time.Second,
		cfg.ReparseSweepBatchSize,
	)
	// P4 (D-DIARY-SHRED-OUTBOX-RETRY) — converge any owed diary-DEK crypto-shred whose inline attempt
	// blipped. Same shutdown-scoped ctx; self-disables when crypto is off. Reuses the reparse cadence.
	go srv.RunDekShredSweeper(
		sweepCtx,
		time.Duration(cfg.ReparseSweepIntervalSeconds)*time.Second,
		cfg.ReparseSweepBatchSize,
	)

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

	sweepCancel()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		slog.Error("shutdown", "error", err)
	}
}
