// services/retention-worker/cmd/retention-worker — L2.K retention worker.
//
// Live wiring (DEFERRED 058):
//  1. Load active realities from meta reality_registry → per-reality pgx pools
//     (for the outbox prune) + a reality_id → DSN map (for the audit script).
//  2. Build ONE retention_loop.Loop: pgx outbox Deleter + os/exec audit
//     ScriptRunner (wraps scripts/event-audit-retention-cron.sh) + DSN lookup.
//  3. Tick hourly: for each reality, prune events_outbox + run audit retention.
//  4. Serve /healthz + /readyz + /metrics; shut down gracefully on signal.
//
// INVARIANT: NEVER touches the `events` table (archive-worker's surface, Q-L2K-1).
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/contracts/realityreg"
	"github.com/loreweave/foundation/services/retention-worker/pkg/audit_invoker"
	"github.com/loreweave/foundation/services/retention-worker/pkg/outbox_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/pgio"
	"github.com/loreweave/foundation/services/retention-worker/pkg/retention_loop"
	"github.com/loreweave/foundation/services/retention-worker/pkg/scriptrun"
	"github.com/loreweave/foundation/services/retention-worker/pkg/snapshot_pruner"
	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

func main() {
	if err := run(); err != nil {
		slog.Error("[retention-worker] fatal", "error", err)
		os.Exit(1)
	}
}

func run() error {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	cfg, err := loadConfig()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	metaPool, err := openPool(ctx, cfg.MetaDBURL)
	if err != nil {
		return fmt.Errorf("meta db: %w", err)
	}
	defer metaPool.Close()

	realities, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		return fmt.Errorf("load realities: %w", err)
	}
	pools := map[string]*pgxpool.Pool{}
	dsnMap := map[uuid.UUID]string{}
	var ids []uuid.UUID
	var skipped int
	for _, r := range realities {
		rid, perr := uuid.Parse(r.ID)
		if perr != nil {
			skipped++
			continue
		}
		dsn, derr := cfg.DSN.DSN(r.DBHost, r.DBName)
		if derr != nil {
			slog.Error("[retention-worker] skip reality: bad DSN", "reality", r.ID, "error", derr)
			skipped++
			continue
		}
		pool, poolErr := openPool(ctx, dsn)
		if poolErr != nil {
			slog.Error("[retention-worker] skip reality: pool open failed", "reality", r.ID, "error", poolErr)
			skipped++
			continue
		}
		defer pool.Close()
		pools[r.ID] = pool
		dsnMap[rid] = dsn
		ids = append(ids, rid)
	}
	slog.Info("[retention-worker] realities", "open", len(ids), "skipped", skipped)

	loop, err := buildLoop(pools, dsnMap, cfg)
	if err != nil {
		return fmt.Errorf("build loop: %w", err)
	}

	m := newMetrics()
	reg := prometheus.NewRegistry()
	reg.MustRegister(m.collectors()...)

	var ready atomicBool
	ready.set(true)
	httpSrv := newHTTPServer(cfg.HTTPAddr, &ready, reg)
	go func() {
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("[retention-worker] http server", "error", err)
		}
	}()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); runRetention(ctx, loop, ids, m, cfg.Interval) }()

	slog.Info("[retention-worker] started", "realities", len(ids), "interval", cfg.Interval.String())

	<-ctx.Done()
	slog.Info("[retention-worker] shutdown signal")
	ready.set(false)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	wg.Wait()
	slog.Info("[retention-worker] stopped")
	return nil
}

func buildLoop(pools map[string]*pgxpool.Pool, dsnMap map[uuid.UUID]string, cfg config) (*retention_loop.Loop, error) {
	op, err := outbox_pruner.New(outbox_pruner.Config{
		Deleter: pgio.NewDeleter(pools),
		Clock:   outbox_pruner.RealClock{},
		Cfg:     cfg.Retention,
	})
	if err != nil {
		return nil, err
	}
	ai, err := audit_invoker.New(scriptrun.New(cfg.AuditScript), cfg.Retention)
	if err != nil {
		return nil, err
	}
	return retention_loop.New(retention_loop.Config{
		OutboxPruner:   op,
		AuditInvoker:   ai,
		SnapshotPruner: snapshot_pruner.New(),
		DSNLookup:      &retention_loop.MapDSNLookup{M: dsnMap},
		Mode:           staticMode{},
	})
}

// runRetention ticks every reality's retention loop.
func runRetention(ctx context.Context, loop *retention_loop.Loop, ids []uuid.UUID, m *metrics, interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	tick := func() {
		for _, rid := range ids {
			stats, err := loop.Run(ctx, rid)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				m.errors.Inc()
				slog.Error("[retention-worker] retention iteration", "reality", rid, "error", err)
				continue
			}
			m.outboxDeleted.Add(float64(stats.Outbox.Deleted))
			m.auditNonFlagged.Add(float64(stats.Audit.NonFlaggedDeleted))
			m.auditFlagged.Add(float64(stats.Audit.FlaggedDeleted))
			m.auditPartitions.Add(float64(stats.Audit.PartitionsDropped))
		}
	}
	tick()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			tick()
		}
	}
}

func openPool(ctx context.Context, dsn string) (*pgxpool.Pool, error) {
	poolCfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("parse dsn: %w", err)
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
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping: %w", err)
	}
	return pool, nil
}

// staticMode always reports ModeFull (V1 — degraded gating not wired here).
type staticMode struct{}

func (staticMode) Mode() lifecycle.ServiceMode { return lifecycle.ModeFull }

// ── Config ────────────────────────────────────────────────────────────────

type config struct {
	MetaDBURL   string
	DSN         realityreg.DSNConfig
	AuditScript string
	Retention   types.RetentionConfig
	Interval    time.Duration
	HTTPAddr    string
}

func loadConfig() (config, error) {
	var c config
	var missing []string
	req := func(key string) string {
		v := os.Getenv(key)
		if v == "" {
			missing = append(missing, key)
		}
		return v
	}

	c.MetaDBURL = req("META_DB_URL")
	dsnUser := req("SHARD_DB_USER")
	dsnPass := req("SHARD_DB_PASSWORD")
	if len(missing) > 0 {
		return c, fmt.Errorf("missing required env: %v", missing)
	}

	override, err := realityreg.ParseHostOverride(os.Getenv("PUBLISHER_SHARD_HOST_OVERRIDE"))
	if err != nil {
		return c, err
	}
	port := 5432
	if v := os.Getenv("SHARD_DB_PORT"); v != "" {
		if p, perr := strconv.Atoi(v); perr == nil {
			port = p
		} else {
			return c, fmt.Errorf("SHARD_DB_PORT: %w", perr)
		}
	}
	sslmode := os.Getenv("SHARD_DB_SSLMODE")
	if sslmode == "" {
		sslmode = "require"
	}
	c.DSN = realityreg.DSNConfig{User: dsnUser, Password: dsnPass, Port: port, SSLMode: sslmode, HostOverride: override}

	c.AuditScript = os.Getenv("RETENTION_AUDIT_SCRIPT")
	if c.AuditScript == "" {
		c.AuditScript = "scripts/event-audit-retention-cron.sh"
	}
	c.Retention = types.DefaultConfig()
	c.Interval = durationEnv("RETENTION_INTERVAL", time.Hour)
	c.HTTPAddr = os.Getenv("RETENTION_HTTP_ADDR")
	if c.HTTPAddr == "" {
		c.HTTPAddr = ":8080"
	}
	return c, nil
}

func durationEnv(key string, def time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
	}
	return def
}

// ── Metrics ───────────────────────────────────────────────────────────────

type metrics struct {
	outboxDeleted   prometheus.Counter
	auditNonFlagged prometheus.Counter
	auditFlagged    prometheus.Counter
	auditPartitions prometheus.Counter
	errors          prometheus.Counter
}

func newMetrics() *metrics {
	return &metrics{
		outboxDeleted:   prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_retention_outbox_deleted_total", Help: "events_outbox rows pruned."}),
		auditNonFlagged: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_retention_audit_nonflagged_deleted_total", Help: "non-flagged event_audit rows pruned."}),
		auditFlagged:    prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_retention_audit_flagged_deleted_total", Help: "flagged event_audit rows pruned."}),
		auditPartitions: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_retention_audit_partitions_dropped_total", Help: "fully-expired event_audit partitions dropped."}),
		errors:          prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_retention_errors_total", Help: "retention iteration errors."}),
	}
}

func (m *metrics) collectors() []prometheus.Collector {
	return []prometheus.Collector{m.outboxDeleted, m.auditNonFlagged, m.auditFlagged, m.auditPartitions, m.errors}
}

// ── HTTP ──────────────────────────────────────────────────────────────────

func newHTTPServer(addr string, ready *atomicBool, reg *prometheus.Registry) *http.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) {
		if ready.get() {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte("ready"))
			return
		}
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte("draining"))
	})
	mux.Handle("/metrics", promhttp.HandlerFor(reg, promhttp.HandlerOpts{}))
	return &http.Server{Addr: addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
}

type atomicBool struct {
	mu sync.RWMutex
	v  bool
}

func (a *atomicBool) set(v bool) { a.mu.Lock(); a.v = v; a.mu.Unlock() }
func (a *atomicBool) get() bool  { a.mu.RLock(); defer a.mu.RUnlock(); return a.v }
