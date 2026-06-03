// services/publisher/cmd/publisher — L2.D outbox publisher entry point.
//
// Live wiring (DEFERRED 054 / D-PUBLISHER-LIVE-WIRING):
//  1. Load the active realities from the meta `reality_registry`.
//  2. Open a pgx pool per reality (DSN resolved via the shard-host→DSN
//     resolver) + a meta pool for heartbeats.
//  3. Connect Redis; build the pgx Source + redis Emitter/StreamEmitter.
//  4. Run two tickers: the poll loop (drain outbox → XADD → mark) and the
//     heartbeat (upsert publisher_heartbeats).
//  5. Serve /healthz + /readyz + /metrics; shut down gracefully on signal.
//
// V1 is single-replica per shard (Q-L2D-1) with a no-op leader (Q-L2-5) and
// drains EVERY active reality. The reality set is loaded once at startup;
// adding realities requires a restart (V1 simplification — tracked).
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

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/realityreg"
	"github.com/loreweave/foundation/services/publisher/pkg/heartbeat"
	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/metahb"
	"github.com/loreweave/foundation/services/publisher/pkg/pgsource"
	"github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/redisemit"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/xreality_fanout"
)

func main() {
	if err := run(); err != nil {
		slog.Error("[publisher] fatal", "error", err)
		os.Exit(1)
	}
}

func run() error {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := loadConfig()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// ── Meta DB pool (reality_registry + publisher_heartbeats) ───────────
	metaPool, err := openPool(ctx, cfg.MetaDBURL)
	if err != nil {
		return fmt.Errorf("meta db: %w", err)
	}
	defer metaPool.Close()

	// ── Resolve the active realities + open a pool per reality ───────────
	realities, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		return fmt.Errorf("load realities: %w", err)
	}
	realityPools := map[string]*pgxpool.Pool{}
	var realityIDs []string
	var skipped int
	for _, r := range realities {
		dsn, derr := cfg.DSN.DSN(r.DBHost, r.DBName)
		if derr != nil {
			// A malformed registry row (bad db_name/host) shouldn't stop the
			// whole publisher — skip it like Run isolates a bad reality.
			slog.Error("[publisher] skip reality: bad DSN", "reality", r.ID, "host", r.DBHost, "error", derr)
			skipped++
			continue
		}
		pool, perr := openPool(ctx, dsn)
		if perr != nil {
			// A single reality DB being unreachable at startup must NOT prevent
			// draining the healthy ones (mirrors poll_loop's per-reality
			// isolation). Skip + log; the operator restarts to re-pick it up.
			slog.Error("[publisher] skip reality: pool open failed", "reality", r.ID, "host", r.DBHost, "error", perr)
			skipped++
			continue
		}
		defer pool.Close()
		realityPools[r.ID] = pool
		realityIDs = append(realityIDs, r.ID)
	}
	slog.Info("[publisher] loaded realities", "drained", len(realityIDs), "skipped", skipped, "total", len(realities))

	// ── Redis ────────────────────────────────────────────────────────────
	redisOpts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return fmt.Errorf("redis url: %w", err)
	}
	rdb := redis.NewClient(redisOpts)
	defer rdb.Close()
	if err := rdb.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("redis ping: %w", err)
	}
	slog.Info("[publisher] redis connected")

	// ── Build the loop ────────────────────────────────────────────────────
	policy := retry.DefaultPolicy()
	source, err := pgsource.New(realityPools, policy)
	if err != nil {
		return fmt.Errorf("pgsource: %w", err)
	}
	fanout, err := xreality_fanout.New(redisemit.NewStreamEmitter(rdb, cfg.StreamMaxLen))
	if err != nil {
		return fmt.Errorf("fanout: %w", err)
	}
	hbWriter, err := metahb.New(metaPool)
	if err != nil {
		return fmt.Errorf("heartbeat writer: %w", err)
	}
	hb, err := heartbeat.New(cfg.PublisherID, cfg.ShardHost, hbWriter, heartbeat.RealClock{})
	if err != nil {
		return fmt.Errorf("heartbeat: %w", err)
	}
	loop, err := poll_loop.New(poll_loop.Config{
		Leader:    leader_election.NewNoOp(),
		Source:    source,
		Emitter:   redisemit.NewEmitter(rdb, cfg.StreamMaxLen),
		Fanout:    fanout,
		Mode:      hb, // heartbeat owns the ServiceMode (L1.J degraded gating)
		Policy:    policy,
		BatchSize: cfg.BatchSize,
		Realities: realityIDs,
	})
	if err != nil {
		return fmt.Errorf("poll loop: %w", err)
	}

	m := newMetrics()
	reg := prometheus.NewRegistry()
	reg.MustRegister(m.collectors()...)

	// ── HTTP (health + metrics) ───────────────────────────────────────────
	var ready atomicBool
	ready.set(true)
	httpSrv := newHTTPServer(cfg.HTTPAddr, &ready, reg)
	go func() {
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("[publisher] http server", "error", err)
		}
	}()

	// ── Tickers ───────────────────────────────────────────────────────────
	// Poll + heartbeat run on ONE goroutine (two tickers, single select). The
	// heartbeat.Loop is pull-style by design (its ServiceMode + failureCount
	// are unsynchronized) and poll_loop reads that mode via hb.Mode() every
	// iteration — fanning them onto separate goroutines would be a data race.
	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); runLoops(ctx, loop, hb, m, cfg.PollInterval, cfg.HeartbeatInterval) }()

	slog.Info("[publisher] started",
		"publisher_id", cfg.PublisherID, "shard_host", cfg.ShardHost,
		"realities", len(realityIDs), "poll_interval", cfg.PollInterval.String())

	<-ctx.Done()
	slog.Info("[publisher] shutdown signal — draining")
	ready.set(false)

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	wg.Wait()
	slog.Info("[publisher] stopped")
	return nil
}

// runLoops drives BOTH the drain poll and the heartbeat from a single
// goroutine (two tickers, one select) so the heartbeat.Loop's unsynchronized
// ServiceMode/failureCount are only ever touched by this one goroutine.
func runLoops(ctx context.Context, loop *poll_loop.Loop, hb *heartbeat.Loop, m *metrics, pollInterval, hbInterval time.Duration) {
	poll := time.NewTicker(pollInterval)
	defer poll.Stop()
	beat := time.NewTicker(hbInterval)
	defer beat.Stop()

	// Write one heartbeat immediately so liveness is visible before tick #1.
	doHeartbeat(ctx, hb, m)
	for {
		select {
		case <-ctx.Done():
			return
		case <-poll.C:
			doPoll(ctx, loop, m)
		case <-beat.C:
			doHeartbeat(ctx, hb, m)
		}
	}
}

func doPoll(ctx context.Context, loop *poll_loop.Loop, m *metrics) {
	stats, err := loop.Run(ctx)
	// Per-reality drains are isolated: stats still reflect the realities that
	// succeeded even when err is non-nil (one reality's DB was down).
	m.published.Add(float64(stats.Published))
	m.retried.Add(float64(stats.Retried))
	m.deadLettered.Add(float64(stats.DeadLettered))
	m.fanout.WithLabelValues("ok").Add(float64(stats.FanoutOK))
	m.fanout.WithLabelValues("error").Add(float64(stats.FanoutErr))
	m.realityErrors.Add(float64(stats.RealityErrors))
	if err != nil {
		m.iterationErrors.Inc()
		slog.Error("[publisher] poll iteration", "error", err, "reality_errors", stats.RealityErrors)
	}
}

func doHeartbeat(ctx context.Context, hb *heartbeat.Loop, m *metrics) {
	if err := hb.Tick(ctx); err != nil {
		m.heartbeatFailures.Inc()
		slog.Warn("[publisher] heartbeat write failed", "error", err, "consecutive", hb.FailureCount())
	}
}

// openPool opens a tuned pgx pool from a DSN.
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

// ── Config ────────────────────────────────────────────────────────────────

type config struct {
	PublisherID       string
	ShardHost         string
	MetaDBURL         string
	RedisURL          string
	DSN               realityreg.DSNConfig
	PollInterval      time.Duration
	HeartbeatInterval time.Duration
	BatchSize         int
	StreamMaxLen      int64
	HTTPAddr          string
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

	c.PublisherID = req("PUBLISHER_ID")
	c.ShardHost = req("SHARD_HOST")
	c.MetaDBURL = req("META_DB_URL")
	c.RedisURL = req("REDIS_URL")

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
	c.DSN = realityreg.DSNConfig{
		User:         dsnUser,
		Password:     dsnPass,
		Port:         port,
		SSLMode:      sslmode,
		HostOverride: override,
	}

	c.PollInterval = durationEnv("POLL_INTERVAL", time.Second)
	c.HeartbeatInterval = durationEnv("HEARTBEAT_INTERVAL", 10*time.Second)
	c.BatchSize = intEnv("BATCH_SIZE", 100)
	c.StreamMaxLen = int64(intEnv("STREAM_MAXLEN", 0))
	c.HTTPAddr = os.Getenv("PUBLISHER_HTTP_ADDR")
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

func intEnv(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

// ── Metrics ───────────────────────────────────────────────────────────────

type metrics struct {
	published         prometheus.Counter
	retried           prometheus.Counter
	deadLettered      prometheus.Counter
	fanout            *prometheus.CounterVec
	realityErrors     prometheus.Counter
	iterationErrors   prometheus.Counter
	heartbeatFailures prometheus.Counter
}

func newMetrics() *metrics {
	return &metrics{
		published:         prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_publisher_published_total", Help: "Outbox rows XADDed + marked published."}),
		retried:           prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_publisher_retried_total", Help: "Outbox rows marked for retry after a transient XADD failure."}),
		deadLettered:      prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_publisher_dead_lettered_total", Help: "Outbox rows dead-lettered at max attempts."}),
		fanout:            prometheus.NewCounterVec(prometheus.CounterOpts{Name: "lw_publisher_fanout_total", Help: "xreality fanout XADDs by result."}, []string{"result"}),
		realityErrors:     prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_publisher_reality_errors_total", Help: "Per-reality drain transactions that failed (infra error)."}),
		iterationErrors:   prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_publisher_iteration_errors_total", Help: "Poll-loop iterations that returned an error."}),
		heartbeatFailures: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_publisher_heartbeat_failures_total", Help: "Heartbeat upsert failures."}),
	}
}

func (m *metrics) collectors() []prometheus.Collector {
	return []prometheus.Collector{
		m.published, m.retried, m.deadLettered, m.fanout, m.realityErrors, m.iterationErrors, m.heartbeatFailures,
	}
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

// atomicBool is a tiny lock-guarded bool for the readiness flag.
type atomicBool struct {
	mu sync.RWMutex
	v  bool
}

func (a *atomicBool) set(v bool) { a.mu.Lock(); a.v = v; a.mu.Unlock() }
func (a *atomicBool) get() bool  { a.mu.RLock(); defer a.mu.RUnlock(); return a.v }
