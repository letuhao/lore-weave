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

	"github.com/loreweave/notification-service/internal/api"
	"github.com/loreweave/notification-service/internal/config"
	"github.com/loreweave/notification-service/internal/consumer"
	"github.com/loreweave/notification-service/internal/migrate"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "notification-service"))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config failed", "error", err)
		os.Exit(1)
	}

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

	// Phase 2d — LLM-jobs consumer. Optional: empty RABBITMQ_URL skips
	// the subscription so dev-without-broker keeps working.
	consumerCtx, consumerCancel := context.WithCancel(context.Background())
	defer consumerCancel()
	var llmConsumer *consumer.Consumer
	if cfg.RabbitMQURL != "" {
		llmConsumer, err = consumer.Start(consumerCtx, cfg.RabbitMQURL, pool, slog.Default())
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
