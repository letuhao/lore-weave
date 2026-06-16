package main

import (
	"testing"
	"time"
)

func setRequiredEnv(t *testing.T) {
	t.Helper()
	t.Setenv("PUBLISHER_ID", "pub-1")
	t.Setenv("SHARD_HOST", "pg-shard-0.internal")
	t.Setenv("META_DB_URL", "postgres://m:m@localhost:55432/foundation?sslmode=disable")
	t.Setenv("REDIS_URL", "redis://localhost:56379/0")
	t.Setenv("SHARD_DB_USER", "foundation")
	t.Setenv("SHARD_DB_PASSWORD", "foundation")
}

func TestLoadConfig_MissingRequiredFails(t *testing.T) {
	// No env set → all required missing.
	t.Setenv("PUBLISHER_ID", "")
	t.Setenv("SHARD_HOST", "")
	t.Setenv("META_DB_URL", "")
	t.Setenv("REDIS_URL", "")
	t.Setenv("SHARD_DB_USER", "")
	t.Setenv("SHARD_DB_PASSWORD", "")
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected error when required env missing")
	}
}

func TestLoadConfig_DefaultsAndOverrides(t *testing.T) {
	setRequiredEnv(t)
	t.Setenv("PUBLISHER_SHARD_HOST_OVERRIDE", "*=localhost:55432")
	t.Setenv("SHARD_DB_SSLMODE", "disable")

	c, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if c.PollInterval != time.Second {
		t.Errorf("PollInterval default = %v want 1s", c.PollInterval)
	}
	if c.HeartbeatInterval != 10*time.Second {
		t.Errorf("HeartbeatInterval default = %v want 10s", c.HeartbeatInterval)
	}
	if c.BatchSize != 100 {
		t.Errorf("BatchSize default = %d want 100", c.BatchSize)
	}
	if c.HTTPAddr != ":8080" {
		t.Errorf("HTTPAddr default = %q want :8080", c.HTTPAddr)
	}
	if c.DSN.HostOverride["*"] != "localhost:55432" {
		t.Errorf("host override not parsed: %v", c.DSN.HostOverride)
	}
	// Sanity: the DSN resolver works with the loaded config.
	dsn, err := c.DSN.DSN("pg-shard-9.prod", "reality_x")
	if err != nil {
		t.Fatal(err)
	}
	if want := "@localhost:55432/reality_x"; !contains(dsn, want) {
		t.Errorf("DSN %q missing %q", dsn, want)
	}
}

func TestLoadConfig_RespectsExplicitIntervals(t *testing.T) {
	setRequiredEnv(t)
	t.Setenv("POLL_INTERVAL", "250ms")
	t.Setenv("HEARTBEAT_INTERVAL", "5s")
	t.Setenv("BATCH_SIZE", "500")
	t.Setenv("STREAM_MAXLEN", "100000")
	t.Setenv("PUBLISHER_HTTP_ADDR", ":9999")

	c, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if c.PollInterval != 250*time.Millisecond {
		t.Errorf("PollInterval = %v want 250ms", c.PollInterval)
	}
	if c.HeartbeatInterval != 5*time.Second {
		t.Errorf("HeartbeatInterval = %v want 5s", c.HeartbeatInterval)
	}
	if c.BatchSize != 500 {
		t.Errorf("BatchSize = %d want 500", c.BatchSize)
	}
	if c.StreamMaxLen != 100000 {
		t.Errorf("StreamMaxLen = %d want 100000", c.StreamMaxLen)
	}
	if c.HTTPAddr != ":9999" {
		t.Errorf("HTTPAddr = %q want :9999", c.HTTPAddr)
	}
}

func TestDurationEnv_FallsBackOnGarbage(t *testing.T) {
	t.Setenv("X_DUR", "not-a-duration")
	if got := durationEnv("X_DUR", 3*time.Second); got != 3*time.Second {
		t.Errorf("garbage duration should fall back, got %v", got)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (func() bool {
		for i := 0; i+len(sub) <= len(s); i++ {
			if s[i:i+len(sub)] == sub {
				return true
			}
		}
		return false
	})()
}
