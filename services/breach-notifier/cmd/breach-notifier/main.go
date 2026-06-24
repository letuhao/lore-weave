// breach-notifier — 106 D-BREACH-DELIVERY-CONSUMER. Consumes the lw.incidents.breach
// Redis stream (produced by incident-bot 108), DELIVERS the GDPR Art.33 DPO notice via
// a pluggable Notifier, and records a durable delivery-confirmed marker. Q-L7-1:
// incident-bot decides+emits; this SEPARATE service delivers.
//
// V1 transport: LogNotifier (a real audit-line delivery) by default; the Slack
// transport is an opt-in scaffold (LW_BREACH_NOTIFIER=slack) whose live round-trip is
// deferred (D-BREACH-SLACK-LIVE). No secrets hardcoded; SLACK_BOT_TOKEN via env only.
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

	"github.com/loreweave/foundation/services/breach-notifier/internal/consume"
	"github.com/loreweave/foundation/services/breach-notifier/internal/deliver"
	"github.com/loreweave/foundation/services/breach-notifier/internal/handler"
	"github.com/loreweave/foundation/services/breach-notifier/internal/migrate"
	"github.com/loreweave/foundation/services/breach-notifier/internal/store"
)

func main() {
	if err := run(); err != nil {
		slog.Error("[breach-notifier] fatal", "error", err)
		os.Exit(1)
	}
}

func run() error {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "breach-notifier"))

	cfg, err := loadConfig()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	pool, err := pgxpool.New(ctx, cfg.DBURL)
	if err != nil {
		return fmt.Errorf("db: %w", err)
	}
	defer pool.Close()
	if err := pool.Ping(ctx); err != nil {
		return fmt.Errorf("db ping: %w", err)
	}
	if err := migrate.Up(ctx, pool); err != nil {
		return err
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

	notifier, err := buildNotifier(cfg)
	if err != nil {
		return err
	}
	hdl, err := handler.New(notifier, store.NewPgDeliveryStore(pool), time.Now, slog.Default())
	if err != nil {
		return err
	}
	source, err := consume.NewRedisSource(consume.Config{
		RDB: rdb, Stream: cfg.Stream, Group: cfg.Group, Consumer: cfg.Consumer, Block: cfg.Block,
	})
	if err != nil {
		return err
	}
	if err := source.EnsureGroup(ctx); err != nil {
		return err
	}
	proc, err := consume.NewProcessor(source, hdl.Handle)
	if err != nil {
		return err
	}

	m := newMetrics()
	reg := prometheus.NewRegistry()
	reg.MustRegister(m.collectors()...)

	var ready atomicBool
	ready.set(true)
	httpSrv := newHTTPServer(cfg.HTTPAddr, &ready, reg)
	go func() {
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("[breach-notifier] http server", "error", err)
		}
	}()

	var wg sync.WaitGroup
	wg.Add(2)
	go func() { defer wg.Done(); runLoop(ctx, proc, m, cfg.BatchSize) }()
	go func() {
		defer wg.Done()
		runReclaim(ctx, proc, m, cfg.ReclaimInterval, cfg.ReclaimMinIdle, cfg.BatchSize)
	}()

	slog.Info("[breach-notifier] started", "stream", cfg.Stream, "group", cfg.Group, "notifier", cfg.NotifierKind)

	<-ctx.Done()
	slog.Info("[breach-notifier] shutdown signal — draining")
	ready.set(false)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	wg.Wait()
	slog.Info("[breach-notifier] stopped")
	return nil
}

// runLoop repeatedly processes one batch; the source's blocking read paces it. A read
// error backs off briefly (unless the context is done). Never exits except on ctx done.
func runLoop(ctx context.Context, proc *consume.Processor, m *metrics, batch int) {
	for {
		if ctx.Err() != nil {
			return
		}
		st, err := proc.ProcessOne(ctx, batch)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			m.iterErrors.Inc()
			slog.Error("[breach-notifier] process iteration", "error", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
			continue
		}
		m.record(st)
	}
}

// runReclaim periodically reclaims this consumer's stale pending entries (crashed
// before ack) so a notice is never stuck un-redelivered (H2). minIdle is generous so
// only genuinely-stuck (not in-flight) entries are reclaimed.
func runReclaim(ctx context.Context, proc *consume.Processor, m *metrics, interval, minIdle time.Duration, batch int) {
	t := time.NewTicker(interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			st, err := proc.ReclaimOnce(ctx, minIdle, batch)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				m.iterErrors.Inc()
				slog.Error("[breach-notifier] reclaim sweep", "error", err)
				continue
			}
			if st.Read > 0 {
				slog.Info("[breach-notifier] reclaimed stale pending entries", "count", st.Read, "delivered", st.Delivered, "skipped_duplicate", st.SkippedDuplicate)
			}
			m.record(st)
		}
	}
}

func buildNotifier(cfg config) (deliver.Notifier, error) {
	if cfg.NotifierKind == "slack" {
		n, err := deliver.NewSlackNotifier(os.Getenv("SLACK_BOT_TOKEN"), os.Getenv("SLACK_COMPLIANCE_CHANNEL"))
		if err != nil {
			return nil, fmt.Errorf("slack notifier: %w", err)
		}
		return n, nil
	}
	return deliver.NewLogNotifier(slog.Default()), nil
}

// ── Config ──────────────────────────────────────────────────────────────────

type config struct {
	RedisURL        string
	DBURL           string
	Stream          string
	Group           string
	Consumer        string
	Block           time.Duration
	BatchSize       int
	HTTPAddr        string
	NotifierKind    string // "log" (default) | "slack"
	ReclaimInterval time.Duration
	ReclaimMinIdle  time.Duration
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
	c.RedisURL = req("REDIS_URL")
	c.DBURL = req("BREACH_NOTIFIER_DB_URL")
	if len(missing) > 0 {
		return c, fmt.Errorf("missing required env: %v", missing)
	}
	c.Stream = envOr("LW_BREACH_STREAM", "lw.incidents.breach")
	c.Group = envOr("CONSUMER_GROUP", "breach-notifier")
	c.Consumer = envOr("CONSUMER_NAME", defaultConsumerName())
	c.Block = durationEnv("READ_BLOCK", 5*time.Second)
	c.BatchSize = intEnv("BATCH_SIZE", 50)
	c.HTTPAddr = envOr("HTTP_ADDR", ":8093")
	c.NotifierKind = envOr("LW_BREACH_NOTIFIER", "log")
	c.ReclaimInterval = durationEnv("RECLAIM_INTERVAL", time.Minute)
	c.ReclaimMinIdle = durationEnv("RECLAIM_MIN_IDLE", 5*time.Minute)
	return c, nil
}

func defaultConsumerName() string {
	if h, err := os.Hostname(); err == nil && h != "" {
		return "breach-notifier-" + h
	}
	return "breach-notifier-1"
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
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
	delivered  prometheus.Counter
	failed     prometheus.Counter
	skippedDup prometheus.Counter
	malformed  prometheus.Counter
	iterErrors prometheus.Counter
}

func newMetrics() *metrics {
	return &metrics{
		delivered:  prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_breach_delivery_delivered_total", Help: "DPO notices delivered + recorded."}),
		failed:     prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_breach_delivery_failed_total", Help: "DPO notice delivery attempts that failed (left pending for redelivery)."}),
		skippedDup: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_breach_delivery_skipped_duplicate_total", Help: "DPO notices skipped because already delivered (idempotency)."}),
		malformed:  prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_breach_delivery_malformed_total", Help: "dpo_notice obligations dropped as malformed (failed contract Validate) — alertable."}),
		iterErrors: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_breach_delivery_iteration_errors_total", Help: "consumer loop iterations that returned an error."}),
	}
}

func (m *metrics) collectors() []prometheus.Collector {
	return []prometheus.Collector{m.delivered, m.failed, m.skippedDup, m.malformed, m.iterErrors}
}

// record folds a batch's stats into the counters (shared by the read loop + reclaim sweep).
func (m *metrics) record(st consume.Stats) {
	m.delivered.Add(float64(st.Delivered))
	m.failed.Add(float64(st.Failed))
	m.skippedDup.Add(float64(st.SkippedDuplicate))
	m.malformed.Add(float64(st.Malformed))
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
