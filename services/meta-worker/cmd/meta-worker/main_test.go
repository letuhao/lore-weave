package main

import (
	"testing"
	"time"
)

func setRequiredEnv(t *testing.T) {
	t.Helper()
	t.Setenv("META_DB_URL", "postgres://m:m@localhost:55432/foundation?sslmode=disable")
	t.Setenv("REDIS_URL", "redis://localhost:56379/0")
	t.Setenv("SHARD_DB_USER", "foundation")
	t.Setenv("SHARD_DB_PASSWORD", "foundation")
}

func TestLoadConfig_MissingRequiredFails(t *testing.T) {
	t.Setenv("META_DB_URL", "")
	t.Setenv("REDIS_URL", "")
	t.Setenv("SHARD_DB_USER", "")
	t.Setenv("SHARD_DB_PASSWORD", "")
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected error when required env missing")
	}
}

func TestLoadConfig_Defaults(t *testing.T) {
	setRequiredEnv(t)
	t.Setenv("PUBLISHER_SHARD_HOST_OVERRIDE", "*=localhost:55432")
	c, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if c.CanonStream != "xreality.book.canon.updated" {
		t.Errorf("CanonStream=%q want xreality.book.canon.updated", c.CanonStream)
	}
	if c.ConsumerGroup != "meta-worker" {
		t.Errorf("ConsumerGroup=%q want meta-worker", c.ConsumerGroup)
	}
	if c.ConsumerID == "" {
		t.Error("ConsumerID should default to hostname")
	}
	if c.BatchSize != 100 {
		t.Errorf("BatchSize=%d want 100", c.BatchSize)
	}
	if c.Block != 2*time.Second {
		t.Errorf("Block=%v want 2s", c.Block)
	}
	if c.HTTPAddr != ":8080" {
		t.Errorf("HTTPAddr=%q want :8080", c.HTTPAddr)
	}
}

func TestLoadConfig_RespectsOverrides(t *testing.T) {
	setRequiredEnv(t)
	t.Setenv("CANON_STREAM", "xreality.custom")
	t.Setenv("CONSUMER_GROUP", "mw2")
	t.Setenv("CONSUMER_ID", "c7")
	t.Setenv("BATCH_SIZE", "50")
	t.Setenv("CONSUMER_BLOCK", "500ms")
	c, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if c.CanonStream != "xreality.custom" || c.ConsumerGroup != "mw2" || c.ConsumerID != "c7" {
		t.Errorf("overrides not applied: %+v", c)
	}
	if c.BatchSize != 50 || c.Block != 500*time.Millisecond {
		t.Errorf("batch/block override wrong: %+v", c)
	}
}
