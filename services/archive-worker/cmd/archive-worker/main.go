// services/archive-worker/cmd/archive-worker — L2.J cold-storage archiver.
//
// Live wiring (DEFERRED 056+057):
//  1. Load active realities from meta reality_registry → per-reality pgx pools.
//  2. Connect MinIO; ensure the lw-event-archive bucket.
//  3. Build one archive_loop.Loop per reality (pgx Catalog/RowSource/Dropper/
//     state + shared MinIO store + Parquet+ZSTD encoder).
//  4. Tick: for each reality, archive the oldest eligible partition
//     (Parquet→MinIO→verify→archive_state→DETACH+DROP).
//  5. Serve /healthz + /readyz + /metrics; shut down gracefully on signal.
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
	"github.com/loreweave/foundation/services/archive-worker/pkg/archive_loop"
	"github.com/loreweave/foundation/services/archive-worker/pkg/miniostore"
	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
	"github.com/loreweave/foundation/services/archive-worker/pkg/partition_picker"
	"github.com/loreweave/foundation/services/archive-worker/pkg/pgio"
	"github.com/loreweave/foundation/services/archive-worker/pkg/state"
)

const bucketName = "lw-event-archive"

func main() {
	if err := run(); err != nil {
		slog.Error("[archive-worker] fatal", "error", err)
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

	store, err := miniostore.New(ctx, miniostore.Config{
		Endpoint: cfg.MinioEndpoint, AccessKey: cfg.MinioAccessKey,
		SecretKey: cfg.MinioSecretKey, UseSSL: cfg.MinioUseSSL,
	})
	if err != nil {
		return fmt.Errorf("minio: %w", err)
	}
	if err := store.EnsureBucket(ctx, bucketName); err != nil {
		return fmt.Errorf("ensure bucket: %w", err)
	}

	realities, err := realityreg.ActiveRealities(ctx, metaPool)
	if err != nil {
		return fmt.Errorf("load realities: %w", err)
	}
	loops := map[uuid.UUID]*archive_loop.Loop{}
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
			slog.Error("[archive-worker] skip reality: bad DSN", "reality", r.ID, "error", derr)
			skipped++
			continue
		}
		pool, poolErr := openPool(ctx, dsn)
		if poolErr != nil {
			slog.Error("[archive-worker] skip reality: pool open failed", "reality", r.ID, "error", poolErr)
			skipped++
			continue
		}
		defer pool.Close()
		loop, lerr := buildLoop(pool, store, cfg.Cutoff)
		if lerr != nil {
			return fmt.Errorf("build loop reality=%s: %w", r.ID, lerr)
		}
		loops[rid] = loop
		ids = append(ids, rid)
	}
	slog.Info("[archive-worker] reality loops", "open", len(ids), "skipped", skipped)

	m := newMetrics()
	reg := prometheus.NewRegistry()
	reg.MustRegister(m.collectors()...)

	var ready atomicBool
	ready.set(true)
	httpSrv := newHTTPServer(cfg.HTTPAddr, &ready, reg)
	go func() {
		if err := httpSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("[archive-worker] http server", "error", err)
		}
	}()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() { defer wg.Done(); runArchive(ctx, loops, ids, m, cfg.Interval) }()

	slog.Info("[archive-worker] started", "realities", len(ids), "interval", cfg.Interval.String())

	<-ctx.Done()
	slog.Info("[archive-worker] shutdown signal")
	ready.set(false)
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpSrv.Shutdown(shutdownCtx)
	wg.Wait()
	slog.Info("[archive-worker] stopped")
	return nil
}

func buildLoop(pool *pgxpool.Pool, store *miniostore.Store, cutoff time.Duration) (*archive_loop.Loop, error) {
	st := state.NewPostgres(pool)
	picker, err := partition_picker.New(partition_picker.Config{
		Catalog: pgio.NewCatalog(pool),
		State:   st,
		Clock:   partition_picker.RealClock{},
		Cutoff:  cutoff,
	})
	if err != nil {
		return nil, err
	}
	return archive_loop.New(archive_loop.Config{
		Picker:     picker,
		Source:     pgio.NewRowSource(pool),
		Encoder:    parquet_writer.NewEncoder(),
		Decoder:    parquet_writer.NewDecoder(),
		Store:      store,
		State:      st,
		Dropper:    pgio.NewPartitionDropper(pool),
		Mode:       staticMode{},
		Clock:      archive_loop.RealClock{},
		BucketName: bucketName,
	})
}

// runArchive ticks every reality's archive loop. Each tick archives AT MOST
// one partition per reality (PickOldest) so a backlog drains in time order
// without one reality starving the others.
func runArchive(ctx context.Context, loops map[uuid.UUID]*archive_loop.Loop, ids []uuid.UUID, m *metrics, interval time.Duration) {
	t := time.NewTicker(interval)
	defer t.Stop()
	tick := func() {
		for _, rid := range ids {
			stats, err := loops[rid].Run(ctx, rid)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				m.errors.Inc()
				slog.Error("[archive-worker] archive iteration", "reality", rid, "error", err)
				continue
			}
			if stats.Dropped {
				m.archived.Inc()
				m.rowsArchived.Add(float64(stats.RowCount))
				m.bytesArchived.Add(float64(stats.ByteSize))
				slog.Info("[archive-worker] archived partition",
					"reality", rid, "partition", stats.Partition, "rows", stats.RowCount, "bytes", stats.ByteSize)
			}
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

// staticMode always reports ModeFull (archive-worker V1 has no degraded gating).
type staticMode struct{}

func (staticMode) Mode() lifecycle.ServiceMode { return lifecycle.ModeFull }

// ── Config ────────────────────────────────────────────────────────────────

type config struct {
	MetaDBURL      string
	MinioEndpoint  string
	MinioAccessKey string
	MinioSecretKey string
	MinioUseSSL    bool
	DSN            realityreg.DSNConfig
	Cutoff         time.Duration
	Interval       time.Duration
	HTTPAddr       string
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
	c.MinioEndpoint = req("MINIO_ENDPOINT")
	c.MinioAccessKey = req("MINIO_ACCESS_KEY")
	c.MinioSecretKey = req("MINIO_SECRET_KEY")
	dsnUser := req("SHARD_DB_USER")
	dsnPass := req("SHARD_DB_PASSWORD")
	if len(missing) > 0 {
		return c, fmt.Errorf("missing required env: %v", missing)
	}

	c.MinioUseSSL = os.Getenv("MINIO_USE_SSL") == "true"

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

	c.Cutoff = durationEnv("ARCHIVE_CUTOFF", 90*24*time.Hour)
	c.Interval = durationEnv("ARCHIVE_INTERVAL", time.Hour)
	c.HTTPAddr = os.Getenv("ARCHIVE_HTTP_ADDR")
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
	archived      prometheus.Counter
	rowsArchived  prometheus.Counter
	bytesArchived prometheus.Counter
	errors        prometheus.Counter
}

func newMetrics() *metrics {
	return &metrics{
		archived:      prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_archive_partitions_total", Help: "Partitions archived + dropped."}),
		rowsArchived:  prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_archive_rows_total", Help: "Event rows archived."}),
		bytesArchived: prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_archive_bytes_total", Help: "Encoded archive bytes uploaded."}),
		errors:        prometheus.NewCounter(prometheus.CounterOpts{Name: "lw_archive_errors_total", Help: "Archive iteration errors."}),
	}
}

func (m *metrics) collectors() []prometheus.Collector {
	return []prometheus.Collector{m.archived, m.rowsArchived, m.bytesArchived, m.errors}
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
