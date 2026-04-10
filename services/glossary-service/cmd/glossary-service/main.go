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

	"github.com/loreweave/glossary-service/internal/api"
	"github.com/loreweave/glossary-service/internal/config"
	"github.com/loreweave/glossary-service/internal/migrate"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "glossary-service"))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
		os.Exit(1)
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("db", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	if err := migrate.Up(ctx, pool); err != nil {
		slog.Error("migrate", "error", err)
		os.Exit(1)
	}
	if err := migrate.Seed(ctx, pool); err != nil {
		slog.Error("seed", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpSnapshot(ctx, pool); err != nil {
		slog.Error("migrate snapshot", "error", err)
		os.Exit(1)
	}
	if err := migrate.BackfillSnapshots(ctx, pool); err != nil {
		slog.Error("backfill snapshots", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpSoftDelete(ctx, pool); err != nil {
		slog.Error("migrate soft-delete", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpGenreGroups(ctx, pool); err != nil {
		slog.Error("migrate genre-groups", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpWiki(ctx, pool); err != nil {
		slog.Error("migrate wiki", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpWikiSuggestions(ctx, pool); err != nil {
		slog.Error("migrate wiki-suggestions", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpExtraction(ctx, pool); err != nil {
		slog.Error("migrate extraction", "error", err)
		os.Exit(1)
	}

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

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		slog.Error("shutdown", "error", err)
	}
}
