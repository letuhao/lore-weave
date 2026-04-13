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
	"github.com/loreweave/glossary-service/internal/shortdesc"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "glossary-service"))

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "error", err)
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
	if err := migrate.UpEvidenceChapterIndex(ctx, pool); err != nil {
		slog.Error("migrate evidence-chapter-index", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpKnowledgeMemory(ctx, pool); err != nil {
		slog.Error("migrate knowledge-memory", "error", err)
		os.Exit(1)
	}
	if err := migrate.BackfillKnowledgeMemory(ctx, pool); err != nil {
		slog.Error("backfill knowledge-memory", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpShortDescAuto(ctx, pool); err != nil {
		slog.Error("migrate short-desc-auto", "error", err)
		os.Exit(1)
	}

	// Run the short-description backfill in a background goroutine so
	// the HTTP listener + healthcheck come up immediately. For a fresh
	// DB this completes in milliseconds; for a catalogue with many
	// thousands of entities it may take longer and we don't want to
	// block startup.
	go func() {
		bctx := context.Background()
		n, err := migrate.BackfillShortDescription(bctx, pool,
			func(name, description, kindName string) string {
				return shortdesc.Generate(name, description, kindName, shortdesc.DefaultMaxChars)
			})
		if err != nil {
			slog.Error("backfill short-description", "error", err, "processed", n)
			return
		}
		if n > 0 {
			slog.Info("backfill short-description complete", "processed", n)
		}
	}()

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
