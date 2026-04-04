package main

import (
	"context"
	"log"
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
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}
	defer pool.Close()

	if err := migrate.Up(ctx, pool); err != nil {
		log.Fatalf("migrate: %v", err)
	}
	if err := migrate.Seed(ctx, pool); err != nil {
		log.Fatalf("seed: %v", err)
	}
	if err := migrate.UpSnapshot(ctx, pool); err != nil {
		log.Fatalf("migrate snapshot: %v", err)
	}
	if err := migrate.BackfillSnapshots(ctx, pool); err != nil {
		log.Fatalf("backfill snapshots: %v", err)
	}
	if err := migrate.UpSoftDelete(ctx, pool); err != nil {
		log.Fatalf("migrate soft-delete: %v", err)
	}
	if err := migrate.UpGenreGroups(ctx, pool); err != nil {
		log.Fatalf("migrate genre-groups: %v", err)
	}

	srv := api.NewServer(pool, cfg)
	httpSrv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Printf("glossary-service listening on %s", cfg.HTTPAddr)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown: %v", err)
	}
}
