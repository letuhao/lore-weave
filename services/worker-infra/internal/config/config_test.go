package config

import (
	"testing"
)

// setRequiredEnvs satisfies the required-env panics in Load() so tests
// that only care about OPTIONAL defaults don't blow up at requireEnv.
// Pre-D-WORKER-INFRA-CONFIG-TEST the suite called os.Unsetenv on every
// required var and asserted cfg.EventsDBURL != "" — Load() panicked
// before reaching the asserts; the test never ran in CI (likely never
// did, since the panic would have caught attention).
func setRequiredEnvs(t *testing.T) {
	t.Helper()
	t.Setenv("EVENTS_DB_URL", "postgres://test/events")
	t.Setenv("REDIS_URL", "redis://test:6379")
	t.Setenv("PANDOC_URL", "http://test:3030")
	t.Setenv("MINIO_ENDPOINT", "test:9000")
	t.Setenv("MINIO_ACCESS_KEY", "test")
	t.Setenv("MINIO_SECRET_KEY", "test")
	t.Setenv("BOOK_SERVICE_URL", "http://test:8080")
	t.Setenv("INTERNAL_SERVICE_TOKEN", "test_token")
}

func TestLoadDefaults(t *testing.T) {
	setRequiredEnvs(t)
	// Optional vars: explicitly unset (via t.Setenv to empty so cleanup is automatic).
	t.Setenv("WORKER_TASKS", "")
	t.Setenv("OUTBOX_SOURCES", "")
	t.Setenv("OUTBOX_CLEANUP_RETAIN_DAYS", "")

	cfg := Load()

	if cfg.EventsDBURL == "" {
		t.Fatal("expected EventsDBURL to carry the test value")
	}
	if cfg.RedisURL == "" {
		t.Fatal("expected RedisURL to carry the test value")
	}
	if cfg.CleanupRetainDays != 7 {
		t.Fatalf("expected default 7 retain days, got %d", cfg.CleanupRetainDays)
	}
	if len(cfg.WorkerTasks) != 0 {
		t.Fatalf("expected empty tasks, got %v", cfg.WorkerTasks)
	}
}

func TestLoadOutboxSources(t *testing.T) {
	setRequiredEnvs(t)
	t.Setenv("OUTBOX_SOURCES", "book:postgres://host/loreweave_book,glossary:postgres://host/loreweave_glossary")

	cfg := Load()

	if len(cfg.OutboxSources) != 2 {
		t.Fatalf("expected 2 sources, got %d", len(cfg.OutboxSources))
	}
	if cfg.OutboxSources[0].Name != "book" {
		t.Fatalf("expected source name 'book', got %q", cfg.OutboxSources[0].Name)
	}
	if cfg.OutboxSources[1].Name != "glossary" {
		t.Fatalf("expected source name 'glossary', got %q", cfg.OutboxSources[1].Name)
	}
}

func TestLoadWorkerTasks(t *testing.T) {
	setRequiredEnvs(t)
	t.Setenv("WORKER_TASKS", "outbox-relay,outbox-cleanup")

	cfg := Load()

	if len(cfg.WorkerTasks) != 2 {
		t.Fatalf("expected 2 tasks, got %d", len(cfg.WorkerTasks))
	}
	if cfg.WorkerTasks[0] != "outbox-relay" {
		t.Fatalf("expected 'outbox-relay', got %q", cfg.WorkerTasks[0])
	}
}
