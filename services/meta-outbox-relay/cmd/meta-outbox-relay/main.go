// meta-outbox-relay — P2/101 slice B: drains the meta DB's meta_outbox table
// (written by MetaWrite's sdks/go/metaoutbox appender) to Redis Streams.
//
// Live wiring:
//  1. Open a pgx pool to the meta DB + connect Redis.
//  2. Build the pgx Source + redis Emitter + drain.Loop (shared publisher retry).
//  3. Run a ticker (drain meta_outbox → XADD lw.meta.events + xreality bridge → mark).
//  4. Serve /healthz + /readyz + /metrics; shut down gracefully on signal.
//
// V1 is single-replica (no leader election); the FOR UPDATE SKIP LOCKED batch
// SELECT keeps it correct at V2+ multi-replica (no duplicate XADD).
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

	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/drain"
	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/pgsource"
	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/redisemit"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

func main() {
	if err := run(); err != nil {
		slog.Error("[meta-outbox-relay] fatal", "error", err)
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

	pool, err := pgxpool.New(ctx, cfg.MetaDBURL)
	if err != nil {
		return fmt.Errorf("meta db: %w", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("meta db ping: %w", err)
	}

	redisOpts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return fmt.Errorf("redis url: %w", err)
	}
	rdb := redis.NewClient(redisOpts)
	defer rdb.Close()
	if err := rdb.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("redis ping: %w", err)
	}

	policy := retry.DefaultPolicy()
	source, err := pgsource.New(pool, policy)
	if err != nil {
		return fmt.Errorf("pgsource: %w", err)
	}
	emitter, err := redisemit.New(rdb, cfg.HomeStream, cfg.StreamMaxLen)
	if err != nil {
		return fmt.Errorf("emitter: %w", err)
	}
	loop, err := drain.New(drain.Config{Source: source, Emitter: emitter, Policy: policy, BatchSize: cfg.BatchSize})
	if err != nil {
		return fmt.Errorf("drain loop: %w", err)
	}

	m := newMetrics()
	reg := prometheus.NewRegistry()
	reg.MustRegister(m.collectors()...)

	var ready atomicBool
	ready.set(true)
	httpSrv := newHTTPServer(cfg.HTTPAddr, &ready, reg)
	go func() {
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("[meta-outbox-relay] http server", "error", err)
		}
	}()

	// Pending-depth gauge source (/review-impl #3): a cheap COUNT over the
	// partial pending index, so SRE can see drain lag (relay down ⇒ rows pile up).
	countPending := func(ctx context.Context) (int64, error) {
		var n int64
		err := pool.QueryRow(ctx,
			`SELECT count(*) FROM meta_outbox WHERE published = FALSE AND dead_lettered_at IS NULL`).Scan(&n)
		return n, err
	}

	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); runLoop(ctx, loop, m, countPending, cfg.PollInterval) }()

	slog.Info("[meta-outbox-relay] started",
		"home_stream", cfg.HomeStream, "poll_interval", cfg.PollInterval.String(), "batch_size", cfg.BatchSize)

	<-ctx.Done()
	slog.Info("[meta-outbox-relay] shutdown signal — draining")
	ready.set(false)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	wg.Wait()
	slog.Info("[meta-outbox-relay] stopped")
	return nil
}

func runLoop(ctx context.Context, loop *drain.Loop, m *metrics, countPending func(context.Context) (int64, error), interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			stats, err := loop.Run(ctx)
			m.published.Add(float64(stats.Published))
			m.retried.Add(float64(stats.Retried))
			m.deadLettered.Add(float64(stats.DeadLettered))
			m.xreality.Add(float64(stats.XRealityOK))
			if err != nil {
				m.iterationErrors.Inc()
				slog.Error("[meta-outbox-relay] drain iteration", "error", err)
			}
			// Update the drain-lag gauge (best-effort; a count failure is logged
			// but never stops the loop).
			if n, cerr := countPending(ctx); cerr == nil {
				m.pending.Set(float64(n))
			} else {
				slog.Warn("[meta-outbox-relay] pending-depth count failed", "error", cerr)
			}
		}
	}
}

// ── Config ──────────────────────────────────────────────────────────────────

type config struct {
	MetaDBURL    string
	RedisURL     string
	HomeStream   string
	PollInterval time.Duration
	BatchSize    int
	StreamMaxLen int64
	HTTPAddr     string
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
	c.RedisURL = req("REDIS_URL")
	if len(missing) > 0 {
		return c, fmt.Errorf("missing required env: %v", missing)
	}
	c.HomeStream = os.Getenv("META_EVENTS_STREAM")
	if c.HomeStream == "" {
		c.HomeStream = "lw.meta.events"
	}
	c.PollInterval = durationEnv("POLL_INTERVAL", time.Second)
	c.BatchSize = intEnv("BATCH_SIZE", 100)
	c.StreamMaxLen = int64(intEnv("STREAM_MAXLEN", 0))
	c.HTTPAddr = os.Getenv("HTTP_ADDR")
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
	published       prometheus.Counter
	retried         prometheus.Counter
	deadLettered    prometheus.Counter
	xreality        prometheus.Counter
	iterationErrors prometheus.Counter
	pending         prometheus.Gauge
}

func newMetrics() *metrics {
	return &metrics{
		published:       prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_outbox_published_total", Help: "meta_outbox rows XADDed + marked published."}),
		retried:         prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_outbox_retried_total", Help: "meta_outbox rows marked for retry after a transient XADD failure."}),
		deadLettered:    prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_outbox_dead_lettered_total", Help: "meta_outbox rows dead-lettered at max attempts."}),
		xreality:        prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_outbox_xreality_total", Help: "meta_outbox rows ALSO emitted to an xreality.* topic (cross-reality bridge)."}),
		iterationErrors: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_outbox_iteration_errors_total", Help: "drain-loop iterations that returned an error."}),
		pending:         prometheus.NewGauge(prometheus.GaugeOpts{Name: "lw_meta_outbox_pending", Help: "Unpublished, non-dead-lettered meta_outbox rows (drain lag — alert if it grows unbounded, i.e. relay down)."}),
	}
}

func (m *metrics) collectors() []prometheus.Collector {
	return []prometheus.Collector{m.published, m.retried, m.deadLettered, m.xreality, m.iterationErrors, m.pending}
}

// ── HTTP ────────────────────────────────────────────────────────────────────

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
