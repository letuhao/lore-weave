package config

import (
	"os"
	"testing"
)

func TestLoadDefaults(t *testing.T) {
	// Clear env to test defaults
	os.Unsetenv("EVENTS_DB_URL")
	os.Unsetenv("REDIS_URL")
	os.Unsetenv("WORKER_TASKS")
	os.Unsetenv("OUTBOX_SOURCES")
	os.Unsetenv("OUTBOX_CLEANUP_RETAIN_DAYS")

	cfg := Load()

	if cfg.EventsDBURL == "" {
		t.Fatal("expected default EventsDBURL")
	}
	if cfg.RedisURL == "" {
		t.Fatal("expected default RedisURL")
	}
	if cfg.CleanupRetainDays != 7 {
		t.Fatalf("expected default 7 retain days, got %d", cfg.CleanupRetainDays)
	}
	if len(cfg.WorkerTasks) != 0 {
		t.Fatalf("expected empty tasks, got %v", cfg.WorkerTasks)
	}
}

func TestLoadOutboxSources(t *testing.T) {
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
	t.Setenv("WORKER_TASKS", "outbox-relay,outbox-cleanup")

	cfg := Load()

	if len(cfg.WorkerTasks) != 2 {
		t.Fatalf("expected 2 tasks, got %d", len(cfg.WorkerTasks))
	}
	if cfg.WorkerTasks[0] != "outbox-relay" {
		t.Fatalf("expected 'outbox-relay', got %q", cfg.WorkerTasks[0])
	}
}
