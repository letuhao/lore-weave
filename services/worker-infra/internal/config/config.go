package config

import (
	"os"
	"strconv"
	"strings"
)

type OutboxSource struct {
	Name  string
	DBURL string
}

type Config struct {
	WorkerTasks       []string
	EventsDBURL       string
	RedisURL          string
	OutboxSources     []OutboxSource
	CleanupRetainDays int
}

func Load() *Config {
	cfg := &Config{
		EventsDBURL:       envOrDefault("EVENTS_DB_URL", "postgres://loreweave:loreweave_dev@localhost:5432/loreweave_events"),
		RedisURL:          envOrDefault("REDIS_URL", "redis://localhost:6379"),
		CleanupRetainDays: 7,
	}

	if v := os.Getenv("WORKER_TASKS"); v != "" {
		cfg.WorkerTasks = strings.Split(v, ",")
	}

	if v := os.Getenv("OUTBOX_SOURCES"); v != "" {
		for _, entry := range strings.Split(v, ",") {
			parts := strings.SplitN(entry, ":", 2)
			if len(parts) == 2 {
				cfg.OutboxSources = append(cfg.OutboxSources, OutboxSource{
					Name:  strings.TrimSpace(parts[0]),
					DBURL: strings.TrimSpace(parts[1]),
				})
			}
		}
	}

	if v := os.Getenv("OUTBOX_CLEANUP_RETAIN_DAYS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			cfg.CleanupRetainDays = n
		}
	}

	return cfg
}

func envOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
