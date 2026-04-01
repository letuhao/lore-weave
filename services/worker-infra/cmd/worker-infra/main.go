package main

import (
	"context"
	"log"
	"os/signal"
	"syscall"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/worker-infra/internal/config"
	"github.com/loreweave/worker-infra/internal/migrate"
	"github.com/loreweave/worker-infra/internal/registry"
	"github.com/loreweave/worker-infra/internal/tasks"
)

func main() {
	cfg := config.Load()

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Connect to events DB and run migration
	eventsPool, err := pgxpool.New(ctx, cfg.EventsDBURL)
	if err != nil {
		log.Fatalf("[main] events DB: %v", err)
	}
	defer eventsPool.Close()
	migrate.Up(ctx, eventsPool)

	// Connect to Redis
	opts, err := redis.ParseURL(cfg.RedisURL)
	if err != nil {
		log.Fatalf("[main] redis URL: %v", err)
	}
	rdb := redis.NewClient(opts)
	defer rdb.Close()
	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("[main] redis ping: %v", err)
	}
	log.Println("[main] redis connected")

	// Connect to each outbox source DB
	sourcePools := make(map[string]*pgxpool.Pool, len(cfg.OutboxSources))
	for _, src := range cfg.OutboxSources {
		p, err := pgxpool.New(ctx, src.DBURL)
		if err != nil {
			log.Fatalf("[main] source DB %q: %v", src.Name, err)
		}
		defer p.Close()
		sourcePools[src.Name] = p
		log.Printf("[main] source DB %q connected", src.Name)
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

	// Run selected tasks until signal
	log.Printf("[main] running tasks: %v", cfg.WorkerTasks)
	if err := reg.RunSelected(ctx, cfg.WorkerTasks); err != nil {
		log.Fatalf("[main] %v", err)
	}
	log.Println("[main] shutdown complete")
}
