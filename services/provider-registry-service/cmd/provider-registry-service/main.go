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

	"github.com/loreweave/provider-registry-service/internal/api"
	"github.com/loreweave/provider-registry-service/internal/config"
	"github.com/loreweave/provider-registry-service/internal/jobs"
	"github.com/loreweave/provider-registry-service/internal/migrate"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "provider-registry-service"))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
		os.Exit(1)
	}
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
	}

	srv := api.NewServer(pool, cfg, notifier)
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
