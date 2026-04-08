package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
	"github.com/loreweave/worker-infra/internal/migrate"
	"github.com/loreweave/worker-infra/internal/registry"
	"github.com/loreweave/worker-infra/internal/tasks"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "worker-infra"))

	cfg := config.Load()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Connect to events DB and run migration
	eventsPool, err := pgxpool.New(ctx, cfg.EventsDBURL)
	if err != nil {
		slog.Error("events DB", "error", err)
		os.Exit(1)
	}
	defer eventsPool.Close()
	migrate.Up(ctx, eventsPool)

	// Connect to Redis
	opts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		slog.Error("redis URL", "error", err)
		os.Exit(1)
	}
	rdb := redis.NewClient(opts)
	defer rdb.Close()
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("redis ping", "error", err)
		os.Exit(1)
	}
	slog.Info("redis connected")

	// Connect to each outbox source DB
	sourcePools := make(map[string]*pgxpool.Pool, len(cfg.OutboxSources))
	for _, src := range cfg.OutboxSources {
		p, err := pgxpool.New(ctx, src.DBURL)
		if err != nil {
			slog.Error("source DB connection failed", "source", src.Name, "error", err)
			os.Exit(1)
		}
		defer p.Close()
		sourcePools[src.Name] = p
		slog.Info("source DB connected", "source", src.Name)
	}

	// Connect to book DB (for import-processor)
	var bookPool *pgxpool.Pool
	if cfg.BookDBURL != "" {
		bp, err := pgxpool.New(ctx, cfg.BookDBURL)
		if err != nil {
			slog.Error("book DB connection failed", "error", err)
			os.Exit(1)
		}
		defer bp.Close()
		bookPool = bp
		slog.Info("book DB connected")
	}

	// Connect to MinIO (for import-processor)
	var minioClient *minio.Client
	if cfg.MinioSecretKey != "" {
		mc, err := minio.New(cfg.MinioEndpoint, &minio.Options{
			Creds:  credentials.NewStaticV4(cfg.MinioAccessKey, cfg.MinioSecretKey, ""),
			Secure: false,
		})
		if err != nil {
			slog.Error("minio connection failed", "error", err)
			os.Exit(1)
		}
		minioClient = mc
		slog.Info("minio connected")
	}

	// Register tasks
	reg := registry.New()
	reg.Register(&tasks.OutboxRelay{
		Sources:     cfg.OutboxSources,
		SourcePools: sourcePools,
		EventsPool:  eventsPool,
		Redis:       rdb,
	})
	reg.Register(&tasks.OutboxCleanup{
		Sources:     cfg.OutboxSources,
		SourcePools: sourcePools,
		RetainDays:  cfg.CleanupRetainDays,
	})
	if bookPool != nil && minioClient != nil {
		reg.Register(&tasks.ImportProcessor{
			Cfg:    cfg,
			Redis:  rdb,
			BookDB: bookPool,
			Minio:  minioClient,
		})
	}

	// Run selected tasks until signal
	slog.Info("running tasks", "tasks", cfg.WorkerTasks)
	if err := reg.RunSelected(ctx, cfg.WorkerTasks); err != nil {
		slog.Error("fatal", "error", err)
		os.Exit(1)
	}
	slog.Info("shutdown complete")
}
