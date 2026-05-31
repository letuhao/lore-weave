// services/meta-worker/cmd/meta-worker — L2.L sole xreality consumer.
//
// Live wiring (DEFERRED 069, meta-worker canon path):
//  1. Load active realities from meta reality_registry → per-reality pgx pools
//     (canon_projection subscriber DBs) + a meta pool (subscribers + audit).
//  2. Connect Redis; create the consumer group on the canon stream.
//  3. Register canon_writer.Handle for the 4 canon.entry.* event types,
//     bound to pgx adapters (canon_projection upsert / subscribers / audit).
//  4. Loop consumer.ProcessOne (XREADGROUP → dispatch → ACK).
//  5. Serve /healthz + /readyz + /metrics; shut down gracefully on signal.
//
// I7: the ONLY ingress is the xreality.* stream; the dispatcher allowlist
// keeps the routing keys (canon.entry.*) inner-named but xreality-fed.
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
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
	"github.com/loreweave/foundation/services/meta-worker/pkg/canon_writer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/consumer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
	"github.com/loreweave/foundation/services/meta-worker/pkg/pgwrite"
	"github.com/loreweave/foundation/services/meta-worker/pkg/redisconsume"
	"github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer/pglive"
	"github.com/loreweave/foundation/services/publisher/pkg/realityreg"
)

func main() {
	if err := run(); err != nil {
		slog.Error("[meta-worker] fatal", "error", err)
		os.Exit(1)
	}
}

// sysClock / randUUID are the production Clock/UUIDGen for the meta-scrub
// MetaWrite path (P2/071).
type sysClock struct{}

func (sysClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type randUUID struct{}

func (randUUID) New() uuid.UUID { return uuid.New() }

func run() error {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	cfg, err := loadConfig()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// ── Meta DB pool (reality_registry + book_reality_subscription + audit) ──
	metaPool, err := openPool(ctx, cfg.MetaDBURL)
	if err != nil {
		return fmt.Errorf("meta db: %w", err)
	}
	defer metaPool.Close()

	// ── Per-reality pools (canon_projection subscriber DBs) ──────────────────
	realities, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		return fmt.Errorf("load realities: %w", err)
	}
	realityPools := map[string]*pgxpool.Pool{}
	var skipped int
	for _, r := range realities {
		dsn, derr := cfg.DSN.DSN(r.DBHost, r.DBName)
		if derr != nil {
			slog.Error("[meta-worker] skip reality: bad DSN", "reality", r.ID, "error", derr)
			skipped++
			continue
		}
		pool, perr := openPool(ctx, dsn)
		if perr != nil {
			slog.Error("[meta-worker] skip reality: pool open failed", "reality", r.ID, "error", perr)
			skipped++
			continue
		}
		defer pool.Close()
		realityPools[r.ID] = pool
	}
	slog.Info("[meta-worker] reality pools", "open", len(realityPools), "skipped", skipped)

	// ── Redis + consumer group ───────────────────────────────────────────────
	redisOpts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		return fmt.Errorf("redis url: %w", err)
	}
	rdb := redis.NewClient(redisOpts)
	defer rdb.Close()
	if err := rdb.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("redis ping: %w", err)
	}
	source, err := redisconsume.New(redisconsume.Config{
		RDB:      rdb,
		Streams:  []string{cfg.CanonStream, cfg.UserErasedStream},
		Group:    cfg.ConsumerGroup,
		Consumer: cfg.ConsumerID,
		Block:    cfg.Block,
	})
	if err != nil {
		return fmt.Errorf("redis source: %w", err)
	}
	if err := source.EnsureGroups(ctx); err != nil {
		return fmt.Errorf("ensure groups: %w", err)
	}

	// ── Dispatcher: canon_writer bound to pgx adapters ───────────────────────
	cw, err := canon_writer.New(canon_writer.Config{
		Subscribers: pgwrite.NewSubscribers(metaPool),
		DB:          pgwrite.NewCanonDB(realityPools),
		Audit:       pgwrite.NewAudit(metaPool),
	})
	if err != nil {
		return fmt.Errorf("canon_writer: %w", err)
	}
	d := dispatch.New()
	for _, et := range canon_writer.EventTypes() {
		d.Register(et, cw.Handle)
	}

	// ── user-erased cascade (P2/071): xreality.user.erased → scrub PII ──────────
	// Per-reality pc_projection scrub (always) + meta player_character_index.pc_name
	// scrub via MetaWrite (only when META_ALLOWLIST_PATH is set → graceful degrade:
	// the canon path + the per-reality scrub work without it; the meta-index scrub
	// needs the allowlist/MetaWrite Config).
	uerCfg := user_erased_writer.Config{
		Lookup: pglive.NewPgUserRealityLookup(metaPool),
		DB: pglive.NewPgPerRealityScrubber(func(rid uuid.UUID) (*pgxpool.Pool, error) {
			p, ok := realityPools[rid.String()]
			if !ok {
				return nil, fmt.Errorf("no pool for reality %s", rid)
			}
			return p, nil
		}),
		Audit: pglive.LogAuditSink{},
	}
	if allowPath := os.Getenv("META_ALLOWLIST_PATH"); allowPath != "" {
		allow, aerr := meta.LoadAllowlist(allowPath)
		if aerr != nil {
			return fmt.Errorf("load allowlist: %w", aerr)
		}
		mwCfg := &meta.Config{
			DB: metapg.New(metaPool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
			Clock: sysClock{}, UUIDGen: randUUID{},
		}
		uerCfg.MetaScrubber = pglive.NewPgMetaScrubber(metaPool, mwCfg, "meta-worker")
	} else {
		slog.Warn("[meta-worker] META_ALLOWLIST_PATH unset — user.erased per-reality scrub wired, but the meta player_character_index.pc_name scrub is DISABLED (set it to complete erasure)")
	}
	uer, uerr := user_erased_writer.New(uerCfg)
	if uerr != nil {
		return fmt.Errorf("user_erased_writer: %w", uerr)
	}
	for _, et := range user_erased_writer.EventTypes() {
		d.Register(et, uer.Handle)
	}

	if err := d.ValidateAllowlist(); err != nil {
		return fmt.Errorf("I7 allowlist: %w", err)
	}
	cons, err := consumer.New(source, d)
	if err != nil {
		return fmt.Errorf("consumer: %w", err)
	}

	m := newMetrics()
	reg := prometheus.NewRegistry()
	reg.MustRegister(m.collectors()...)

	var ready atomicBool
	ready.set(true)
	httpSrv := newHTTPServer(cfg.HTTPAddr, &ready, reg)
	go func() {
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("[meta-worker] http server", "error", err)
		}
	}()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); runConsumer(ctx, cons, m, cfg.BatchSize) }()

	slog.Info("[meta-worker] started",
		"canon_stream", cfg.CanonStream, "group", cfg.ConsumerGroup, "consumer", cfg.ConsumerID,
		"handlers", len(d.Registered()))

	<-ctx.Done()
	slog.Info("[meta-worker] shutdown signal")
	ready.set(false)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	wg.Wait()
	slog.Info("[meta-worker] stopped")
	return nil
}

// runConsumer loops ProcessOne until ctx is cancelled.
func runConsumer(ctx context.Context, cons *consumer.Consumer, m *metrics, batchSize int) {
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		stats, err := cons.ProcessOne(ctx, batchSize)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			m.readErrors.Inc()
			slog.Error("[meta-worker] process", "error", err)
			// Back off briefly so a persistent Redis error doesn't hot-loop.
			select {
			case <-ctx.Done():
				return
			case <-time.After(time.Second):
			}
			continue
		}
		m.read.Add(float64(stats.Read))
		m.dispatched.Add(float64(stats.Dispatched))
		m.acked.Add(float64(stats.Acked))
		m.noHandler.Add(float64(stats.NoHandler))
		m.handlerErr.Add(float64(stats.HandlerErr))
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

// ── Config ────────────────────────────────────────────────────────────────

type config struct {
	MetaDBURL        string
	RedisURL         string
	DSN              realityreg.DSNConfig
	CanonStream      string
	UserErasedStream string
	ConsumerGroup    string
	ConsumerID       string
	Block            time.Duration
	BatchSize        int
	HTTPAddr         string
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

	c.CanonStream = os.Getenv("CANON_STREAM")
	if c.CanonStream == "" {
		c.CanonStream = "xreality.book.canon.updated"
	}
	c.UserErasedStream = os.Getenv("USER_ERASED_STREAM")
	if c.UserErasedStream == "" {
		c.UserErasedStream = "xreality.user.erased"
	}
	c.ConsumerGroup = os.Getenv("CONSUMER_GROUP")
	if c.ConsumerGroup == "" {
		c.ConsumerGroup = "meta-worker"
	}
	c.ConsumerID = os.Getenv("CONSUMER_ID")
	if c.ConsumerID == "" {
		host, _ := os.Hostname()
		if host == "" {
			host = "meta-worker-1"
		}
		c.ConsumerID = host
	}
	c.Block = durationEnv("CONSUMER_BLOCK", 2*time.Second)
	c.BatchSize = intEnv("BATCH_SIZE", 100)
	c.HTTPAddr = os.Getenv("METAWORKER_HTTP_ADDR")
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
	read       prometheus.Counter
	dispatched prometheus.Counter
	acked      prometheus.Counter
	noHandler  prometheus.Counter
	handlerErr prometheus.Counter
	readErrors prometheus.Counter
}

func newMetrics() *metrics {
	return &metrics{
		read:       prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_worker_read_total", Help: "xreality messages read."}),
		dispatched: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_worker_dispatched_total", Help: "messages dispatched + acked."}),
		acked:      prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_worker_acked_total", Help: "messages XACKed."}),
		noHandler:  prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_worker_no_handler_total", Help: "messages with no registered handler (I7 allowlist)."}),
		handlerErr: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_worker_handler_errors_total", Help: "handler errors (NACK / redelivery)."}),
		readErrors: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_meta_worker_read_errors_total", Help: "XREADGROUP errors."}),
	}
}

func (m *metrics) collectors() []prometheus.Collector {
	return []prometheus.Collector{m.read, m.dispatched, m.acked, m.noHandler, m.handlerErr, m.readErrors}
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
