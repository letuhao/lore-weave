package main

import (
	"testing"
	"time"
)

func setRequiredEnv(t *testing.T) {
	t.Helper()
	t.Setenv("META_DB_URL", "postgres://m:m@localhost:55432/foundation?sslmode=disable")
	t.Setenv("MINIO_ENDPOINT", "localhost:59000")
	t.Setenv("MINIO_ACCESS_KEY", "foundation")
	t.Setenv("MINIO_SECRET_KEY", "foundation-secret-dev-only")
	t.Setenv("SHARD_DB_USER", "foundation")
	t.Setenv("SHARD_DB_PASSWORD", "foundation")
}

func TestLoadConfig_MissingRequiredFails(t *testing.T) {
	for _, k := range []string{"META_DB_URL", "MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "SHARD_DB_USER", "SHARD_DB_PASSWORD"} {
		t.Setenv(k, "")
	}
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
	if c.Cutoff != 90*24*time.Hour {
		t.Errorf("Cutoff default = %v want 90d", c.Cutoff)
	}
	if c.Interval != time.Hour {
		t.Errorf("Interval default = %v want 1h", c.Interval)
	}
	if c.HTTPAddr != ":8080" {
		t.Errorf("HTTPAddr default = %q want :8080", c.HTTPAddr)
	}
	if c.DSN.HostOverride["*"] != "localhost:55432" {
		t.Errorf("host override not parsed: %v", c.DSN.HostOverride)
	}
}

func TestLoadConfig_RespectsOverrides(t *testing.T) {
	setRequiredEnv(t)
	t.Setenv("ARCHIVE_CUTOFF", "1h")
	t.Setenv("ARCHIVE_INTERVAL", "30s")
	c, err := loadConfig()
	if err != nil {
		t.Fatalf("loadConfig: %v", err)
	}
	if c.Cutoff != time.Hour || c.Interval != 30*time.Second {
		t.Errorf("overrides not applied: cutoff=%v interval=%v", c.Cutoff, c.Interval)
	}
}
