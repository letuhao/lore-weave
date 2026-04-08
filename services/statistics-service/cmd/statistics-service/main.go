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
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/statistics-service/internal/api"
	"github.com/loreweave/statistics-service/internal/config"
	"github.com/loreweave/statistics-service/internal/consumer"
	"github.com/loreweave/statistics-service/internal/migrate"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "statistics-service"))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
		os.Exit(1)
	}

	pool, err := pgxpool.New(context.Background(), cfg.DatabaseURL)
	if err != nil {
		slog.Error("db", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	if err := migrate.Up(context.Background(), pool); err != nil {
		slog.Error("migrate", "error", err)
		os.Exit(1)
	}

	// Connect Redis
	opts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		slog.Error("redis url", "error", err)
		os.Exit(1)
	}
	rdb := redis.NewClient(opts)
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		slog.Error("redis ping", "error", err)
		os.Exit(1)
	}
	defer rdb.Close()

	// Start event consumer in background
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cons := &consumer.Consumer{
		Pool:  pool,
		Redis: rdb,
		Cfg:   cfg,
	}
	go cons.Run(ctx)

	// Start HTTP server
	srv := api.NewServer(pool, cfg)
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

	cancel() // stop consumer

	shutCtx, shutCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutCancel()
	_ = httpSrv.Shutdown(shutCtx)
}
