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

	"github.com/loreweave/glossary-service/internal/api"
	"github.com/loreweave/glossary-service/internal/config"
	"github.com/loreweave/glossary-service/internal/events"
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

	// Phase 6c — OpenTelemetry tracing. No-op when OTEL_EXPORTER_OTLP_ENDPOINT
	// is unset, so a broker-less / collector-less dev run still boots.
	shutdownTracer, err := observability.InitTracer(context.Background(), "glossary-service")
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

	// One-time, ledgered migration chain (schema_migrations). Each step runs EXACTLY
	// ONCE per database, then is skipped on subsequent boots — no more per-boot DDL/seed
	// replay (and no more CREATE+seed→DROP churn of the legacy system_kind_attributes
	// table; D-GKA-G4-SEED-CLEANUP). The ordered sequence + its load-bearing ordering
	// (FK targets, G4 cutover→cache→drop) lives in internal/migrate/ledger.go. The two
	// async background backfills below stay OUT of the chain (non-blocking, self-limiting).
	if err := migrate.RunChain(ctx, pool); err != nil {
		slog.Error("migrate chain", "error", err)
		os.Exit(1)
	}

	// Run the short-description backfill in a background goroutine so
	// the HTTP listener + healthcheck come up immediately. For a fresh
	// DB this completes in milliseconds; for a catalogue with many
	// thousands of entities it may take longer and we don't want to
	// block startup. The goroutine honours `ctx` so a shutdown signal
	// cancels the work mid-batch.
	go func(bctx context.Context) {
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
	}(ctx)

	// VG-1: glossary entity versioning. Enabled only when REDIS_URL is set.
	if cfg.RedisURL != "" {
		// Baseline existing entities (protect their current state before any edit)
		// in the background — a bulk INSERT…SELECT that must not block startup.
		go func(bctx context.Context) {
			if err := migrate.BackfillEntityRevisions(bctx, pool); err != nil {
				slog.Warn("backfill entity-revisions failed (non-fatal)", "error", err)
			}
		}(ctx)
		// Async revision-projection consumer off the event stream.
		if rc, err := events.NewRevisionConsumer(pool, cfg.RedisURL); err != nil {
			slog.Warn("revision-consumer init failed (history capture disabled)", "error", err)
		} else if rc != nil {
			go rc.Run(ctx)
		}
		// wiki-llm Phase-2 (§5.2) — wiki change-control capture: flags AI articles
		// stale (ledger) when a source they were built from changes. Never regenerates.
		if sc, err := events.NewStalenessConsumer(pool, cfg.RedisURL); err != nil {
			slog.Warn("staleness-consumer init failed (wiki staleness capture disabled)", "error", err)
		} else if sc != nil {
			go sc.Run(ctx)
		}
	}

	srv := api.NewServer(pool, cfg)

	// D-BATCH-RESEARCH-JOB M2 — the in-process batch entity-research worker. Drains
	// `pending` jobs (one paid web search per entity, reusing the deep-research core),
	// resuming from each job's cursor across restarts. Honours ctx for shutdown. Gated on
	// a web-search provider URL being configured (without it every job would just fail).
	if cfg.ProviderRegistryURL != "" {
		go srv.RunResearchWorker(ctx)
	}

	// D-GRANT-INSTANT-REVOKE — tail book-service grant revokes (Redis) → drop the
	// matching cached grant from this process's grant client at once (vs the TTL).
	if cfg.RedisURL != "" {
		if rc, err := events.NewGrantRevokeConsumer(cfg.RedisURL, srv.GrantClient()); err != nil {
			slog.Warn("grant-revoke-consumer init failed (instant revoke disabled; TTL still applies)", "error", err)
		} else if rc != nil {
			go rc.Run(ctx)
		}
	}

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
