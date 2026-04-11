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

	// Import processor config
	BookDBURL       string
	PandocURL       string
	MinioEndpoint   string
	MinioAccessKey  string
	MinioSecretKey  string
	MinioBucket     string
	BookServiceURL  string
	InternalToken   string
	RabbitMQURL     string
}

func Load() *Config {
	cfg := &Config{
		EventsDBURL:       requireEnv("EVENTS_DB_URL"),
		RedisURL:          requireEnv("REDIS_URL"),
		CleanupRetainDays: 7,
		BookDBURL:         envOrDefault("BOOK_DB_URL", ""),
		PandocURL:         requireEnv("PANDOC_URL"),
		MinioEndpoint:     envOrDefault("MINIO_ENDPOINT", "localhost:9000"),
		MinioAccessKey:    envOrDefault("MINIO_ACCESS_KEY", "loreweave"),
		MinioSecretKey:    requireEnv("MINIO_SECRET_KEY"),
		MinioBucket:       envOrDefault("MINIO_BUCKET", "loreweave-dev-books"),
		BookServiceURL:    requireEnv("BOOK_SERVICE_URL"),
		InternalToken:     requireEnv("INTERNAL_SERVICE_TOKEN"),
		RabbitMQURL:       envOrDefault("RABBITMQ_URL", ""),
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

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		panic("required environment variable " + key + " is not set")
	}
	return v
}
