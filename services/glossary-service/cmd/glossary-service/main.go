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

	if err := migrate.Up(ctx, pool); err != nil {
		slog.Error("migrate", "error", err)
		os.Exit(1)
	}
	if err := migrate.Seed(ctx, pool); err != nil {
		slog.Error("seed", "error", err)
		os.Exit(1)
	}
	// Kind-alias epic E2: default aliases (faction→organization, generic→terminology).
	// MUST run after Seed (it references the seeded kinds) — idempotent, every startup.
	if err := migrate.SeedKindAliases(ctx, pool); err != nil {
		slog.Error("seed kind-aliases", "error", err)
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
	// C4 (K14) — transactional outbox for glossary.entity_updated events.
	if err := migrate.UpOutbox(ctx, pool); err != nil {
		slog.Error("migrate outbox", "error", err)
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
	// D-K2a-01 + D-K2a-02: defense-in-depth CHECK constraints on
	// short_description (non-empty + ≤500 runes). Must run AFTER
	// UpShortDescAuto because the backfill inside this step may
	// touch columns the prior migration ensures exist, and the
	// idempotent DO-block pattern is cheap if re-run.
	if err := migrate.UpShortDescConstraints(ctx, pool); err != nil {
		slog.Error("migrate short-desc-constraints", "error", err)
		os.Exit(1)
	}

	// lore-enrichment supplement layer (F-C13-1 + F-C13-2 / PO ruling B1):
	// enrichment content lives in its own table, FK→canonical entity, so it
	// stays structurally distinct from the original authored canon
	// (short_description). Runs after the entity table + short-desc migrations
	// since it references glossary_entities(entity_id).
	if err := migrate.UpEntityEnrichments(ctx, pool); err != nil {
		slog.Error("migrate entity-enrichments", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpEntityMerge(ctx, pool); err != nil {
		slog.Error("migrate entity-merge", "error", err)
		os.Exit(1)
	}
	if err := migrate.UpMergeCandidates(ctx, pool); err != nil {
		slog.Error("migrate merge-candidates", "error", err)
		os.Exit(1)
	}
	// D-GLOSSARY-VERSIONING (VG-1): entity_revisions history store.
	if err := migrate.UpEntityRevisions(ctx, pool); err != nil {
		slog.Error("migrate entity-revisions", "error", err)
		os.Exit(1)
	}
	// D-GLOSSARY-RAW-SEARCH-BE: pg_trgm + GIN trigram indexes for raw entity search.
	if err := migrate.UpGlossarySearch(ctx, pool); err != nil {
		slog.Error("migrate glossary-search", "error", err)
		os.Exit(1)
	}
	// D-GLOSSARY-SORT-BE (counts-sort): denormalized appearance counters + triggers.
	if err := migrate.UpEntityCounts(ctx, pool); err != nil {
		slog.Error("migrate entity-counts", "error", err)
		os.Exit(1)
	}
	// SS-4: T2 per-user kind tables (user_kinds + user_kind_attributes).
	if err := migrate.UpUserKinds(ctx, pool); err != nil {
		slog.Error("migrate user-kinds", "error", err)
		os.Exit(1)
	}
	// G1 (genre·kind·attribute tiering, 2026-06-19): additive new schema — genre
	// tier, kind↔genre links, per-(kind,genre) attributes, book tier, entity genre
	// override. Old genre_tags[]/genre_groups/system_kind_attributes drop later (G4)
	// as their consumers retarget. Spec docs/specs/2026-06-19-genre-kind-attribute-tiering.md.
	if err := migrate.UpGenreKindAttr(ctx, pool); err != nil {
		slog.Error("migrate genre-kind-attr", "error", err)
		os.Exit(1)
	}
	// Seed the system standards into the tiered tables (genres + kind↔genre links +
	// attributes under universal), derived from the seeded system kinds. After Seed.
	if err := migrate.SeedGenreKindAttr(ctx, pool); err != nil {
		slog.Error("seed genre-kind-attr", "error", err)
		os.Exit(1)
	}
	// G4 (genre·kind·attribute tiering, 2026-06-19): destructive cutover — repoints
	// glossary_entities.kind_id → book_kinds and entity_attribute_values.attr_def_id →
	// book_attributes, rewrites recalculate_entity_snapshot to the book tier. MUST run
	// AFTER UpGenreKindAttr (FK targets) + SeedGenreKindAttr. Books must be adopted
	// before entities can be created in them. Gated (execGuarded), idempotent.
	if err := migrate.UpGlossaryCutoverG4(ctx, pool); err != nil {
		slog.Error("migrate glossary-cutover-g4", "error", err)
		os.Exit(1)
	}
	// G4 (cont.): merge_candidates.kind_id follows the entity layer onto the book tier
	// (FK system_kinds -> book_kinds). MUST run AFTER the cutover (book_kinds present).
	if err := migrate.UpMergeCandidatesG4(ctx, pool); err != nil {
		slog.Error("migrate merge-candidates-g4", "error", err)
		os.Exit(1)
	}
	// G4 (cont.): restore the cache+search-aware recalculate_entity_snapshot on the book
	// tier (the cutover wrote the base body, dropping cached_name/aliases/search_vector
	// maintenance). MUST run AFTER the cutover (and after UpKnowledgeMemory).
	if err := migrate.UpGlossaryCutoverG4Cache(ctx, pool); err != nil {
		slog.Error("migrate glossary-cutover-g4-cache", "error", err)
		os.Exit(1)
	}
	// G4e (genre·kind·attribute tiering, 2026-06-19): IRREVERSIBLE destructive drop of
	// the retired legacy objects — genre_groups, system_kind_attributes, and the
	// genre_tags TEXT[] columns (system_kinds/user_kinds). MUST run LAST — after every
	// reader/writer retarget (G4d) + the cutover + the cache rewrite (so the snapshot
	// fn no longer joins system_kind_attributes). Idempotent (DROP/ALTER … IF EXISTS).
	if err := migrate.UpGlossaryDropLegacyG4(ctx, pool); err != nil {
		slog.Error("migrate glossary-drop-legacy-g4", "error", err)
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
