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

	"github.com/loreweave/scheduler-service/internal/config"
	"github.com/loreweave/scheduler-service/internal/migrate"
	"github.com/loreweave/scheduler-service/internal/scheduler"
)

// scheduler-service (WS-3.1, spec 11) — the platform's one true scheduler hole, filled. It owns the
// clock: a tick driver claims due `scheduled_agent_runs` rows and enqueues the work onto existing
// consumers. worker-ai stays a pure executor (P3-D1). Go per the language rule (meta/domain infra).
func main() {
	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	poolCfg, err := pgxpool.ParseConfig(cfg.DatabaseURL)
	if err != nil {
		slog.Error("pool config", "error", err)
		os.Exit(1)
	}
	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		slog.Error("pool", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	if err := migrate.Up(ctx, pool); err != nil {
		slog.Error("migrate", "error", err)
		os.Exit(1)
	}

	enq := &scheduler.HTTPEnqueuer{
		ChatInternalURL: cfg.ChatInternalURL,
		InternalToken:   cfg.InternalToken,
		Client:          &http.Client{Timeout: 30 * time.Second},
	}
	driver := scheduler.NewDriver(pool, enq, cfg.ConsumerName)
	go driver.Run(ctx, cfg.TickInterval)
	slog.Info("scheduler-service started", "tick", cfg.TickInterval.String(), "consumer", cfg.ConsumerName)

	// Minimal health listener (liveness/readiness only — the scheduler has no request API).
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if err := pool.Ping(r.Context()); err != nil {
			http.Error(w, "db down", http.StatusServiceUnavailable)
			return
		}
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	srv := &http.Server{Addr: cfg.HTTPAddr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("http", "error", err)
		}
	}()

	<-ctx.Done()
	slog.Info("scheduler-service shutting down")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}
