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

	// P1 (2026-05-23) — knowledge-service /internal/parse for structural decomposition.
	KnowledgeServiceURL string

	// 26 IX-12 — composition-service /internal/books/{id}/materialize-scenes: the import
	// tail decompiles imported prose into spec scenes and writes back scenes.source_scene_id
	// from the returned map (composition never writes book-service's DB, SCOPE-2).
	CompositionServiceURL string

	// D-C-PRODUCER-OUTBOX — where the outbox relay delivers notification-typed rows
	// (the producers' durable notification path). Defaults to the compose service name.
	NotificationServiceURL string
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
		// P1 — defaults match docker-compose KNOWLEDGE_SERVICE_URL.
		KnowledgeServiceURL: envOrDefault("KNOWLEDGE_SERVICE_URL", "http://knowledge-service:8092"),
		// 26 IX-12 — default matches the compose service name/port.
		CompositionServiceURL: envOrDefault("COMPOSITION_SERVICE_URL", "http://composition-service:8093"),
		// D-C-PRODUCER-OUTBOX — default matches the compose service name/port.
		NotificationServiceURL: envOrDefault("NOTIFICATION_SERVICE_URL", "http://notification-service:8091"),
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
